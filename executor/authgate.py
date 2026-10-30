# -*- coding: utf-8 -*-
"""executor.authgate —— 资源端授权校验与撤销竞态契约（AUTH-01 / AUTH-02）。

服务的规则：
- AASEGS-GOV-04（P1）：失败关闭。
- AASEGS-GOV-12（P0）：权威层级只是决策规则，必须靠权限/沙箱/CI 实现；
  **Prompt 不具备安全边界的法律效力或技术强制性**。
- AASEGS-AGT-004（P0）：标记 revocation_pending 的任务不得继续副作用操作。
- AASEGS-AGT-011（P0）：**上下文压缩摘要本身不能构成权限证据**。
- AASEGS-SUP-004（P0）：审批过期/拒绝/撤销必须闭合权限租约。

与 ID-01/ID-03（executor/authz.py）的分工：
- authz 管**租约的签发与主体隔离**——"谁可以拿到什么样的租约"；
- authgate 管**资源端在每次受保护操作前的独立校验**——"这一次操作凭什么放行"。
  资源端不信任签发方的自述，只信任自己能独立验签的凭证。

AUTH-01（资源端/独立网关授权检查，deny on any failure）
  1. 无租约 → 拒绝；
  2. 租约必须是**可独立验签**的签名凭证：形态不符、算法未知、验签材料缺失、
     签名不匹配 → 拒绝；
  3. **压缩摘要、记忆文本、Prompt 声明一律不构成权限证据**（AGT-011/GOV-12），
     以 dict/文本/``authority="prompt"`` 形式提交的权限主张一律拒绝；
  4. 租约必须与本次请求的 run_id/task_id 绑定，不符 → 拒绝（防跨任务借用）；
  5. 过期 → 拒绝；已撤销 → 拒绝；**撤销传播延迟期内同样拒绝**——
     不得以"还没同步到"为理由继续执行；
  6. 动作或资源超出 scope → 拒绝。

AUTH-02（撤销回执与竞态契约）
  7. 撤销必须产生**可核查的撤销回执**（receipt_ref），无回执的撤销不予受理；
  8. 撤销一经宣告即进入 ``revocation_pending``：此后**新的受保护副作用一律拒绝**，
     不等传播完成；
  9. 已发出且结果未知的在途请求**不得盲重试**，必须走状态核对
     （``confirmed_no_effect`` / ``confirmed_effect`` / ``unknown``）；
  10. 核对后仍为 ``unknown``（无法确认凭证是否已失效）→ **隔离执行通道并转人工**，
      人工放行前该通道上一切操作拒绝；
  11. 审批过期/拒绝/撤销 → 立即**闭合租约**（SUP-004），闭合后不可再用。

诚实边界（重要，不得据本模块宣称"身份体系已落地"）：
- 本模块是**进程内**的签发/校验分离：验签材料仍在同一进程内存中交换，
  信任根并未独立到另一主机或另一信任域，因此只能支撑 **tested（逻辑验证）**，
  不能支撑 **verified（独立信任域证据）**——后者属 AUTH-01/02 的 verified 路径，
  当前受 EXC-02 约束；
- 验签算法为 HMAC-SHA256（对称），仅用于证明"校验方独立验签、不接受自述"，
  不构成真实生产身份体系的安全强度声明；
- 撤销传播延迟在本模块内是**被显式建模并一律按拒绝处理**，不模拟真实网络延迟。
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime

from .audit import AuditLog

ALGORITHM = "HS256"
TOKEN_VERSION = "v1"
APPROVAL_CLOSED_STATES = ("expired", "rejected", "revoked")
RECONCILE_OUTCOMES = ("confirmed_no_effect", "confirmed_effect", "unknown")


class GatewayDenied(Exception):
    pass


def _parse(ts):
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64dec(s):
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _jsonable(v):
    """审计事件里不允许出现不可序列化的时间戳（曾导致告警写不进去）。"""
    return v.isoformat() if isinstance(v, datetime) else v


def _verifiable_ref(ref):
    """凭证必须可核查：URL / URN / 长哈希；空口声明不算凭证。"""
    if not ref or not isinstance(ref, str):
        return False
    ref = ref.strip()
    if ref.startswith(("http://", "https://", "urn:")):
        return True
    return len(ref) >= 16 and all(c.isalnum() or c in "-_:/." for c in ref)


class IdentityBroker:
    """签发方：唯一持有签名密钥的一侧。不得被资源端复用为校验方。"""

    def __init__(self, issuer_id, secret, audit_path):
        self.issuer_id = issuer_id
        self.secret = secret
        self.audit = AuditLog(audit_path)
        self.issued = {}

    # ---- 签发（这是本模块唯一能产生签名的入口）----
    def issue(self, lease_id, subject, run_id, task_id, scope,
              issued_at, expires_at, resources=None, subject_kind="run"):
        i, e = _parse(issued_at), _parse(expires_at)
        if i is None or e is None:
            raise GatewayDenied("unparseable_lease_window")
        if e <= i:
            raise GatewayDenied("non_positive_lease")
        payload = {
            "v": TOKEN_VERSION, "alg": ALGORITHM, "iss": self.issuer_id,
            "jti": lease_id, "sub": subject, "sub_kind": subject_kind,
            "run": run_id, "task": task_id, "scope": list(scope or []),
            "res": list(resources or []), "iat": str(issued_at),
            "exp": str(expires_at),
        }
        body = _b64(json.dumps(payload, sort_keys=True,
                               separators=(",", ":")).encode("utf-8"))
        sig = _b64(hmac.new(self.secret.encode("utf-8"),
                            f"{TOKEN_VERSION}.{body}".encode("ascii"),
                            hashlib.sha256).digest())
        token = f"{TOKEN_VERSION}.{body}.{sig}"
        self.issued[lease_id] = {"token": token, "payload": payload}
        self.audit.append("authgate.lease_issued", lease_id=lease_id,
                          subject=subject, run_id=run_id, task_id=task_id)
        return token

    def verify_material(self):
        """交给资源端的**校验用**材料（issuer → secret）。

        资源端只能用它验签，不得签发：``ResourceGateway`` 不提供 sign 方法。
        """
        return {self.issuer_id: self.secret}


class ResourceGateway:
    """资源端/独立网关：只做校验，不具备签发能力（职责分离）。"""

    def __init__(self, verify_keys, audit_path):
        self.keys = dict(verify_keys or {})
        self.audit = AuditLog(audit_path)
        self.revocations = {}        # jti -> {"pending_since","effective_at","receipt"}
        self.closed = {}             # jti -> {"reason","ref","at"}
        self.inflight = {}           # request_id -> {...}
        self.channel_quarantined = None
        self.human_release = None

    # ---------------- 内部：独立验签 ----------------
    def _verify(self, token, now):
        """返回 payload；任何一步不成立都抛 GatewayDenied（失败关闭）。"""
        # 1) 无租约
        if token is None:
            self._deny(None, "missing_lease", now=now)
        # 3) 压缩摘要 / 记忆文本 / Prompt 声明不构成权限证据（AGT-011/GOV-12）
        if isinstance(token, dict) or isinstance(token, (list, tuple)):
            self._deny(None, "summary_not_evidence", now=now,
                       shape=type(token).__name__)
        if not isinstance(token, str):
            self._deny(None, "lease_not_signed", now=now,
                       shape=type(token).__name__)
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != TOKEN_VERSION:
            # 形态不符：常见情形是把一段"看起来像授权"的文本当租约提交
            self._deny(None, "malformed_lease", now=now,
                       detail="not a signed credential")
        _, body, sig = parts
        try:
            payload = json.loads(_b64dec(body).decode("utf-8"))
        except Exception:
            self._deny(None, "malformed_lease", now=now, detail="undecodable")
        if payload.get("alg") != ALGORITHM or payload.get("v") != TOKEN_VERSION:
            self._deny(payload.get("jti"), "unsupported_algorithm",
                       alg=payload.get("alg"))
        key = self.keys.get(payload.get("iss"))
        if key is None:
            self._deny(payload.get("jti"), "unknown_issuer",
                       issuer=payload.get("iss"))
        expect = _b64(hmac.new(key.encode("utf-8"),
                               f"{TOKEN_VERSION}.{body}".encode("ascii"),
                               hashlib.sha256).digest())
        if not hmac.compare_digest(expect, sig):
            self._deny(payload.get("jti"), "invalid_signature")
        return payload

    def _deny(self, lease_id, reason, **extra):
        self.audit.append("authgate.denied", lease_id=lease_id, reason=reason,
                          **{k: _jsonable(v) for k, v in extra.items()})
        raise GatewayDenied(f"{reason}: {extra}")

    # ---------------- AUTH-01：每次受保护操作前的校验 ----------------
    def authorize(self, token, action, resource=None, run_id=None,
                  task_id=None, now=None, authority=None):
        # 执行通道被隔离（撤销后无法确认凭证状态）→ 一律拒绝，直到人工放行
        if self.channel_quarantined is not None:
            self._deny(None, "execution_channel_quarantined",
                       since=self.channel_quarantined, human_release_pending=True)
        now = _parse(now) or datetime.now()
        # GOV-12：Prompt 声明不是安全边界
        if authority in ("prompt", "declared", "asserted", "summary"):
            self._deny(None, "prompt_authority_not_enforceable",
                       authority=authority)
        payload = self._verify(token, now)
        jti = payload.get("jti")

        # 4) 绑定：租约必须与本次 run/task 一致（防跨任务借用）
        if run_id is not None and payload.get("run") != run_id:
            self._deny(jti, "binding_mismatch", field="run",
                       lease=payload.get("run"), request=run_id)
        if task_id is not None and payload.get("task") != task_id:
            self._deny(jti, "binding_mismatch", field="task",
                       lease=payload.get("task"), request=task_id)

        # 5) 撤销：一经宣告即拒绝，撤销传播延迟不构成继续执行的理由
        rev = self.revocations.get(jti)
        if rev is not None:
            # pending 与已生效都拒绝：差别只在告警语义，不在放行与否
            reason = ("revoked_lease" if rev.get("finalized")
                      else "revocation_pending")
            self._deny(jti, reason, resource=resource,
                       receipt=rev.get("receipt"))
        if jti in self.closed:
            self._deny(jti, "lease_closed",
                       close_reason=self.closed[jti]["reason"],
                       ref=self.closed[jti]["ref"])
        exp = _parse(payload.get("exp"))
        if exp is None or now > exp:
            self._deny(jti, "expired_lease", exp=payload.get("exp"))

        # 6) 超范围
        scope = payload.get("scope") or []
        if action not in scope and not any(
                s.endswith("*") and action.startswith(s[:-1]) for s in scope):
            self._deny(jti, "out_of_scope_action", action=action, scope=scope)
        res_scope = payload.get("res") or []
        if res_scope and resource is not None:
            if not any(resource == r or resource.startswith(r.rstrip("*"))
                       for r in res_scope):
                self._deny(jti, "out_of_scope_resource", resource=resource,
                           allowed=res_scope)

        self.audit.append("authgate.allowed", lease_id=jti, action=action,
                          resource=resource, run_id=payload.get("run"),
                          task_id=payload.get("task"))
        return {"decision": "ALLOWED", "lease_id": jti,
                "subject": payload.get("sub")}

    # ---------------- AUTH-02：撤销回执与竞态契约 ----------------
    def revoke(self, lease_id, receipt, at=None, propagation_seconds=0):
        if not _verifiable_ref(receipt):
            self.audit.append("authgate.revocation_rejected",
                              lease_id=lease_id,
                              reason="unverifiable_receipt", receipt=receipt)
            raise GatewayDenied(f"unverifiable_revocation_receipt: {lease_id}")
        at = _parse(at) or datetime.now()
        rec = {"pending_since": at.isoformat(), "receipt": receipt,
               "effective_at": None, "finalized": False,
               "propagation_seconds": propagation_seconds}
        self.revocations[lease_id] = rec
        # 在途请求：不得盲重试，必须逐条核对真实状态
        pending = [rid for rid, r in self.inflight.items()
                   if r.get("lease_id") == lease_id and not r.get("reconciled")]
        self.audit.append("authgate.revocation_pending", lease_id=lease_id,
                          receipt=receipt, pending_requests=pending)
        return {"lease_id": lease_id, "state": "revocation_pending",
                "receipt_ref": receipt,
                "effective_at": rec["effective_at"],
                "inflight_requiring_reconciliation": pending}

    def finalize_revocation(self, lease_id, at=None):
        """传播完成：撤销从 pending 转为已生效（撤销前后一律拒绝）。"""
        rec = self.revocations.get(lease_id)
        if rec is None:
            raise GatewayDenied(f"unknown_revocation: {lease_id}")
        at = _parse(at) or datetime.now()
        rec["effective_at"] = at.isoformat()
        rec["finalized"] = True
        self.audit.append("authgate.revocation_effective", lease_id=lease_id,
                          effective_at=rec["effective_at"])
        return {"lease_id": lease_id, "state": "revoked",
                "effective_at": rec["effective_at"]}

    # ---- 在途请求：状态核对，不盲重试 ----
    def declare_inflight(self, request_id, lease_id, action, resource=None):
        self.inflight[request_id] = {"request_id": request_id,
                                     "lease_id": lease_id, "action": action,
                                     "resource": resource, "reconciled": False,
                                     "outcome": None}
        return self.inflight[request_id]

    def reconcile(self, request_id, outcome, evidence_ref=None):
        req = self.inflight.get(request_id)
        if req is None:
            raise GatewayDenied(f"unknown_inflight_request: {request_id}")
        if outcome not in RECONCILE_OUTCOMES:
            self._deny(req.get("lease_id"), "invalid_reconcile_outcome",
                       request_id=request_id, outcome=outcome)
        if not _verifiable_ref(evidence_ref):
            self._deny(req.get("lease_id"), "unverifiable_reconcile_evidence",
                       request_id=request_id, evidence_ref=evidence_ref)
        req["reconciled"] = True
        req["outcome"] = outcome
        req["evidence_ref"] = evidence_ref
        self.audit.append("authgate.inflight_reconciled",
                          request_id=request_id, outcome=outcome,
                          lease_id=req.get("lease_id"))
        return req

    def retry(self, request_id, token=None, now=None):
        """重试必须建立在真实状态核对之上：unknown → 不盲重试并隔离通道。"""
        req = self.inflight.get(request_id)
        if req is None:
            raise GatewayDenied(f"unknown_inflight_request: {request_id}")
        lease_id = req.get("lease_id")
        if self.channel_quarantined is not None:
            self._deny(lease_id, "execution_channel_quarantined")
        if not req.get("reconciled"):
            self._deny(lease_id, "blind_retry_denied",
                       request_id=request_id,
                       detail="result unknown, reconcile required")
        if req.get("outcome") == "unknown":
            # 无法确认凭证是否已失效 → 隔离执行通道并转人工
            self.channel_quarantined = (self.channel_quarantined
                                        or datetime.now().isoformat())
            self.audit.append("authgate.channel_quarantined",
                              lease_id=lease_id, request_id=request_id,
                              reason="credential_state_unconfirmable")
            self._deny(lease_id, "credential_state_unconfirmable",
                       request_id=request_id, escalated_to="human")
        if req.get("outcome") == "confirmed_effect":
            self._deny(lease_id, "retry_would_duplicate_effect",
                       request_id=request_id)
        # confirmed_no_effect：可安全重试，但仍需重新走一次完整授权校验
        if token is None:
            self._deny(lease_id, "missing_lease", request_id=request_id)
        return self.authorize(token, req.get("action"),
                              resource=req.get("resource"), now=now)

    def release_channel(self, human_approver, ref=None):
        if self.channel_quarantined is None:
            return "NOT_QUARANTINED"
        if not human_approver or not _verifiable_ref(ref):
            raise GatewayDenied("channel_release_needs_human_and_ref")
        self.channel_quarantined = None
        self.human_release = {"approver": human_approver, "ref": ref}
        self.audit.append("authgate.channel_released",
                          approver=human_approver, ref=ref)
        return "RELEASED"

    # ---- SUP-004：审批过期/拒绝/撤销 → 闭合租约 ----
    def close_for_approval(self, lease_id, approval_state, approval_ref):
        if approval_state not in APPROVAL_CLOSED_STATES:
            raise GatewayDenied(f"invalid_approval_state: {approval_state}")
        if not _verifiable_ref(approval_ref):
            self.audit.append("authgate.lease_close_rejected",
                              lease_id=lease_id,
                              reason="unverifiable_approval_ref")
            raise GatewayDenied("unverifiable_approval_ref")
        self.closed[lease_id] = {"reason": f"approval_{approval_state}",
                                 "ref": approval_ref,
                                 "at": datetime.now().isoformat()}
        self.audit.append("authgate.lease_closed", lease_id=lease_id,
                          approval_state=approval_state, ref=approval_ref)
        return {"lease_id": lease_id, "state": "closed",
                "reason": f"approval_{approval_state}"}
