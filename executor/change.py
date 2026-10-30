# -*- coding: utf-8 -*-
"""executor.change —— 策略变更影响评估与活动 Run 处置（CHG-01 / GOV-16）。

规则背景（GOV-16，P0，MUST NOT）：中途出现重大安全热修复时，
必须暂停受影响 Run、撤销旧权限并重授权；**禁止悄悄热替换策略造成证据不一致**。

本模块把这条变成机器判定：

1. 活动 Run 注册表：run_id / task_id / 启动时绑定的 policy_hash / 状态；
2. 发布变更前计算受影响集合：启动策略 ≠ 新策略的活动 Run；
3. 每个受影响 Run 必须有处置决定，四选一：
     continue / pause / reauthorize / terminate
   缺省即 REJECT（失败关闭）；
4. **重大安全热修复（severe=True）不允许 continue**——GOV-16 的核心；
5. reauthorize 必须携带与**新策略一致**的审批证明（approver + policy_hash），
   且审批人不得是该 Run 的 Agent 主体（复用 ATT-01 的"不得自批"直觉）；
6. 全部写审计流，处置决定可追溯。

诚实边界：本模块只强制"变更必须做影响分析并处置活动 Run"这一**流程闭环**，
它不能替代真正的权限撤销/重授权（那是身份服务与权限平面的职责）。
"""
from .audit import AuditLog

ACTIVE = "ACTIVE"
DECISIONS = ("continue", "pause", "reauthorize", "terminate")
AGENT_HINTS = ("agent-", "run-", "bot-", "assistant", "copilot")


class Rejected(Exception):
    pass


class RunRegistry:
    """活动 Run 注册表（最小实现：内存 + 审计流落盘）。"""

    def __init__(self, audit_path):
        self.runs = {}
        self.audit = AuditLog(audit_path)

    def register(self, run_id, task_id, policy_hash, owner="unknown"):
        self.runs[run_id] = {"run_id": run_id, "task_id": task_id,
                             "policy_hash": policy_hash, "owner": owner,
                             "state": ACTIVE}
        self.audit.append("run.registered", run_id=run_id, task_id=task_id,
                          policy_hash=policy_hash)
        return self.runs[run_id]

    def active_runs(self):
        return [r for r in self.runs.values() if r["state"] == ACTIVE]

    def affected_by(self, new_policy_hash):
        return [r for r in self.active_runs() if r["policy_hash"] != new_policy_hash]


class ChangeEvaluator:
    def __init__(self, registry, audit_path):
        self.registry = registry
        self.audit = AuditLog(audit_path)

    def _reject(self, new_hash, reason, **extra):
        self.audit.append("change.rejected", new_policy_hash=new_hash,
                          reason=reason, **extra)
        raise Rejected(f"{reason}: {extra}")

    def evaluate(self, new_policy_hash, decisions, severe=False,
                 change_id="chg-unknown"):
        """decisions: {run_id: "continue"|"pause"|"reauthorize"|"terminate"|(approval dict)}"""
        affected = self.registry.affected_by(new_policy_hash)
        affected_ids = {r["run_id"] for r in affected}

        if not affected:
            self.audit.append("change.published", change_id=change_id,
                              new_policy_hash=new_policy_hash, affected=0)
            return {"result": "PUBLISHED", "affected": [], "decisions": {}}

        missing = sorted(affected_ids - set(decisions))
        if missing:
            self._reject(new_policy_hash, "missing_disposition", runs=missing)

        unknown = {r: d for r, d in decisions.items()
                   if r in affected_ids and
                   (d not in DECISIONS if isinstance(d, str) else False)}
        if unknown:
            self._reject(new_policy_hash, "bad_disposition", bad=unknown)

        for run in affected:
            rid = run["run_id"]
            d = decisions[rid]
            # 取值：可能是字符串，也可能是 {"decision": ..., "approval": {...}}
            if isinstance(d, dict):
                name, approval = d.get("decision"), d.get("approval")
            else:
                name, approval = d, None

            if severe and name == "continue":
                self._reject(new_policy_hash, "severe_change_requires_pause",
                             change_id=change_id, run_id=rid)

            if name == "reauthorize":
                if not isinstance(approval, dict):
                    self._reject(new_policy_hash, "reauthorize_without_approval",
                                 run_id=rid)
                if approval.get("policy_hash") != new_policy_hash:
                    self._reject(new_policy_hash, "reauthorize_policy_mismatch",
                                 run_id=rid, got=approval.get("policy_hash"))
                approver = approval.get("approver") or ""
                if approver.lower() in AGENT_HINTS or any(
                        h in approver.lower() for h in AGENT_HINTS):
                    self._reject(new_policy_hash, "reauthorize_by_agent",
                                 run_id=rid, approver=approver)
                if approver == run.get("owner"):
                    self._reject(new_policy_hash, "reauthorize_self_approval",
                                 run_id=rid, approver=approver)

            self.audit.append("run.disposition", change_id=change_id,
                              run_id=rid, disposition=name,
                              severe=bool(severe))
            if name in ("terminate",):
                run["state"] = "TERMINATED"
            elif name in ("pause",):
                run["state"] = "PAUSED"
            elif name == "reauthorize":
                run["policy_hash"] = new_policy_hash

        self.audit.append("change.published", change_id=change_id,
                          new_policy_hash=new_policy_hash,
                          affected=len(affected))
        return {"result": "PUBLISHED", "affected": sorted(affected_ids),
                "decisions": {r: decisions[r] for r in affected_ids}}


