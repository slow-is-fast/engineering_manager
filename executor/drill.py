# -*- coding: utf-8 -*-
"""executor.drill —— 隔离演练编排（AUD-015-03）。

四类：凭证泄露 / 越权写入 / 审计中断 / 数据暴露。

与既有模块的边界：
  - `incident.py`（INC-01）管**隔离这个动作本身**：要证据保全、要清单非空，
    关闭时要通知/复验/复盘齐备。它回答"这次处置做得对不对"。
  - 本模块管的是**有没有练过**：四类场景是否都跑过一遍、每一步有没有留下
    证据、复盘有没有结论、演练记录有没有过期。它回答"真出事时我们练过吗"。

为什么"演练编排"值得单列一条
--------------------------
只测 `incident.py` 的字段校验，证明的是"处置记录填得规范"；它不能证明
四类场景都演练过。一次都没练过的流程，在真出事时等于没有流程——
而这类缺口平时完全不可见，因为它不会被任何检查点触发。

几条刻意做狠的地方
------------------
  1. **每一步都要证据**。空证据 = 声称做过，等于没做。
  2. **恢复必须被验证过**，不是"我恢复了"。声称恢复而没复验，是最常见的
     自欺：看起来处置完了，实际留了一半。
  3. **复盘必须有结论与待办**。复盘没结论等于没复盘。
  4. **四类缺一不可**。缺一类的演练报告不能算"演练完成"。
  5. **演练记录会过期**（90 天）。练过一次不等于永远练过；过期的记录
     不再计入完成。
  6. **同一场景不许覆盖**。重演要显式开新的记录，否则"再跑一次并覆盖"
     就能把失败的那次抹掉。

诚实边界（重要）
----------------
本模块编排的是**受控模拟演练**。它不编排真实的生产隔离实操——那需要真实
环境、真实凭证隔离与独立值守，不在本模块能力范围内（`AUD-015-04`，manual）。
因此 `env` 只能声明为 `simulated`：把模拟说成生产演练，是比不演练更糟的
欺骗——它会让"我们演练过"这句话失去意义。声称 `production` 一律拒绝。
"""
import time

from .audit import AuditLog

SCENARIOS = ("credential_leak", "unauthorized_write", "audit_outage",
             "data_exposure")
REQUIRED_STEPS = ("containment", "recovery", "postmortem")

ENV_SIMULATED = "simulated"
ENV_PRODUCTION = "production"       # 只用于拒绝，不允许登记

# 演练记录的有效期。练过一次不等于永远练过。
FRESHNESS_DAYS = 90
SECONDS_PER_DAY = 86400

SOURCE = "drill"


class DrillRejected(Exception):
    pass


class DrillOrchestrator:
    def __init__(self, audit_path, now=None):
        self.audit = AuditLog(audit_path)
        self.now = now
        self.records = {}

    def _ts(self):
        return self.now if self.now is not None else time.time()

    # ---- 开演 ----
    def start(self, scenario, env=ENV_SIMULATED, operator=None):
        if scenario not in SCENARIOS:
            raise DrillRejected(f"unknown drill scenario: {scenario}")
        if scenario in self.records:
            # 覆盖会让"上次失败了，再跑一遍"变得看不见。重演要显式开新的。
            raise DrillRejected(
                f"drill already recorded, refusing to overwrite: {scenario}")
        if env != ENV_SIMULATED:
            # 见模块 docstring：模拟就是模拟，不许说成生产演练。
            raise DrillRejected(
                f"only simulated drills can be orchestrated here: env={env!r}")
        if not operator:
            raise DrillRejected(f"drill requires an operator: {scenario}")
        rec = {
            "scenario": scenario,
            "env": ENV_SIMULATED,
            "operator": operator,
            "started_at": self._ts(),
            "steps": {s: None for s in REQUIRED_STEPS},
            "status": "OPEN",
            "closed_at": None,
        }
        self.records[scenario] = rec
        self.audit.append_from(SOURCE, "drill.started", scenario=scenario,
                               env=ENV_SIMULATED, operator=operator)
        return dict(rec)

    # ---- 逐步记录 ----
    def record_step(self, scenario, step, evidence=None, verified=False,
                    findings=None, actions=None, by=None):
        if scenario not in self.records:
            raise DrillRejected(f"drill not started: {scenario}")
        if step not in REQUIRED_STEPS:
            raise DrillRejected(f"unknown drill step: {step}")
        if not by:
            raise DrillRejected(f"step requires an actor: {scenario}/{step}")
        rec = self.records[scenario]
        if rec["steps"][step] is not None:
            raise DrillRejected(
                f"step already recorded: {scenario}/{step}")

        evidence = evidence or []
        if not evidence:
            # 没有证据的步骤 = 声称做过。处置记录里最不值钱的就是"我做了"。
            raise DrillRejected(
                f"step requires evidence (empty evidence means it was only "
                f"claimed): {scenario}/{step}")

        entry = {"by": by, "at": self._ts(), "evidence": list(evidence)}
        if step == "recovery":
            # "恢复了"与"验证过恢复了"是两件事。没复验的恢复不算恢复。
            if not verified:
                raise DrillRejected(
                    f"recovery must be verified, not just claimed: {scenario}")
            entry["verified"] = True
        if step == "postmortem":
            # 复盘没结论 = 没复盘。只写"已复盘"三个字不算。
            if not findings or not actions:
                raise DrillRejected(
                    f"postmortem requires findings and actions: {scenario}")
            entry["findings"] = list(findings)
            entry["actions"] = list(actions)

        rec["steps"][step] = entry
        self.audit.append_from(SOURCE, f"drill.{step}", scenario=scenario,
                               by=by, evidence_count=len(evidence))
        return dict(entry)

    # ---- 收口 ----
    def close(self, scenario):
        rec = self.records.get(scenario)
        if rec is None:
            raise DrillRejected(f"drill not started: {scenario}")
        missing = [s for s in REQUIRED_STEPS if rec["steps"][s] is None]
        if missing:
            raise DrillRejected(
                f"drill cannot close, steps missing: {scenario} -> {missing}")
        rec["status"] = "CLOSED"
        rec["closed_at"] = self._ts()
        self.audit.append_from(SOURCE, "drill.closed", scenario=scenario)
        return dict(rec)

    # ---- 汇总 ----
    def summary(self, now=None):
        """四类齐备且未过期才算完成。"""
        at = now if now is not None else self._ts()
        done, missing, stale = [], [], []
        for s in SCENARIOS:
            rec = self.records.get(s)
            if rec is None or rec["status"] != "CLOSED":
                missing.append(s)
                continue
            age = (at - rec["closed_at"]) / SECONDS_PER_DAY
            if age > FRESHNESS_DAYS:
                stale.append({"scenario": s, "age_days": round(age, 2)})
            else:
                done.append(s)
        return {"complete": not missing and not stale,
                "done": done, "missing": missing, "stale": stale,
                "freshness_days": FRESHNESS_DAYS}

    def require_complete(self, now=None):
        """完成才返回；缺一类、或记录过期，都抛异常（失败关闭）。"""
        s = self.summary(now=now)
        if not s["complete"]:
            why = s["missing"] or [f"{x['scenario']}({x['age_days']}d)"
                                   for x in s["stale"]]
            raise DrillRejected(
                f"isolation drills incomplete: {why}")
        return s
