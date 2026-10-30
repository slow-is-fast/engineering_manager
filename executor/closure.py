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

验收断言层（2026-10-30 新增）
------------------------------
`machine_ready` 只看"应答控制是否 tested"，**不读 §四 验收标准原文**。
为此引入 `governance/acceptance_matrix.json`：把每条验收标准分解为可判定断言。
断言类型：``test``（映射到真实存在的用例方法）、``script``（跑仓库内校验脚本，
退出码 0）、``evidence``（证据文件存在且含指定内容）、``manual``（须人工签署）、
``unimplemented``（显式记账"当前无机器覆盖"）。

判定原则（失败关闭）：
- 未在矩阵中出现的问题 → `unmapped`，不得据此宣称验收完成；
- 未知断言类型 → 不满足（不默认放过）；
- 声明 `CLOSED` 但仍有未满足断言或未签署的人工项 → `closure_without_acceptance`，
  与 `unbacked_closure` 同属**记账不实**；
- 人工项即使签了 `signoff`，也只代表"记录在案"，独立复核仍是 EXC-01 的前提。
"""
import subprocess
import sys
from datetime import date

from .gate import (GateInputError, exception_waives, load_exceptions,
                   norm_issue_id, parse_audit_issues)

DEFAULT_TTL = {"P0": 30, "P1": 90, "P2": 180, "_unknown": 30}
OPEN_STATES = ("OPEN", "IN_PROGRESS", "READY_FOR_REVIEW", "REOPENED")
CLAIMED_DONE = ("CLOSED", "ACCEPTED_RISK")
ASSERTION_KINDS = ("test", "script", "evidence", "manual", "unimplemented")
RECURSION_GUARD = ("check_audit_closure",)


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
    def __init__(self, base, now=None, run_scripts=True, script_timeout=300):
        self.base = base
        self.now = now or date.today()
        self.catalog = None
        self.issues = None
        self.exceptions = None
        self.acceptance = None
        self.run_scripts = run_scripts
        self.script_timeout = script_timeout
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
        a = p / "governance" / "acceptance_matrix.json"
        if a.exists():
            self.acceptance = json.loads(a.read_text(encoding="utf-8"))
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

    # ---------------- 验收断言判定（§四 原文 → 可判定断言） ----------------
    def _test_exists(self, ref):
        from pathlib import Path
        if not ref:
            return False
        root = Path(self.base) / "tests"
        if not root.is_dir():
            return False
        needle = f"def {ref}("
        for f in root.rglob("*.py"):
            try:
                if needle in f.read_text(encoding="utf-8", errors="ignore"):
                    return True
            except OSError:
                continue
        return False

    def _evidence_ok(self, rel, contains):
        from pathlib import Path
        if not rel:
            return False, "evidence_path_missing"
        f = Path(self.base) / rel
        if not f.is_file():
            return False, "evidence_missing"
        if contains:
            try:
                if contains not in f.read_text(encoding="utf-8", errors="ignore"):
                    return False, "evidence_content_mismatch"
            except OSError:
                return False, "evidence_unreadable"
        return True, None

    def _script_ok(self, command):
        if not command:
            return False, "script_command_missing"
        if any(g in command for g in RECURSION_GUARD):
            # 防止闭合评估递归调用自己
            return False, "script_recursion_guard"
        cmd = command
        if cmd.startswith("python "):
            cmd = f'"{sys.executable}" ' + cmd[len("python "):]
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(self.base),
                               capture_output=True, text=True,
                               timeout=self.script_timeout)
        except subprocess.TimeoutExpired:
            return False, "script_timeout"
        except OSError:
            return False, "script_unavailable"
        return (r.returncode == 0,
                None if r.returncode == 0 else f"script_exit_{r.returncode}")

    def _assertion_state(self, a):
        kind = a.get("kind")
        st = {"id": a.get("id"), "kind": kind, "text": a.get("text", "")}
        # 未知类型不默认放过（失败关闭）
        if kind not in ASSERTION_KINDS:
            st.update(ok=False, reason="unknown_assertion_kind")
            return st
        if kind == "test":
            ok = self._test_exists(a.get("ref") or "")
            st.update(ok=ok, reason=None if ok else "missing_test_ref",
                      detail=a.get("ref"))
        elif kind == "script":
            if not self.run_scripts:
                st.update(ok=False, reason="script_not_evaluated",
                          detail=a.get("command"))
                return st
            ok, why = self._script_ok(a.get("command") or "")
            st.update(ok=ok, reason=why, detail=a.get("command"))
        elif kind == "evidence":
            ok, why = self._evidence_ok(a.get("path") or "", a.get("contains"))
            st.update(ok=ok, reason=why, detail=a.get("path"))
        elif kind == "unimplemented":
            # 显式记账：当前没有机器覆盖，既不假装满足，也不假装已验证
            st.update(ok=False, reason="not_implemented", detail=a.get("target"))
        else:  # manual
            sign = a.get("signoff") or {}
            signed = bool(sign.get("by") and sign.get("ref") and sign.get("date"))
            st.update(ok=signed, manual=True, signed=signed,
                      reason=None if signed else "manual_pending",
                      human_gate=a.get("human_gate"))
        return st

    def _acceptance_state(self, iid):
        if self.acceptance is None:
            return {"mapped": False, "reason": "acceptance_matrix_missing"}
        rec = (self.acceptance.get("issues") or {}).get(iid)
        if rec is None:
            return {"mapped": False, "reason": "acceptance_unmapped"}
        states = [self._assertion_state(a) for a in (rec.get("assertions") or [])]
        if not states:
            return {"mapped": False, "reason": "no_assertions"}
        unsatisfied = [s for s in states if not s["ok"]]
        return {"mapped": True, "total": len(states),
                "satisfied": len(states) - len(unsatisfied),
                "unsatisfied": unsatisfied,
                "manual_pending": sum(1 for s in states
                                      if s.get("manual") and not s["ok"]),
                "machine_complete": not unsatisfied,
                "assertions": states}

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
            acc = self._acceptance_state(iid)
            status = rec["status"]

            if not controls:
                violations.append({"issue": iid, "reason": "unanswered_issue"})
            if status in CLAIMED_DONE and not machine_ready:
                violations.append({"issue": iid, "reason": "unbacked_closure",
                                   "claimed": status,
                                   "blockers": [b["reason"] for b in blockers]
                                   or ["no_addressing_control"]})
            if status in CLAIMED_DONE and not (acc["mapped"]
                                               and acc["machine_complete"]):
                # §四 验收标准未满足（或分解缺失）就声明关闭 → 记账不实
                violations.append({
                    "issue": iid, "reason": "closure_without_acceptance",
                    "claimed": status,
                    "detail": acc.get("reason"),
                    "blocking": [s.get("id") for s in acc.get("unsatisfied", [])],
                })
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
                        "acceptance": acc,
                        "blockers": blockers,
                        "human_gate": "independent_review" if machine_ready else None}

        acc_issues = [v["acceptance"] for v in out.values()
                      if v["acceptance"].get("mapped")]
        summary = {
            "total": len(out),
            "machine_ready": sum(1 for v in out.values() if v["machine_ready"]),
            "ready_for_review": sum(1 for v in out.values()
                                    if v["suggested"] == "READY_FOR_REVIEW"),
            "claimed_closed": sum(1 for v in out.values()
                                  if v["status"] in CLAIMED_DONE),
            "violations": len(violations),
            "evaluated_at": self.now.isoformat(),
            "acceptance": {
                "available": self.acceptance is not None,
                "issues_mapped": len(acc_issues),
                "issues_unmapped": len(out) - len(acc_issues),
                "assertions_total": sum(a["total"] for a in acc_issues),
                "satisfied": sum(a["satisfied"] for a in acc_issues),
                "manual_pending": sum(a["manual_pending"] for a in acc_issues),
                "issues_machine_complete": sum(1 for a in acc_issues
                                               if a["machine_complete"]),
                "scripts_evaluated": self.run_scripts,
            },
        }
        return {"issues": out, "summary": summary, "violations": violations}

    def assert_no_unbacked_closure(self):
        res = self.evaluate()
        if res["violations"]:
            raise ClosureIntegrityError(
                "; ".join(f"{v['issue']}:{v['reason']}" for v in res["violations"]))
        return res
