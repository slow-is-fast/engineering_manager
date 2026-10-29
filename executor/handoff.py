# -*- coding: utf-8 -*-
"""executor.handoff —— 交接契约校验（WF-01 / SMT-01 简化实现）。

规则（v1.1.1 §5 / v1.1 02-C）：
- 交接必须有结构化契约，必需字段缺失即 REJECT；
- policy_hash 缺失或与本地策略不符 → REJECT；
- 消息本身不授予权限：接收方 ACCEPT 后仍需自身有效授权才能行动；
- 终态任务（CLOSED）不得交接。
"""
from .audit import AuditLog

REQUIRED = ("handoff_id", "task_id", "source_run", "destination_role",
            "artifact_manifest", "policy_hash", "validity")
TERMINAL = {"CLOSED"}


class Rejected(Exception):
    pass


class HandoffValidator:
    def __init__(self, local_policy_hash, audit_path):
        self.local = local_policy_hash
        self.audit = AuditLog(audit_path)

    def validate(self, contract, task_state="IMPLEMENTING"):
        missing = [f for f in REQUIRED if contract.get(f) is None]
        if missing:
            self.audit.append("handoff.rejected", handoff_id=contract.get("handoff_id"),
                              reason="missing_fields", missing=missing)
            raise Rejected(f"missing fields: {missing}")
        if contract["policy_hash"] != self.local:
            self.audit.append("handoff.rejected", handoff_id=contract["handoff_id"],
                              reason="policy_hash_mismatch")
            raise Rejected(f"policy_hash mismatch: {contract['policy_hash']}")
        if task_state in TERMINAL:
            self.audit.append("handoff.rejected", handoff_id=contract["handoff_id"],
                              reason="terminal_task")
            raise Rejected(f"task in terminal state {task_state}")
        self.audit.append("handoff.accepted", handoff_id=contract["handoff_id"],
                          task_id=contract["task_id"])
        return "ACCEPT"
