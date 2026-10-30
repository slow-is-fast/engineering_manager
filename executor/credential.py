# -*- coding: utf-8 -*-
"""executor.credential —— 凭证边界策略（CRED-01）。

服务的规则（v1.1 §03-C 信任边界、秘密与工具供应链）：
- AASEGS-SEC-006（P0）：禁止普通 Agent 读取生产凭证、私人 SSH 目录、
  广域云管理员令牌。
- AASEGS-SEC-007（P0）：短期凭证由外部服务签发，禁止作为提示文本或
  普通日志记录；发现即轮换并转事件响应。
- AASEGS-SEC-008（P0）：Agent 不能决定"临时停用"审计/质量检查。

守卫语义（全部失败关闭）：
  1. **主体分类先行**：非人类主体（Agent）对受保护凭证目标的访问一律
     默认拒绝——不论目标分类是否明确，**未分类目标按受保护处理**；
  2. **检测层兜底**：提示文本/日志提交前扫描已知凭证形态
     （fine-grained PAT、经典 PAT/Token、PEM 私钥块、AWS 访问键、
      Slack/Bot Token 等）；命中 → 记 `credential.exposure_detected`，
     且**必须**完成"轮换确认 + 事件登记"两项补救，缺一即失败关闭；
  3. **停用请求一律拒绝**：任何主体经由本守卫请求停用审计/质量检查
     均被拒绝——人类走变更管理（CHG-01），Agent 无此权限（SEC-008）；
  4. 每次拒绝都写审计事件（可告警、可复现），检测事件进入哈希链审计。

诚实边界：形态扫描是**启发式检测**而非穷尽保证——未知形态的凭证
（自造格式、编码/加密变体）不保证被识别；真正的防线是操作系统与
秘密管理层的权限隔离（检测层 ≠ 强制层）。不得据本模块宣称
"凭证不可能泄露"。
"""
import re

from .audit import AuditLog

# 受保护目标分类：普通 Agent 一律不可读
PROTECTED_CLASSES = ("production_credential", "ssh_private", "cloud_admin_token")
UNCLASSIFIED_DEFAULT = "production_credential"   # 未分类按受保护处理

# 已知凭证形态（检测层；非穷尽）
CREDENTIAL_PATTERNS = [
    ("github_finegrained_pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("github_classic_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("pem_private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_bot_token", re.compile(r"\bxox[bapr]-[A-Za-z0-9-]{10,}\b")),
    ("sk_prefixed_secret", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
]

REJECTED_REQUESTS = ("disable_audit", "skip_quality_checks", "suppress_alerts")


class Denied(Exception):
    pass


class CredentialGuard:
    def __init__(self, human_principals, audit_path):
        self.humans = set(human_principals)
        self.audit = AuditLog(audit_path)
        self.exposures = {}   # exposure_id -> remediation state

    # ---- SEC-006：受保护目标的访问控制 ----
    def access(self, principal, principal_type, target):
        """target: {path, classification?}"""
        classification = (target or {}).get("classification") or UNCLASSIFIED_DEFAULT
        if classification in PROTECTED_CLASSES:
            if principal_type != "human" or principal not in self.humans:
                self.audit.append("credential.access_denied",
                                  principal=principal,
                                  principal_type=principal_type,
                                  target=target.get("path"),
                                  classification=classification)
                raise Denied(f"protected_credential_access_denied: "
                             f"{principal}({principal_type}) -> {target.get('path')}")
        self.audit.append("credential.access_allowed", principal=principal,
                          principal_type=principal_type,
                          classification=classification)
        return "ALLOWED"

    # ---- SEC-007：提示文本/日志的凭证形态扫描 ----
    def scan_text(self, text, context):
        """返回命中清单；命中即要求轮换 + 事件登记（见 confirm_remediation）。"""
        hits = []
        for name, pattern in CREDENTIAL_PATTERNS:
            if pattern.search(text or ""):
                hits.append(name)
        if hits:
            import uuid
            exposure_id = "EXP-" + uuid.uuid4().hex[:12]
            self.exposures[exposure_id] = {"exposure_id": exposure_id,
                                           "hits": hits, "context": context,
                                           "rotated": False,
                                           "incident_declared": False}
            self.audit.append("credential.exposure_detected",
                              exposure_id=exposure_id, hits=hits,
                              context=context)
        return hits

    # ---- SEC-007：暴露补救必须闭环（轮换 + 事件登记），缺一即失败关闭 ----
    def confirm_remediation(self, exposure_id, rotated, incident_declared):
        exp = self.exposures.get(exposure_id)
        if exp is None:
            raise Denied(f"unknown_exposure: {exposure_id}")
        if rotated is not True:
            self.audit.append("credential.remediation_rejected",
                              exposure_id=exposure_id, reason="rotation_missing")
            raise Denied(f"rotation_missing: {exposure_id} —— 凭证暴露未确认轮换，失败关闭")
        if incident_declared is not True:
            self.audit.append("credential.remediation_rejected",
                              exposure_id=exposure_id, reason="incident_not_declared")
            raise Denied(f"incident_not_declared: {exposure_id} —— 暴露必须转事件响应")
        exp["rotated"] = True
        exp["incident_declared"] = True
        self.audit.append("credential.remediation_confirmed",
                          exposure_id=exposure_id)
        return "REMEDIATED"

    # ---- SEC-008：停用审计/质量检查的请求一律拒绝 ----
    def request(self, principal, principal_type, action):
        if action in REJECTED_REQUESTS:
            # Agent：无此权限；人类：本守卫不是合法通道，走 CHG-01 变更管理
            reason = ("agent_cannot_suspend_controls"
                      if principal_type != "human"
                      else "wrong_channel_use_change_management")
            self.audit.append("credential.request_rejected",
                              principal=principal,
                              principal_type=principal_type,
                              action=action, reason=reason)
            raise Denied(f"{reason}: {principal} -> {action}")
        self.audit.append("credential.request_processed",
                          principal=principal, action=action)
        return "PROCESSED"
