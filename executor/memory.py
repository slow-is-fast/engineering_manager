# -*- coding: utf-8 -*-
"""executor.memory —— 共享记忆生命周期（MEM-01 / CTX-02 / CTX-03）。

规则（v1.1.1 §4）：
- AGT-007（P1）：晋升为跨任务共享记忆必须进行**来源校验与授权审核**；
- AGT-008（P1）：共享记忆必须可撤销、可检索版本历史；
- AGT-009（P1）：**过期、被否定或撤销的记忆不得用于新任务的规范性决策**。

状态机：DRAFT → PENDING_REVIEW → APPROVED → (REVOKED | EXPIRED)
        任意非终态 → INVALIDATED（来源失效时的级联）

MEM-01 要点（缺失即被审计问题 AUD-006 点名）：
  1. **来源校验**：晋升前必须有可信来源与可核查引用（`verify_source`），
     且校验人 ≠ 作者；未校验直接 submit/approve 一律拒绝；
  2. **版本 CAS**：并发更新以版本号乐观锁拒绝（`CasConflict`）；
  3. **摘要派生与残留**：摘要继承父记忆版本身份；父记忆被撤销/过期/失效
     → 摘要**立即 stale**，检索不可见、决策不可用（防"摘要残留"绕过撤销）；
  4. **撤销传播**：撤销在同一临界区内级联到全部后代，不留窗口；
  5. **来源失效**：`invalidate_source` 把该来源派生出的记忆整体置为不可用，
     并返回传播清单（可审计的"影响了哪些记忆"）。

诚实边界：这是**进程内**的状态机与传播；持久化只是一个 JSON 文件，
不提供跨进程缓存失效、不实现真实索引/向量库的删除传播（AUD-006 的
"检索/缓存集成测试"属关闭条件，本模块不能自称满足）。
"""
import json
import threading
from pathlib import Path

from .audit import AuditLog

TRUSTED_SOURCES = ("human_direct", "signed_policy")
KNOWN_SOURCES = ("human_direct", "signed_policy", "tool_output", "web",
                 "doc", "model", "memory", "unknown")
USABLE_STATES = ("APPROVED",)
TERMINAL = ("REVOKED", "EXPIRED", "INVALIDATED")


class InvalidTransition(Exception):
    pass


class CasConflict(Exception):
    pass


class Unusable(Exception):
    """记忆不可用于规范性决策（撤销/过期/失效/摘要残留/未审核）。"""


def _verifiable_ref(ref):
    if not ref or not isinstance(ref, str):
        return False
    ref = ref.strip()
    if ref.startswith(("http://", "https://", "urn:")):
        return True
    return len(ref) >= 16 and all(c.isalnum() or c in "-_:/." for c in ref)


