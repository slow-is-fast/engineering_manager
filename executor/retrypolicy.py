# -*- coding: utf-8 -*-
"""executor.retrypolicy —— 破坏性操作的默认不重试策略（REC-02）。

规则：AASEGS-WFL-006（P0，MUST NOT）：**生产数据库破坏性变更不得被默认自动重试**。

语义（失败关闭）：
  1. **未分类操作按破坏性处理**——不认识就当作危险，而不是当作安全；
  2. 破坏性操作**默认不重试**：必须同时具备
       ① 人类重授权（含操作范围引用，Agent 角色不得签发）；
       ② **状态核对**：确认上一次尝试没有产生副作用（`confirmed_no_effect`），
     缺一即拒。没有核对的"重试"就是盲目重放；
  3. 非破坏性操作允许有限重试（默认 3 次），超出即拒；
  4. 每次决策（允许或拒绝）都落审计，含操作、尝试序号、破坏性判定与依据。

诚实边界：本模块决定"能不能重试"，不执行重试本身，也不判断操作是否真的
落在生产库上——那取决于调用方传进来的操作分类；分类错了，策略拦不住。
"""
import hashlib

from .audit import AuditLog

DESTRUCTIVE_OPERATIONS = ("drop_table", "drop_column", "truncate", "delete_rows",
                          "alter_column", "migrate_down", "purge")
# 明确安全的操作：不在这个白名单里、又不在破坏性清单里的**未知操作**，
# 一律按破坏性处理（失败关闭），不能靠"没听说过"换取自由重试。
SAFE_OPERATIONS = ("read_config", "apply_index", "reconcile", "refresh_cache")
AGENT_HINTS = ("agent-", "run-", "bot-", "assistant", "copilot")
MAX_SAFE_ATTEMPTS = 3


class RetryRejected(Exception):
    pass


def _verifiable(ref):
    if not ref or not isinstance(ref, str):
        return False
    return ref.startswith(("http://", "https://", "urn:")) or len(ref) >= 16


class RetryPolicy:
    def __init__(self, audit_path, destructive=None, safe=None,
                 max_safe_attempts=None):
        self.audit = AuditLog(audit_path)
        self.destructive = set(destructive or DESTRUCTIVE_OPERATIONS)
        self.safe = set(safe or SAFE_OPERATIONS)
        self.max_safe_attempts = max_safe_attempts or MAX_SAFE_ATTEMPTS

    def is_destructive(self, operation):
        """未知操作按破坏性处理：没听说过 ≠ 安全。"""
        if not operation:
            return True
        if operation in self.destructive:
            return True
        return operation not in self.safe

    def classify(self, operation):
        return {"operation": operation,
                "declared_destructive": operation in self.destructive,
                "declared_safe": operation in self.safe,
                "treated_destructive": self.is_destructive(operation)}

    def request(self, operation, attempt, approval=None, state_check=None):
        destructive = self.is_destructive(operation)
        base = {"operation": operation, "attempt": attempt,
                "destructive": destructive}

        def reject(reason, **extra):
            self.audit.append("retry.rejected", reason=reason, **base, **extra)
            raise RetryRejected(f"{reason}: {base}")

        if attempt is None or int(attempt) < 1:
            reject("invalid_attempt_number")

        if not destructive:
            if int(attempt) > self.max_safe_attempts:
                reject("retry_budget_exhausted",
                       max_attempts=self.max_safe_attempts)
            self.audit.append("retry.allowed", **base)
            return {"decision": "RETRY_ALLOWED", **base}

        # 破坏性：默认不重试，必须人类重授权 + 状态核对
        if not approval:
            reject("destructive_not_auto_retryable")
        if not isinstance(approval, dict):
            reject("malformed_approval")
        approver = str(approval.get("approver") or "")
        if not approver or any(h in approver.lower() for h in AGENT_HINTS):
            reject("reauthz_by_agent", approver=approver)
        if not _verifiable(approval.get("scope_ref")):
            reject("reauthz_without_scope_ref")
        if approval.get("operation") and approval["operation"] != operation:
            reject("reauthz_scope_mismatch", got=approval["operation"])

        if not state_check:
            reject("state_check_required_before_retry")
        if not isinstance(state_check, dict):
            reject("malformed_state_check")
        if state_check.get("result") != "confirmed_no_effect":
            reject("state_check_not_confirmed",
                   got=state_check.get("result"))
        if not _verifiable(state_check.get("evidence_ref")):
            reject("state_check_evidence_unverifiable")

        digest = hashlib.sha256(
            f"{operation}|{approver}|{approval.get('scope_ref')}|"
            f"{state_check.get('evidence_ref')}".encode("utf8")).hexdigest()[:16]
        self.audit.append("retry.allowed", **base, approver=approver,
                          scope_ref=approval.get("scope_ref"),
                          state_check=state_check.get("evidence_ref"),
                          digest=digest)
        return {"decision": "RETRY_ALLOWED", **base, "approver": approver,
                "digest": digest}