RELEASE_KINDS = ("upgrade", "rollback")


class ModelReleaseEvaluator:
    """模型版本升级与回滚：证据必须绑定具体版本（AUD-017 验收项）。

    规则要点：升级改变了执行者本身，上一版本的证据**不能**为新版本背书。
    因此证据以 (model, version) 为键存放，跨版本复用会直接取不到。
    回滚同样是变更，必须带回滚计划与回滚后的复验证据。
    """

    def __init__(self, audit_path):
        self.audit = AuditLog(audit_path)
        self.evidence = {}      # (model, version) -> {...}
        self.current = {}       # model -> version

    def _verifiable(self, ref):
        if not ref or not isinstance(ref, str):
            return False
        return ref.startswith(("http://", "https://", "urn:")) or len(ref) >= 16

    def register_evidence(self, model, version, evidence_ref,
                          approved_by, evidence_at):
        if not self._verifiable(evidence_ref):
            raise Rejected(f"unverifiable_evidence: {model}@{version}")
        if not approved_by or any(h in approved_by.lower() for h in AGENT_HINTS):
            raise Rejected(f"evidence_must_be_approved_by_human: {model}@{version}")
        self.evidence[(model, version)] = {
            "evidence_ref": evidence_ref, "approved_by": approved_by,
            "evidence_at": evidence_at,
        }
        self.audit.append("model.evidence_registered", model=model,
                          version=version, evidence=evidence_ref)
        return self.evidence[(model, version)]

    def evaluate(self, model, to_version, kind="upgrade", plan_ref=None,
                 actor="unknown"):
        if kind not in RELEASE_KINDS:
            raise Rejected(f"unknown_release_kind: {kind}")
        ev = self.evidence.get((model, to_version))
        if ev is None:
            # 不能用上一个版本的证据给新版本背书
            self.audit.append("model.release_rejected", model=model,
                              to_version=to_version, kind=kind,
                              reason="evidence_not_bound_to_version")
            raise Rejected(f"evidence_not_bound_to_version: {model}@{to_version}")
        if kind == "rollback":
            if not self._verifiable(plan_ref):
                self.audit.append("model.release_rejected", model=model,
                                  to_version=to_version, kind=kind,
                                  reason="rollback_without_plan")
                raise Rejected(f"rollback_without_plan: {model}@{to_version}")
        from_version = self.current.get(model)
        self.current[model] = to_version
        self.audit.append("model.released", model=model, kind=kind,
                          from_version=from_version, to_version=to_version,
                          evidence=ev["evidence_ref"], plan_ref=plan_ref,
                          actor=actor,
                          decision="APPROVED" if kind == "upgrade" else "ROLLED_BACK")
        return {"model": model, "kind": kind, "from": from_version,
                "to": to_version,
                "decision": "APPROVED" if kind == "upgrade" else "ROLLED_BACK",
                "evidence_ref": ev["evidence_ref"]}
