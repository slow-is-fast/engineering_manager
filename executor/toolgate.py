# -*- coding: utf-8 -*-
"""executor.toolgate —— 工具能力准入矩阵（TOOL-01）。

规则的来源（v1.1.1 §3 工具能力准入 / AUD-005）：
- 每工具/模型版本必须有**能力清单**，并标明 `enforced` / `advisory` /
  `unsupported`，附验证来源与证据时间；
- **关键能力缺失、仅 advisory 或证据过期时拒绝准入，或降低允许的风险等级**；
- 静态清单不能替代运行时验收。

能力与风险的对应（矩阵内置，可审计）：
  R0/R1 必需：read_scope、write_isolation、audit、termination
  R2 追加：authz_check、credential_isolation
  R3 追加：network_boundary、reviewer_independence、trusted_ci

语义（失败关闭）：
  1. 未登记的工具/版本 → 拒绝（未知即不可准入）；
  2. 任一必需能力不是 `enforced`（缺失/仅 advisory）→ **该风险等级不可准入**，
     但可能仍可准入更低等级（"降低允许的风险等级"而非一票全否）；
  3. 证据过期（默认 90 天）→ 视为能力不可信，按同上规则降级；
  4. 返回允许的最高风险等级，调用方必须使用该上限而不是自行声明。

诚实边界：矩阵判定的是**清单声明与证据时效**；它不验证声明的真实性
（那需要运行时探测与独立复核）。不得据本模块宣称"工具已可信"。
"""
from datetime import date

from .audit import AuditLog

RISKS = ("R0", "R1", "R2", "R3")
SEVERITY = {r: i for i, r in enumerate(RISKS)}

REQUIRED_CAPABILITIES = {
    "R0": {"read_scope", "audit", "termination"},
    "R1": {"read_scope", "write_isolation", "audit", "termination"},
    "R2": {"read_scope", "write_isolation", "audit", "termination",
           "authz_check", "credential_isolation"},
    "R3": {"read_scope", "write_isolation", "audit", "termination",
           "authz_check", "credential_isolation", "network_boundary",
           "reviewer_independence", "trusted_ci"},
}

EVIDENCE_TTL_DAYS = 90
CAPABILITY_STATES = ("enforced", "advisory", "unsupported")


class Denied(Exception):
    pass


def _parse(d):
    try:
        return date.fromisoformat(str(d)[:10])
    except (TypeError, ValueError):
        return None


class ToolGate:
    def __init__(self, audit_path, now=None):
        self.audit = AuditLog(audit_path)
        self.now = now or date.today()
        self.manifest = {}

    def register(self, tool, version, capabilities, evidence_at=None,
                 verified_against=None):
        for cap, state in capabilities.items():
            if state not in CAPABILITY_STATES:
                raise Denied(f"bad_capability_state: {cap}={state}")
        self.manifest[(tool, version)] = {
            "tool": tool, "version": version,
            "capabilities": dict(capabilities),
            "evidence_at": evidence_at,
            "verified_against": verified_against,
        }
        self.audit.append("tool.registered", tool=tool, version=version,
                          evidence_at=evidence_at)
        return self.manifest[(tool, version)]

    def _evidence_fresh(self, entry):
        ev = _parse(entry.get("evidence_at"))
        if ev is None:
            return False, "evidence_missing"
        age = (self.now - ev).days
        if age > EVIDENCE_TTL_DAYS:
            return False, f"evidence_stale({age}d>{EVIDENCE_TTL_DAYS}d)"
        return True, None

    def max_admissible_risk(self, tool, version):
        """在能力清单与证据时效约束下，允许的最高风险等级（None = 不可准入）。"""
        entry = self.manifest.get((tool, version))
        if entry is None:
            return None, ["unregistered_tool_version"]
        fresh, why = self._evidence_fresh(entry)
        caps = entry["capabilities"]
        reasons, allowed = [], None

        if not fresh:
            # 证据过期：所有等级视为能力不可信
            return None, [why]

        for risk in RISKS:
            missing = [c for c in REQUIRED_CAPABILITIES[risk]
                       if caps.get(c) != "enforced"]
            if missing:
                reasons.append({risk: [f"{c}={caps.get(c, 'missing')}"
                                       for c in missing]})
                break
            allowed = risk
        return allowed, reasons

    def admit(self, tool, version, requested_risk):
        requested_risk = str(requested_risk).upper()
        if requested_risk not in RISKS:
            raise Denied(f"unknown_risk_level: {requested_risk}")
        allowed, reasons = self.max_admissible_risk(tool, version)
        if allowed is None or SEVERITY[requested_risk] > SEVERITY[allowed]:
            self.audit.append("tool.admission_denied", tool=tool,
                              version=version, requested=requested_risk,
                              allowed=allowed, reasons=reasons)
            raise Denied(f"tool_admission_denied: {tool}@{version} "
                         f"requested={requested_risk} allowed={allowed} "
                         f"reasons={reasons}")
        self.audit.append("tool.admission_granted", tool=tool,
                          version=version, requested=requested_risk,
                          allowed=allowed)
        return {"decision": "ALLOW", "requested": requested_risk,
                "max_allowed": allowed}
