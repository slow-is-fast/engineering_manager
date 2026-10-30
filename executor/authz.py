# -*- coding: utf-8 -*-
"""executor.authz —— 受保护操作的运行时授权与撤销（ID-01 / ID-03）。

服务的规则：
- AASEGS-AGT-002（P0）：租约必须短期、任务限域；禁止共享人类个人 Token；
  禁止继承前一 Agent 的权限。
- AASEGS-AGT-003（P0）：授权必须由可信 Identity Broker/平台签发，
  **Agent 不能自我宣布身份**。
- AASEGS-AGT-004（P0）：标记 revocation_pending 的任务不得继续副作用操作。

语义（全部失败关闭）：
  ID-01（deny and alert）
    1. 租约必须由**可信签发方**签发，且签发方 ≠ 主体——自己给自己签发即拒绝；
    2. 租约必须**短期**（≤ MAX_LEASE_HOURS）且有到期时间；
    3. 租约必须**任务限域**：绑定 run_id + task_id + scope 清单；
    4. 主体类型必须是 run/service，**不得是人类个人 Token**（禁止共享人类凭证）；
    5. 授权请求的动作必须落在 scope 内，否则拒绝并告警；
    6. 过期、未知、已撤销的租约一律拒绝。

  ID-03（quarantine and deny）
    7. 撤销必须携带**可核查的撤销凭证**（http/https/urn/长哈希），空口撤销不予受理；
    8. 收到撤销凭证后主体进入隔离态，此后所有授权请求一律拒绝并告警；
    9. 隔离是**单向**的：解除隔离需另行重新签发租约，不得由主体自行清除。

诚实边界：本模块是进程内的授权判定；它假设签发方本身可信（身份服务的
信任根不在本模块内），也不实现跨进程/跨主机的凭证校验（AUTH-01/02 的
资源端校验范围）。不得据本模块宣称"身份体系已落地"。
"""
from datetime import datetime

from .audit import AuditLog

MAX_LEASE_HOURS = 8
SUBJECT_KINDS = ("run", "service")


class Denied(Exception):
    pass


def _parse(ts):
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def _verifiable_ref(ref):
    """撤销凭证必须可核查：URL / URN / 长哈希；空口声明不算凭证。"""
    if not ref or not isinstance(ref, str):
        return False
    ref = ref.strip()
    if ref.startswith(("http://", "https://", "urn:")):
        return True
    return len(ref) >= 16 and all(c.isalnum() or c in "-_:/." for c in ref)


class AuthorizationService:
    def __init__(self, trusted_issuers, audit_path):
        self.issuers = set(trusted_issuers)
        self.audit = AuditLog(audit_path)
        self.leases = {}
        self.quarantined = {}     # subject -> receipt

    # ---------------- ID-01：签发短期、任务限域、不可自授的租约 ----------------
    def issue_lease(self, lease_id, issuer, subject, subject_kind,
                    run_id, task_id, scope, issued_at, expires_at):
        if issuer not in self.issuers:
            self._deny(lease_id, "untrusted_issuer", issuer=issuer)
        if issuer == subject:
            # Agent 不能自我宣布身份：自己签发给自己
            self._deny(lease_id, "self_issued_lease", subject=subject)
        if subject_kind not in SUBJECT_KINDS:
            # 人类个人 Token 不得作为 Run 的租约主体（禁止共享人类凭证）
            self._deny(lease_id, "human_token_not_allowed", subject=subject,
                       subject_kind=subject_kind)
        if not run_id or not task_id:
            self._deny(lease_id, "lease_not_task_scoped", run_id=run_id,
                       task_id=task_id)
        if not scope:
            self._deny(lease_id, "empty_scope")
        i, e = _parse(issued_at), _parse(expires_at)
        if e <= i:
            self._deny(lease_id, "non_positive_lease")
        hours = (e - i).total_seconds() / 3600
        if hours > MAX_LEASE_HOURS:
            self._deny(lease_id, "lease_too_long", hours=hours)

        self.leases[lease_id] = {
            "lease_id": lease_id, "issuer": issuer, "subject": subject,
            "subject_kind": subject_kind, "run_id": run_id, "task_id": task_id,
            "scope": list(scope), "issued_at": issued_at,
            "expires_at": expires_at, "revoked": False,
        }
        self.audit.append("authz.lease_issued", lease_id=lease_id,
                          subject=subject, task_id=task_id, hours=hours)
        return self.leases[lease_id]

    def _deny(self, lease_id, reason, **extra):
        self.audit.append("authz.denied", lease_id=lease_id, reason=reason,
                          **extra)
        raise Denied(f"{reason}: {extra}")

    def authorize(self, lease_id, action, now):
        lease = self.leases.get(lease_id)
        if lease is None:
            self._deny(lease_id, "unknown_lease", action=action)
        # 隔离优先于租约撤销：隔离是主体级强状态，告警必须是 quarantined_subject
        if lease["subject"] in self.quarantined:
            self._deny(lease_id, "quarantined_subject", action=action,
                       subject=lease["subject"])
        if lease["revoked"]:
            self._deny(lease_id, "revoked_lease", action=action)
        if _parse(now) > _parse(lease["expires_at"]):
            self._deny(lease_id, "expired_lease", action=action, now=now)
        if not any(action == s or action.startswith(s.rstrip("*"))
                   for s in lease["scope"]):
            self._deny(lease_id, "out_of_scope_action", action=action,
                       scope=lease["scope"])
        self.audit.append("authz.allowed", lease_id=lease_id, action=action,
                          subject=lease["subject"])
        return "ALLOWED"

    # ---------------- ID-03：凭撤销凭证隔离主体 ----------------
    def revoke(self, subject, receipt, reason="unspecified"):
        if not _verifiable_ref(receipt):
            self.audit.append("authz.revocation_rejected", subject=subject,
                              reason="unverifiable_receipt", receipt=receipt)
            raise Denied(f"unverifiable_revocation_receipt: {subject}")
        self.quarantined[subject] = {"receipt": receipt, "reason": reason}
        for lease in self.leases.values():
            if lease["subject"] == subject:
                lease["revoked"] = True
        self.audit.append("authz.subject_quarantined", subject=subject,
                          receipt=receipt, reason=reason)
        return "QUARANTINED"

    def is_quarantined(self, subject):
        return subject in self.quarantined

    def release_quarantine(self, subject, new_lease_id):
        """解除隔离必须凭**新签发**的租约，不得由主体自行清除。"""
        if subject not in self.quarantined:
            return "NOT_QUARANTINED"
        lease = self.leases.get(new_lease_id)
        if lease is None or lease["subject"] != subject or lease["revoked"]:
            self.audit.append("authz.quarantine_release_rejected",
                              subject=subject, lease_id=new_lease_id)
            raise Denied(f"quarantine_release_needs_fresh_lease: {subject}")
        del self.quarantined[subject]
        self.audit.append("authz.quarantine_released", subject=subject,
                          lease_id=new_lease_id)
        return "RELEASED"
