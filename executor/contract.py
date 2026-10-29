# -*- coding: utf-8 -*-
"""executor.contract —— 任务契约与交付报告要素校验（WF-03 / WF-04）。

对应规则：
- AASEGS-WFL-001（02-工作流治理 B）：任务必须含 ID、Owner、风险、目标、
  准入/排除范围、可测验收、依赖、预算、失败策略、批准证明。
- AASEGS-WFL-002（02-工作流治理 B）：交付报告必须含任务 ID、运行 ID、
  变更摘要、路径、测试、CI、提交 SHA、Review 结论、已知风险、批准/例外、
  结案结果。

失败关闭：任何必需字段缺失、占位或语义不合法，一律 REJECT 并写审计。
注意：`not value` 会把空列表/空串与"缺失"混为一谈，本模块统一用
`value is None` 判定缺失，再用独立规则判定占位值（历史 bug 见 T-WF-02 相关记录）。
"""
import re

from .audit import AuditLog

# ---- AASEGS-WFL-001：任务契约要素 ----
TASK_REQUIRED = (
    "task_id", "owner", "risk_level", "objective", "in_scope",
    "out_of_scope", "acceptance_criteria", "dependencies", "budget",
    "failure_policy", "approval_proof",
)
RISK_LEVELS = {"R0", "R1", "R2", "R3"}
PLACEHOLDERS = {"", "TBD", "tbd", "TODO", "N/A", "n/a", "-", "待定"}

# ---- AASEGS-WFL-002：交付报告要素 ----
DELIVERY_REQUIRED = (
    "task_id", "run_id", "change_summary", "paths", "tests", "ci",
    "commit_sha", "review_verdict", "known_risks", "approval_or_exception",
    "closure_result",
)
CLOSURE_RESULTS = {"CLOSED", "COMPENSATED", "MANUAL_REMEDIATION_REQUIRED",
                   "STOPPED", "COMPENSATING"}
SHA_RE = re.compile(r'^[0-9a-f]{7,40}$')


class Rejected(Exception):
    pass


def _missing(payload, required):
    return [f for f in required if payload.get(f) is None]


def _placeholder_hits(payload, required):
    hits = []
    for f in required:
        v = payload.get(f)
        if isinstance(v, str) and v.strip() in PLACEHOLDERS:
            hits.append(f)
    return hits


class TaskContractValidator:
    """WF-03：READY_FOR_APPROVAL 准入检查。"""

    def __init__(self, audit_path):
        self.audit = AuditLog(audit_path)

    def _reject(self, task_id, reason, **extra):
        self.audit.append("task_contract.rejected", task_id=task_id,
                          reason=reason, **extra)
        raise Rejected(f"{reason}: {extra}")

    def validate(self, contract):
        task_id = contract.get("task_id")
        missing = _missing(contract, TASK_REQUIRED)
        if missing:
            self._reject(task_id, "missing_fields", missing=missing)
        placeholders = _placeholder_hits(contract, TASK_REQUIRED)
        if placeholders:
            self._reject(task_id, "placeholder_values", fields=placeholders)
        if contract["risk_level"] not in RISK_LEVELS:
            self._reject(task_id, "bad_risk_level", risk=contract["risk_level"])

        proof = contract["approval_proof"]
        if not isinstance(proof, dict):
            self._reject(task_id, "bad_approval_proof")
        for k in ("approver", "policy_hash", "expires_at"):
            if proof.get(k) is None:
                self._reject(task_id, "incomplete_approval_proof", missing=k)
        # GOV-17 / AGT-001：不得由提交方自己批准（作者不能自批）
        if proof.get("approver") == contract.get("owner"):
            self._reject(task_id, "self_approval", approver=proof.get("approver"))

        self.audit.append("task_contract.accepted", task_id=task_id,
                          risk=contract["risk_level"])
        return "READY_FOR_APPROVAL"


class DeliveryReportValidator:
    """WF-04：结案交付报告要素检查。"""

    def __init__(self, audit_path):
        self.audit = AuditLog(audit_path)

    def _reject(self, task_id, reason, **extra):
        self.audit.append("delivery_report.rejected", task_id=task_id,
                          reason=reason, **extra)
        raise Rejected(f"{reason}: {extra}")

    def validate(self, report):
        task_id = report.get("task_id")
        missing = _missing(report, DELIVERY_REQUIRED)
        if missing:
            self._reject(task_id, "missing_fields", missing=missing)
        placeholders = _placeholder_hits(report, DELIVERY_REQUIRED)
        if placeholders:
            self._reject(task_id, "placeholder_values", fields=placeholders)
        if not SHA_RE.match(report["commit_sha"]):
            self._reject(task_id, "bad_commit_sha", sha=report["commit_sha"])
        if report["closure_result"] not in CLOSURE_RESULTS:
            self._reject(task_id, "bad_closure_result",
                         result=report["closure_result"])
        # 空列表是合法值（无已知风险），但缺失不是
        if not isinstance(report["known_risks"], list):
            self._reject(task_id, "bad_known_risks")
        self.audit.append("delivery_report.accepted", task_id=task_id,
                          run_id=report["run_id"])
        return "DELIVERED"
