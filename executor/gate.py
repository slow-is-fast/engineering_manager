# -*- coding: utf-8 -*-
"""executor.gate —— 成熟度等级与风险等级准入判定（GATE-01 / AUD-020）。

规则（v1.1.1 §12 准入门槛 / 00-总纲 F 上线成熟度 / AASEGS-AUD-020）：
- G0–G4 与 R0–R3 的准入由**机器可判定的合取条件**决定；
- **任一未关闭 P0 问题阻止对应风险等级准入**；
- **门槛判定不可由文档声明替代**。

判定器语义：
  1. 输入缺失（等级矩阵、控制目录、规则注册表、审计清单）→ 失败关闭，抛 GateInputError；
  2. 事实源冲突（同一审计问题在 §四 与 §二·A 严重程度不一致）→ 失败关闭；
     不"任选其一"，因为那会让门槛建立在不确定输入上；
  3. 控制未 tested / 未 verified / 证据过期 / 缺 evidence_at → 计入 blockers；
  4. 风险例外只有同时满足「人类批准人 + 未过期 + 有补偿控制 + 有撤销条件 +
     waives 覆盖该目标 + requirement 类别匹配」才予采信；否则一律不豁免；
  5. `unwaivable`（GATE-01）永不被豁免——判定器不得被自己的豁免关掉；
  6. R2/R3 需逐案评审，且逐案评审**不降低等级门槛**，只在其上追加个案批准；
  7. 未知风险等级、未知等级名、缺 case_review → 拒绝。

诚实边界：本模块判定的是**治理账本自身的完整性与新鲜度**，条件取值来自仓库自报的
状态字段。它不评估执行器在真实生产环境的部署，也不构成第三方背书（EXC-02）。
tested 不等于 verified：只有 G4 要求 verified。
"""
import json
import re
from datetime import date
from pathlib import Path

from .audit import AuditLog

LEVELS = ("G0", "G1", "G2", "G3", "G4")
RISKS = ("R0", "R1", "R2", "R3")

# 审计问题状态：视为"仍未关闭、阻断准入"的状态
OPEN_STATES = ("OPEN", "IN_PROGRESS", "READY_FOR_REVIEW", "REOPENED")

CATALOG_REQUIRED = {"id", "requirement_ref", "owner", "enforcer", "evidence",
                    "failure", "test", "status", "integration_evidence_uri"}


class GateInputError(Exception):
    """输入不可用或自相矛盾。失败关闭：不得给出准入结论。"""
    pass


class AdmissionDenied(Exception):
    pass


def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


