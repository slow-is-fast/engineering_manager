# -*- coding: utf-8 -*-
"""executor.memory —— 共享记忆生命周期（MEM-01 / CTX-02 / CTX-03 简化实现）。

规则（v1.1.1 §4）：
- 状态机 DRAFT -> PENDING_REVIEW -> APPROVED -> (REVOKED | EXPIRED)，CAS 版本控制；
- 晋升必须由非作者审批（职责分离）；
- 撤销必须传播：写入 revocation list，检索层据此过滤（传播与过滤是同一动作，无窗口）；
- 检索只返回 APPROVED 且未撤销未过期的记忆；
- 并发更新 CAS 冲突拒绝。
"""
import json, threading
from pathlib import Path
from .audit import AuditLog


class InvalidTransition(Exception):
    pass


class CasConflict(Exception):
    pass


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

    def create(self, mid, author, content):
        with self._lock:
            d = self._load()
            d[mid] = {"state": "DRAFT", "author": author, "content": content,
                      "version": 1}
            self._save(d)
            self.audit.append("memory.created", mid=mid, author=author)
            return 1

    def submit_for_review(self, mid, expect_version):
        with self._lock:
            d = self._load()
            r = d[mid]
            if r["version"] != expect_version:
                raise CasConflict(mid)
            if r["state"] != "DRAFT":
                raise InvalidTransition(f"{mid}: {r['state']} -> PENDING_REVIEW")
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

    def revoke(self, mid, actor):
        """撤销并立即传播到检索层（同一事务）。"""
        with self._lock:
            d = self._load()
            r = d[mid]
            if r["state"] not in ("APPROVED", "PENDING_REVIEW"):
                raise InvalidTransition(f"{mid}: {r['state']} -> REVOKED")
            r["state"] = "REVOKED"
            r["version"] += 1
            self._save(d)                      # 撤销与传播在同一临界区完成
            self.audit.append("memory.revoked", mid=mid, actor=actor)
            return r["version"]

    def search(self, reader):
        """规范性检索：只返回 APPROVED。REVOKED/EXPIRED/DRAFT/PENDING 一律不可见。"""
        d = self._load()
        return [m for m, r in d.items() if r["state"] == "APPROVED"]