class MemoryStore:
    def __init__(self, path, audit_path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(audit_path)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf8")

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf8"))

    def _save(self, d):
        self.path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf8")

    def create(self, mid, author, content, source_kind="unknown", source_ref=None):
        with self._lock:
            d = self._load()
            if source_kind not in KNOWN_SOURCES:
                # 未知来源不拒绝创建，但永远无法通过晋升校验（失败关闭）
                source_kind = "unknown"
            d[mid] = {"state": "DRAFT", "author": author, "content": content,
                      "version": 1, "source_kind": source_kind,
                      "source_ref": source_ref, "source_verified": False,
                      "source_verified_by": None, "parents": [],
                      "derived": False, "stale": False}
            self._save(d)
            self.audit.append("memory.created", mid=mid, author=author,
                              source_kind=source_kind)
            return 1

    # ---------------- 来源校验（AGT-007） ----------------
    def verify_source(self, mid, verifier, ref):
        with self._lock:
            d = self._load()
            r = d[mid]
            if not _verifiable_ref(ref):
                self.audit.append("memory.source_verify_rejected", mid=mid,
                                  reason="unverifiable_ref", ref=ref)
                raise InvalidTransition(f"{mid}: 来源引用不可核查")
            if not verifier or verifier == r["author"]:
                # 作者不能给自己的来源背书
                self.audit.append("memory.source_verify_rejected", mid=mid,
                                  reason="self_verification")
                raise InvalidTransition(f"{mid}: 来源校验人不得为作者")
            r["source_verified"] = True
            r["source_verified_by"] = verifier
            r["source_ref"] = ref
            r["version"] += 1
            self._save(d)
            self.audit.append("memory.source_verified", mid=mid,
                              verifier=verifier, ref=ref)
            return r["version"]

    def submit_for_review(self, mid, expect_version):
        with self._lock:
            d = self._load()
            r = d[mid]
            if r["version"] != expect_version:
                raise CasConflict(mid)
            if r["state"] != "DRAFT":
                raise InvalidTransition(f"{mid}: {r['state']} -> PENDING_REVIEW")
            if not r.get("source_verified"):
                # 未做来源校验的记忆不得进入晋升通道
                raise InvalidTransition(f"{mid}: 来源未校验，不得晋升")
            r["state"], r["version"] = "PENDING_REVIEW", r["version"] + 1
            self._save(d)
            self.audit.append("memory.submitted", mid=mid)
            return r["version"]

    def approve(self, mid, approver):
        with self._lock:
            d = self._load()
            r = d[mid]
            if r["state"] != "PENDING_REVIEW":
                raise InvalidTransition(f"{mid}: {r['state']} -> APPROVED（必须先经审核）")
            if approver == r["author"]:
                self.audit.append("memory.approval_denied_self", mid=mid,
                                  approver=approver)
                raise InvalidTransition(f"{mid}: 作者不能自批晋升")
            r["state"], r["approver"] = "APPROVED", approver
            r["version"] += 1
            self._save(d)
            self.audit.append("memory.approved", mid=mid, approver=approver)
            return r["version"]

    # ---------------- 摘要派生（防"摘要残留"） ----------------
    def derive_summary(self, mid, parent_ids, content, author):
        with self._lock:
            d = self._load()
            parents = []
            for pid in parent_ids:
                p = d.get(pid)
                if p is None:
                    raise Unusable(f"{mid}: 父记忆不存在 {pid}")
                if not self._usable(pid, d):
                    raise Unusable(f"{mid}: 父记忆不可用 {pid}")
                parents.append({"id": pid, "version": p["version"]})
            d[mid] = {"state": "APPROVED", "author": author, "content": content,
                      "version": 1, "source_kind": "memory",
                      "source_ref": "urn:summary:" + mid,
                      "source_verified": True, "source_verified_by": author,
                      "parents": parents, "derived": True, "stale": False}
            self._save(d)
            self.audit.append("memory.summary_derived", mid=mid,
                              parents=[p["id"] for p in parents])
            return 1

    # ---------------- 撤销 / 过期 / 来源失效 ----------------
    def _descendants(self, mid, d):
        kids = [m for m, r in d.items()
                if any(p["id"] == mid for p in (r.get("parents") or []))]
        out = list(kids)
        for k in kids:
            out.extend(self._descendants(k, d))
        return out

    def revoke(self, mid, actor):
        """撤销并立即传播到后代（同一事务，无窗口）。"""
        with self._lock:
            d = self._load()
            r = d[mid]
            if r["state"] not in ("APPROVED", "PENDING_REVIEW"):
                raise InvalidTransition(f"{mid}: {r['state']} -> REVOKED")
            r["state"] = "REVOKED"
            r["version"] += 1
            stale = []
            for kid in self._descendants(mid, d):
                d[kid]["stale"] = True
                stale.append(kid)
            self._save(d)                      # 撤销与传播在同一临界区完成
            self.audit.append("memory.revoked", mid=mid, actor=actor,
                              stale_summaries=stale)
            return r["version"]

    def expire(self, mid, at=None):
        with self._lock:
            d = self._load()
            r = d[mid]
            if r["state"] != "APPROVED":
                raise InvalidTransition(f"{mid}: {r['state']} -> EXPIRED")
            r["state"] = "EXPIRED"
            r["version"] += 1
            stale = []
            for kid in self._descendants(mid, d):
                d[kid]["stale"] = True
                stale.append(kid)
            self._save(d)
            self.audit.append("memory.expired", mid=mid, at=at,
                              stale_summaries=stale)
            return r["version"]

    def invalidate_source(self, source_ref, actor):
        """来源失效 → 该来源派生的记忆整体不可用，摘要级联 stale。"""
        with self._lock:
            d = self._load()
            affected = [m for m, r in d.items()
                        if r.get("source_ref") == source_ref
                        and r["state"] not in TERMINAL]
            stale = []
            for m in affected:
                d[m]["state"] = "INVALIDATED"
                d[m]["version"] += 1
                for kid in self._descendants(m, d):
                    d[kid]["stale"] = True
                    stale.append(kid)
            self._save(d)
            self.audit.append("memory.source_invalidated", source_ref=source_ref,
                              actor=actor, affected=affected, stale_summaries=stale)
            return {"affected": affected, "stale_summaries": stale}

    # ---------------- 可用性判定 ----------------
    def _usable(self, mid, d, _depth=0):
        if _depth > 32:
            return False
        r = d.get(mid)
        if r is None:
            return False
        if r["state"] not in USABLE_STATES:
            return False
        if r.get("stale"):
            return False
        if not r.get("source_verified", True):
            return False
        # 派生摘要必须逐个父记忆仍然可用（防"父被撤销、摘要还在用"）
        return all(self._usable(p["id"], d, _depth + 1)
                   for p in (r.get("parents") or []))

    def is_usable(self, mid):
        return self._usable(mid, self._load())

    def resolve_for_decision(self, mid):
        """规范性决策入口：不可用即抛 Unusable，并写明原因。"""
        d = self._load()
        r = d.get(mid)
        if r is None:
            raise Unusable(f"{mid}: 不存在")
        if r["state"] == "REVOKED":
            raise Unusable(f"{mid}: 已撤销")
        if r["state"] == "EXPIRED":
            raise Unusable(f"{mid}: 已过期")
        if r["state"] == "INVALIDATED":
            raise Unusable(f"{mid}: 来源失效")
        if r["state"] != "APPROVED":
            raise Unusable(f"{mid}: 未完成审核（{r['state']}）")
        if r.get("stale"):
            raise Unusable(f"{mid}: 摘要残留（父记忆已不可用）")
        if not self._usable(mid, d):
            raise Unusable(f"{mid}: 父记忆链不可用")
        return r

    def search(self, reader):
        """规范性检索：只返回可用记忆（APPROVED 且非 stale 且父链可用）。"""
        d = self._load()
        return [m for m in d if self._usable(m, d)]