class AdmissionGate:
    def __init__(self, base, now=None, audit_path=None):
        self.base = Path(base)
        self.now = now or date.today()
        self.audit = AuditLog(audit_path) if audit_path else None
        self.matrix = None
        self.catalog = None
        self.rules = None
        self.issues = {}          # id -> {severity, status}
        self.exceptions = []      # 原始例外记录
        self.expires_note = []

    # ---------------- 加载（任一失败即失败关闭） ----------------
    def load(self):
        self.matrix = self._load_json("governance/maturity_matrix.json")
        self.catalog = self._load_json("control-catalog.yaml")
        self.rules = self._load_json("rule-registry.json")
        # 注册表是必填输入：门槛必须与规则体系同源，缺规则即输入故障（失败关闭）
        if not (isinstance(self.rules, dict) and self.rules.get("rules")):
            raise GateInputError("rule-registry.json: no rules found")
        self.issues = self._parse_audit_issues()
        self.exceptions = self._load_exceptions()
        if not isinstance(self.matrix.get("levels"), dict):
            raise GateInputError("maturity_matrix: missing levels")
        for lv in self.matrix["levels"]:
            if lv not in LEVELS:
                raise GateInputError(f"maturity_matrix: unknown level {lv}")
        for rk in self.matrix.get("risk_admission", {}):
            if rk not in RISKS:
                raise GateInputError(f"maturity_matrix: unknown risk {rk}")
        return self

    def _load_json(self, rel):
        p = self.base / rel
        if not p.exists():
            raise GateInputError(f"missing required input: {rel}")
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise GateInputError(f"unparseable input {rel}: {exc}")

    def _load_exceptions(self):
        """例外登记是可选的：缺失时按"无例外"处理（更严），但不算输入故障。"""
        p = self.base / "governance" / "exception_register.json"
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise GateInputError(f"unparseable exception_register.json: {exc}")
        return data.get("exceptions", [])

    def _parse_audit_issues(self):
        """§四 逐项登记 = 严重程度的权威源；§二·A = 状态源；§12.1 映射表 = 第三处引用。

        三处对同一问题给出不同严重程度时一律**失败关闭**：不任选其一，
        因为那会让门槛建立在不确定输入上（这正是纯文档流程长期未发现的缺陷）。
        """
        p = self.base / "AASEGS_Audit_Issues_Full.md"
        if not p.exists():
            raise GateInputError("missing required input: AASEGS_Audit_Issues_Full.md")
        text = p.read_text(encoding="utf-8")

        # --- §四：严重程度（权威） ---
        sec4 = text.split("## 四、逐项问题登记")[-1]
        severity = {}
        for block in re.split(r"\n###\s+", sec4):
            m = re.match(r"AASEGS-AUD-(\d{3})", block)
            if not m:
                continue
            sev = re.search(r"严重程度[^\n]*?(P[012])", block)
            if sev:
                severity["AUD-" + m.group(1)] = sev.group(1)

        # --- §二·A：状态（兼第二处严重程度） ---
        status = {}
        if "二·A" in text:
            secA = text.split("二·A")[-1].split("## 三")[0]
            for line in secA.splitlines():
                m = re.match(r"\s*\|\s*(AUD-\d{3})\s*\|\s*(P[012])\s*\|\s*([A-Z_]+)", line)
                if m:
                    status[m.group(1)] = (m.group(2), m.group(3))

        # --- §12.1：实施完整性修订版中的映射表（第三处严重程度） ---
        alt = {}
        fp = self.base / "AASEGS_v1.1.1_实施完整性修订版.md"
        if fp.exists():
            ftext = fp.read_text(encoding="utf-8")
            if "### 12.1" in ftext:
                sec12 = ftext.split("### 12.1")[-1].split("### 12.2")[0]
                for line in sec12.splitlines():
                    m = re.match(r"\s*\|\s*(AUD-\d{3})\s*\|\s*(P[012])\s*\|", line)
                    if m:
                        alt[m.group(1)] = m.group(2)

        if not severity:
            raise GateInputError("audit issues: no severity parsed from §四")
        if not status:
            raise GateInputError("audit issues: no status parsed from §二·A")

        conflicts = []
        for iid, (sev_a, st) in sorted(status.items()):
            sev4 = severity.get(iid)
            if sev4 and sev4 != sev_a:
                conflicts.append({"issue": iid, "source": "§二·A",
                                  "authoritative": sev4, "found": sev_a})
            if sev4 and alt.get(iid) and alt[iid] != sev4:
                conflicts.append({"issue": iid, "source": "§12.1",
                                  "authoritative": sev4, "found": alt[iid]})
        if conflicts:
            raise GateInputError(
                "audit issue severity conflict (authoritative source = §四 逐项问题登记): "
                + ", ".join(f"{c['issue']}({c['source']}={c['found']} vs §四={c['authoritative']})"
                            for c in conflicts))

        return {iid: {"severity": severity[iid], "status": st}
                for iid, (sev, st) in status.items() if iid in severity}

    # ---------------- 控制状态 ----------------
    def _controls(self):
        return self.catalog.get("controls", [])

    def _by_id(self):
        return {c["id"]: c for c in self._controls()}

    def _ttl(self, control):
        ttl = self.matrix.get("evidence_ttl_days", {})
        lvl = control.get("risk_level")
        if lvl in ttl:
            return ttl[lvl]
        return ttl.get("_unknown", 30)

    def _exception_covers(self, cid, requirement):
        """返回采信该豁免的例外 ID，否则 None。"""
        unwaivable = set(self.matrix.get("evaluation_model", {}).get("unwaivable", []))
        if cid in unwaivable:
            return None
        for e in self.exceptions:
            if not self._exception_valid(e):
                continue
            w = e.get("waives", {})
            if cid not in w.get("controls", []):
                continue
            reqs = w.get("requirement") or ["tested"]
            if requirement not in reqs:
                continue
            return e["id"]
        return None

    def _exception_valid(self, e):
        if str(e.get("status", "ACTIVE")).upper() != "ACTIVE":
            return False
        if not e.get("approver") or e.get("approver_type") != "human":
            return False
        exp = _parse_date(e.get("expires"))
        if exp is None or exp <= self.now:
            return False
        if not e.get("compensating_controls"):
            return False
        if not e.get("revocation"):
            return False
        if not e.get("waives", {}).get("controls"):
            return False
        return True

    def _check_control(self, cid, requirement, require_fresh):
        """返回 (blocker_or_None, waiver_id_or_None)。

        豁免语义：例外只豁免**它声明的那一项要求**（tested 或 verified）。
        被豁免后不再对同一项做二次判定；但控制只要**自称 tested**，就必须有
        可新鲜度校验的 evidence_at——证据新鲜度不受豁免（RVF-01 独立约束）。
        """
        c = self._by_id().get(cid)
        if c is None:
            return ({"type": "control", "id": cid, "reason": "missing_control",
                     "detail": "control listed in maturity matrix but absent from catalog"},
                    None)
        st = c.get("state", {})
        waiver = None
        if not st.get(requirement, False):
            waiver = self._exception_covers(cid, requirement)
            if waiver is None:
                return ({"type": "control", "id": cid,
                         "reason": f"control_not_{requirement}",
                         "risk_level": c.get("risk_level"),
                         "detail": f"state.{requirement} is false and no valid exception covers it"},
                        None)
        if require_fresh and st.get("tested", False):
            ev = _parse_date(c.get("evidence_at"))
            if ev is None:
                return ({"type": "control", "id": cid, "reason": "evidence_unverifiable",
                         "risk_level": c.get("risk_level"),
                         "detail": "tested control without evidence_at cannot be freshness-checked"},
                        waiver)
            ttl = self._ttl(c)
            age = (self.now - ev).days
            if age > ttl:
                return ({"type": "control", "id": cid, "reason": "stale_evidence",
                         "risk_level": c.get("risk_level"),
                         "detail": f"evidence_at={c.get('evidence_at')} age={age}d exceeds TTL={ttl}d"},
                        waiver)
        return (None, waiver)

    # ---------------- 输入完整体 ----------------
    def _catalog_schema_valid(self):
        for c in self._controls():
            if not CATALOG_REQUIRED <= set(c.keys()):
                return False
            if not (c.get("state") or {}):
                return False
        return True

    def _ci_gate_present(self):
        wf = self.base / ".github" / "workflows" / "governance.yml"
        if not wf.exists():
            return False
        body = wf.read_text(encoding="utf-8", errors="ignore")
        return "validate_controls.py" in body

    # ---------------- 等级判定 ----------------
    def _open_issues(self, severities=None):
        out = []
        for iid, rec in sorted(self.issues.items()):
            if rec["status"] not in OPEN_STATES:
                continue
            if severities and rec["severity"] not in severities:
                continue
            if self._exception_covers_issue(iid):
                continue
            out.append({"type": "issue", "id": iid, "reason": "open_issue",
                        "severity": rec["severity"], "status": rec["status"]})
        return out

    def _exception_covers_issue(self, iid):
        for e in self.exceptions:
            if not self._exception_valid(e):
                continue
            if iid in e.get("waives", {}).get("audit_issues", []):
                return True
        return False

    def _eval_level(self, lv):
        crit = self.matrix["levels"].get(lv, {}).get("criteria", {}) or {}
        blockers, waivers = [], []
        require_fresh = bool(crit.get("require_fresh_evidence", True))

        if crit.get("catalog_schema_valid") and not self._catalog_schema_valid():
            blockers.append({"type": "input", "id": "control-catalog.yaml",
                             "reason": "catalog_schema_invalid"})
        if crit.get("ci_gate_present") and not self._ci_gate_present():
            blockers.append({"type": "input", "id": ".github/workflows/governance.yml",
                             "reason": "ci_gate_missing"})

        for cid in crit.get("controls_tested", []) or []:
            b, w = self._check_control(cid, "tested", require_fresh)
            if b:
                blockers.append(b)
            if w:
                waivers.append({"control": cid, "requirement": "tested", "by": w, "level": lv})

        for flag, req in (("all_p0_controls_tested", "tested"),
                          ("all_p1_controls_tested", "tested"),
                          ("all_p0_controls_verified", "verified")):
            if not crit.get(flag):
                continue
            want = "P0" if "p0" in flag else "P1"
            for c in self._controls():
                if c.get("risk_level") != want:
                    continue
                b, w = self._check_control(c["id"], req, require_fresh)
                if b:
                    blockers.append(b)
                if w:
                    waivers.append({"control": c["id"], "requirement": req, "by": w, "level": lv})

        if crit.get("max_open_p0_issues") is not None:
            op = self._open_issues(("P0",))
            if len(op) > crit["max_open_p0_issues"]:
                blockers.extend(op)
        if crit.get("max_open_p1_issues") is not None:
            op = self._open_issues(("P1",))
            if len(op) > crit["max_open_p1_issues"]:
                blockers.extend(op)
        if crit.get("max_open_issues_total") is not None:
            op = self._open_issues()
            if len(op) > crit["max_open_issues_total"]:
                blockers.extend(op)

        if crit.get("max_active_exceptions") is not None:
            active = [e for e in self.exceptions if self._exception_valid(e)]
            if len(active) > crit["max_active_exceptions"]:
                for e in active:
                    blockers.append({"type": "exception", "id": e["id"],
                                     "reason": "active_exception_over_limit"})

        return {"level": lv,
                "title": self.matrix["levels"].get(lv, {}).get("title"),
                "satisfied": not blockers,
                "blockers": blockers,
                "waivers": waivers}

    def evaluate(self):
        """累积式判定：返回达到的最高等级与逐等级结果。"""
        if self.matrix is None:
            self.load()
        results, reached = [], "G0"
        for lv in LEVELS:
            if lv not in self.matrix["levels"]:
                continue
            r = self._eval_level(lv)
            results.append(r)
            if not r["satisfied"]:
                break
            reached = lv
        blockers = [b for r in results if not r["satisfied"] for b in r["blockers"]]
        waivers = [w for r in results for w in r["waivers"]]
        return {"level": reached, "levels": results, "blockers": blockers,
                "waivers": waivers, "evaluated_at": self.now.isoformat()}

    # ---------------- 准入判定 ----------------
    def admit(self, risk, case_review=None):
        if self.matrix is None:
            self.load()
        risk = str(risk).upper()
        spec = self.matrix.get("risk_admission", {}).get(risk)
        if spec is None:
            raise AdmissionDenied(f"unknown_risk_level: {risk}")

        asmt = self.evaluate()
        required = spec["min_level"]
        idx_req, idx_got = LEVELS.index(required), LEVELS.index(asmt["level"])

        # 只取"所需等级及以下"的阻断项：达到 G3 时，G4 的未完成项
        # 不应阻断一个只要求 G2 的 R0 申请（否则门槛永远拒绝）。
        relevant = [r for r in asmt["levels"]
                    if LEVELS.index(r["level"]) <= idx_req]
        blockers = [b for r in relevant for b in r["blockers"]]
        waivers = [w for r in relevant for w in r["waivers"]]
        reasons = []
        if idx_got < idx_req:
            reasons.append(f"level_insufficient: required>={required}, actual={asmt['level']}")

        if spec.get("case_review"):
            if not isinstance(case_review, dict):
                reasons.append("case_review_required: missing case review record")
                blockers.append({"type": "process", "id": "case_review",
                                 "reason": "case_review_missing"})
            else:
                if not case_review.get("approval_ref"):
                    blockers.append({"type": "process", "id": "case_review",
                                     "reason": "case_review_missing_approval_ref"})
                    reasons.append("case_review_required: missing approval_ref")
                if not case_review.get("approver") or case_review.get("principal_type") != "human":
                    blockers.append({"type": "process", "id": "case_review",
                                     "reason": "case_review_not_human"})
                    reasons.append("case_review_required: approver must be a human principal")

        decision = "DENY" if (reasons or blockers) else "ALLOW"
        out = {"decision": decision, "risk": risk, "required_level": required,
               "actual_level": asmt["level"], "reasons": reasons,
               "blockers": blockers, "waivers": waivers,
               "evaluated_at": asmt["evaluated_at"]}
        if self.audit:
            self.audit.append("admission.decision", risk=risk, decision=decision,
                              required_level=required, actual_level=asmt["level"],
                              blockers=len(blockers))
        return out
