# -*- coding: utf-8 -*-
"""executor.attestation —— 人工审批主体真实性校验（ATT-01 / 规则 AASEGS-SUP-005）。

规则：不得让同一 Agent 假扮"人工批准"。

本模块是审批证明的最低机器化约束（不是身份服务的替代品）：
- 审批主体必须是**人类委托人**（human allowlist），principal_type 必须为 human；
- 主体标识不得是 Agent/Run 身份（禁止 `agent-*` / 与 run_id 相同 / `self`）；
- 必须携带**外部可核查的旁证**（attestation_ref，指向 PR review / 签名记录 / CLI 凭证）；
- 证明通道必须**带外**（out-of-band：pr_review / signed_record / cli_attest），
  禁止 `self`、`in_band`、`prompt` 一类同通道声明；
- 缺字段、占位值、策略哈希不符一律 REJECT（失败关闭）。

诚实边界：本校验只能证明"审批证明材料齐全且主体不似 Agent"；
没有独立身份服务（IdP 签名）时，它不能证明审批人本人按下过按钮——
那是 identity attestation 控制的职责（T-ID 系列）。不要越界宣称。
"""
from .audit import AuditLog

REQUIRED = ("task_id", "approver_principal", "principal_type", "decision",
            "attestation_ref", "channel", "issued_at", "policy_hash")
OUT_OF_BAND = {"pr_review", "signed_record", "cli_attest"}
PLACEHOLDERS = {"", "TBD", "tbd", "TODO", "N/A", "n/a", "-", "待定", "self"}
AGENT_HINTS = ("agent-", "run-", "bot-", "assistant", "copilot")


class Rejected(Exception):
    pass


class ApprovalAttestationValidator:
    def __init__(self, human_principals, local_policy_hash, audit_path):
        self.humans = set(human_principals)
        self.local = local_policy_hash
        self.audit = AuditLog(audit_path)

    def _reject(self, task_id, reason, **extra):
        self.audit.append("approval.rejected", task_id=task_id,
                          reason=reason, **extra)
        raise Rejected(f"{reason}: {extra}")

    def validate(self, att):
        task_id = att.get("task_id")
        missing = [f for f in REQUIRED if att.get(f) is None]
        if missing:
            self._reject(task_id, "missing_fields", missing=missing)
        for f in REQUIRED:
            v = att.get(f)
            if isinstance(v, str) and v.strip() in PLACEHOLDERS:
                self._reject(task_id, "placeholder_values", field=f)

        principal = att["approver_principal"]
        if att["principal_type"] != "human":
            self._reject(task_id, "non_human_principal",
                         principal_type=att["principal_type"])
        low = principal.lower()
        if any(h in low for h in AGENT_HINTS) or low == "self":
            self._reject(task_id, "agent_impersonating_human", principal=principal)
        if principal not in self.humans:
            self._reject(task_id, "principal_not_allowlisted", principal=principal)

        if att["channel"] not in OUT_OF_BAND:
            self._reject(task_id, "in_band_attestation", channel=att["channel"])
        ref = att["attestation_ref"]
        if not (ref.startswith("https://") or ref.startswith("http://")
                or ref.startswith("urn:")):
            self._reject(task_id, "unverifiable_attestation_ref", ref=ref)
        if att["policy_hash"] != self.local:
            self._reject(task_id, "policy_hash_mismatch")

        self.audit.append("approval.accepted", task_id=task_id,
                          principal=principal, channel=att["channel"])
        return "APPROVED_BY_HUMAN"
