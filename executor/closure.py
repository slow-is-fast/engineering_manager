# -*- coding: utf-8 -*-
"""executor.closure —— 审计问题闭合评估（AUD-001～022 的收口流程）。

依据《AASEGS v1.1 审计问题清单》§二 状态管理：
- `CLOSED` 必须满足全部验收标准，并有可追溯证据；
- `ACCEPTED_RISK` 不等于修复完成，必须记录批准人、范围、补偿控制、
  到期时间与撤销条件；
- **文档修改完成不等于运行时控制问题关闭**。

判定语义（失败关闭）：
  1. 每个问题从控制目录 `addresses` 反查应答控制（目录为唯一事实源）；
  2. `machine_ready` = 所有应答控制均 tested（或持有效例外豁免）**且**
     证据未过期——这只是"控制级证据齐备"，不等于问题可关闭；
  3. 处于 `CLOSED` / `ACCEPTED_RISK` 但 machine_ready 为假 → **记账不实**，
     抛 ClosureIntegrityError（这是本模块存在的首要理由：
     防止"把文档改完就当问题关闭"）；
  4. `ACCEPTED_RISK` 还必须有有效例外登记明确覆盖该问题；
  5. 无应答控制的问题 → 视为未应答，不给出任何"可关闭"建议。

建议状态只到 `READY_FOR_REVIEW`：**关闭结论必须由独立复核给出**
（当前受 EXC-01 约束，第二人类主体不可达）。

诚实边界：本模块判定的是"控制级证据 + 状态声明是否自洽"，
它不读 §四 的验收标准原文，因此**不能**替代逐条验收。
`READY_FOR_REVIEW` 不等于通过验收。
"""
from datetime import date

from .gate import (GateInputError, exception_waives, load_exceptions,
                   norm_issue_id, parse_audit_issues)

DEFAULT_TTL = {"P0": 30, "P1": 90, "P2": 180, "_unknown": 30}
OPEN_STATES = ("OPEN", "IN_PROGRESS", "READY_FOR_REVIEW", "REOPENED")
CLAIMED_DONE = ("CLOSED", "ACCEPTED_RISK")


class ClosureIntegrityError(Exception):
    pass


def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


class ClosureEvaluator:
    def __init__(self, base, now=None):
        self.base = base
        self.now = now or date.today()
        self.catalog = None
        self.issues = None
        self.exceptions = None
        self.ttl = dict(DEFAULT_TTL)

    def load(self):
        from pathlib import Path
        import json
        p = Path(self.base)
        cat = p / "control-catalog.yaml"
        if not cat.exists():
            raise GateInputError("missing required input: control-catalog.yaml")
        self.catalog = json.loads(cat.read_text(encoding="utf-8"))
        self.issues = parse_audit_issues(self.base)
        self.exceptions = load_exceptions(self.base)
        m = p / "governance" / "maturity_matrix.json"
        if m.exists():
            ttl = json.loads(m.read_text(encoding="utf-8")).get("evidence_ttl_days", {})
            self.ttl.update({k: v for k, v in ttl.items() if isinstance(v, int)})
        return self

    # ---------------- 单个应答控制的判定 ----------------
    def _control_state(self, cid):
        c = next((x for x in self.catalog["controls"] if x["id"] == cid), None)
        if c is None:
            return {"control": cid, "ok": False, "reason": "control_not_found"}
        waiver = None
        if not c.get("state", {}).get("tested", False):
            waiver = exception_waives(cid, "tested", self.exceptions, self.now)
            if waiver is None:
                return {"control": cid, "ok": False,
                        "reason": "control_not_tested",
                        "risk_level": c.get("risk_level")}
        if c.get("state", {}).get("tested", False):
            ev = _parse_date(c.get("evidence_at"))
            if ev is None:
                return {"control": cid, "ok": False, "reason": "evidence_unverifiable"}
            ttl = self.ttl.get(c.get("risk_level") or "_unknown", 30)
            age = (self.now - ev).days
            if age > ttl:
                return {"control": cid, "ok": False, "reason": "stale_evidence",
                        "detail": f"age={age}d>{ttl}d"}
        return {"control": cid, "ok": True, "waived_by": waiver}

    # ---------------- 全量评估 ----------------
    def evaluate(self):
        if self.catalog is None:
            self.load()
        out, violations = {}, []
        for iid, rec in sorted(self.issues.items()):
            # 目录写 AASEGS-AUD-001、清单写 AUD-001：归一化后再比对
            controls = [c["id"] for c in self.catalog["controls"]
                        if iid in {norm_issue_id(a) for a in (c.get("addresses") or [])}]
            checks = [self._control_state(cid) for cid in controls]
            blockers = [c for c in checks if not c["ok"]]
            machine_ready = bool(controls) and not blockers
            status = rec["status"]

            if not controls:
                violations.append({"issue": iid, "reason": "unanswered_issue"})
            if status in CLAIMED_DONE and not machine_ready:
                violations.append({"issue": iid, "reason": "unbacked_closure",
                                   "claimed": status,
                                   "blockers": [b["reason"] for b in blockers]
                                   or ["no_addressing_control"]})
            if status == "ACCEPTED_RISK":
                covered = any(
                    iid in e.get("waives", {}).get("audit_issues", [])
                    for e in self.exceptions)
                if not covered:
                    violations.append({"issue": iid,
                                       "reason": "risk_acceptance_without_registration"})

            if status in CLAIMED_DONE:
                suggested = status
            elif machine_ready:
                suggested = "READY_FOR_REVIEW"
            elif status == "IN_PROGRESS":
                suggested = "IN_PROGRESS"
            else:
                suggested = "OPEN"

            out[iid] = {"issue": iid, "severity": rec["severity"],
                        "status": status, "suggested": suggested,
                        "controls": controls, "checks": checks,
                        "machine_ready": machine_ready,
                        "blockers": blockers,
                        "human_gate": "independent_review" if machine_ready else None}

        summary = {
            "total": len(out),
            "machine_ready": sum(1 for v in out.values() if v["machine_ready"]),
            "ready_for_review": sum(1 for v in out.values()
                                    if v["suggested"] == "READY_FOR_REVIEW"),
            "claimed_closed": sum(1 for v in out.values()
                                  if v["status"] in CLAIMED_DONE),
            "violations": len(violations),
            "evaluated_at": self.now.isoformat(),
        }
        return {"issues": out, "summary": summary, "violations": violations}

    def assert_no_unbacked_closure(self):
        res = self.evaluate()
        if res["violations"]:
            raise ClosureIntegrityError(
                "; ".join(f"{v['issue']}:{v['reason']}" for v in res["violations"]))
        return res
