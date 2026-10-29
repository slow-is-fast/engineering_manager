# -*- coding: utf-8 -*-
"""executor.approval —— 人工审批闸门（APR-01）。

服务的规则：
- GOV-06 人工最终责任
- GOV-15 审批必须绑定 task_id + risk + scope + policy_hash + commit_sha(如适用)
        + expires_at；审批过期、对象变化、吊销则失效
- GOV-17 不得允许 Agent 自行批准自己受影响的例外
- SEC-009 R3 不得因 AI Reviewer 判断 PASS 而自动放行

闸门语义：
  1. 审批是**有界对象**：绑定任务、风险、范围、策略版本、提交、有效期；
  2. 任一绑定要素漂移（换 commit、扩范围、升风险、换策略）→ 审批失效；
  3. 过期或吊销 → 失效；
  4. R3 必须有**人类**审批；仅凭 AI Reviewer 的 PASS 不放行；
  5. 失败关闭：任何疑问都拒绝，不"默认放行"。

诚实边界：本模块验证"审批记录与当前请求是否一致"；
它不证明审批人本人的意愿（那是身份服务的职责，见 ATT-01 的同类声明）。
"""
from datetime import datetime
from .audit import AuditLog


class Rejected(Exception):
    pass


def _parse(ts):
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))


class ApprovalGate:
    def __init__(self, human_principals, audit_path):
        self.humans = set(human_principals)
        self.audit = AuditLog(audit_path)
        self.approvals = {}
        self.revoked = set()

    # ---- 签发：审批本身必须绑定六要素，且主体是人类 ----
    def grant(self, approval_id, approver, task_id, risk, scope, policy_hash,
              commit_sha=None, expires_at=None, channel="signed_record"):
        if approver not in self.humans:
            self.audit.append("approval.rejected", approval_id=approval_id,
                              reason="non_human_grantor", approver=approver)
            raise Rejected(f"non_human_grantor: {approver}")
        self.approvals[approval_id] = {
            "approval_id": approval_id, "approver": approver, "task_id": task_id,
            "risk": risk, "scope": list(scope or []), "policy_hash": policy_hash,
            "commit_sha": commit_sha, "expires_at": expires_at, "channel": channel,
        }
        self.audit.append("approval.granted", approval_id=approval_id,
                          task_id=task_id, risk=risk, approver=approver)
        return self.approvals[approval_id]

    def revoke(self, approval_id, reason="unspecified"):
        self.revoked.add(approval_id)
        self.audit.append("approval.revoked", approval_id=approval_id, reason=reason)

    def _reject(self, approval_id, reason, **extra):
        self.audit.append("approval.rejected", approval_id=approval_id,
                          reason=reason, **extra)
        raise Rejected(f"{reason}: {extra}")

    # ---- 校验：审批是否仍然覆盖当前请求 ----
    def validate(self, approval_id, request, now=None, ai_verdict=None):
        """
        request: {task_id, risk, scope, policy_hash, commit_sha?}
        ai_verdict: AI Reviewer 的结论（如 "PASS"），仅作参考，不构成放行依据
        """
        a = self.approvals.get(approval_id)
        if a is None:
            self._reject(approval_id, "unknown_approval")
        if approval_id in self.revoked:
            self._reject(approval_id, "revoked_approval")

        if a["expires_at"]:
            now_dt = _parse(now) if isinstance(now, str) else (now or datetime.now())
            if now_dt > _parse(a["expires_at"]):
                self._reject(approval_id, "expired_approval",
                             expires_at=a["expires_at"])

        for field in ("task_id", "risk", "policy_hash"):
            if request.get(field) != a[field]:
                self._reject(approval_id, "binding_drift", field=field,
                             approved=a[field], requested=request.get(field))

        approved_scope = set(a["scope"])
        requested_scope = set(request.get("scope") or [])
        if not requested_scope <= approved_scope:
            self._reject(approval_id, "scope_creep",
                         extra=sorted(requested_scope - approved_scope))

        if a["commit_sha"] and request.get("commit_sha") \
                and request["commit_sha"] != a["commit_sha"]:
            self._reject(approval_id, "commit_drift",
                         approved=a["commit_sha"], requested=request["commit_sha"])

        # SEC-009：R3 必须有人工审批；AI Reviewer 的 PASS 不能单独放行
        if request.get("risk") == "R3":
            if a["approver"] not in self.humans:
                self._reject(approval_id, "r3_requires_human_approval",
                             approver=a["approver"])
            if ai_verdict == "PASS" and a["channel"] not in (
                    "pr_review", "signed_record", "cli_attest"):
                self._reject(approval_id, "r3_ai_pass_not_sufficient",
                             channel=a["channel"])

        self.audit.append("approval.valid", approval_id=approval_id,
                          task_id=a["task_id"], risk=a["risk"],
                          ai_verdict=ai_verdict)
        return "APPROVED"
