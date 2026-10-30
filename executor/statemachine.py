# -*- coding: utf-8 -*-
"""executor.statemachine —— 任务状态机转换矩阵（SMT-01）。

规则（v1.1.1 §5）：AASEGS-WFL 系列要求状态转换有唯一事实源，不允许
"Agent 文字声明即改变状态"。

SMT-01 语义（全部失败关闭）：
  1. **未声明的转换一律拒绝**——转换表是唯一事实源，代码里没有隐式兜底；
  2. **角色受限**：每条转换声明允许的 actor 角色，越权即拒；
  3. **必须证据**：转换声明的 `requires` 必须全部提供，缺一即拒；
  4. **并发覆盖**：带版本号的 CAS，陈旧版本即拒（不静默覆盖）；
  5. **终态不可重开**：终态出发的任何转换都拒绝，包括"人类要求也不行"——
     补偿是**新任务**（`open_compensation`），不是把已关闭任务改回运行；
  6. **解除暂停须授权**：PAUSED 恢复只允许人类治理角色，Agent 不得自行解除；
  7. **逐次记录**：from/to/actor/role/decision/evidence/version 全部落审计。

诚实边界：本模块校验的是"转换是否合规"，不校验证据内容本身是否真实；
`requires` 只保证有引用，不保证引用可核查（可核查性由对应控制负责）。
"""
import json
from pathlib import Path

from .audit import AuditLog

TERMINAL_STATES = ("CLOSED", "CANCELLED")
AGENT_ROLES = ("agent", "run", "service")
HUMAN_GOVERNANCE_ROLES = ("human_owner", "governance_owner", "security_owner")


class TransitionRejected(Exception):
    pass


class ConcurrentOverwrite(TransitionRejected):
    pass


def default_table():
    """AASEGS 试点任务的规范转换表（机器可读，可直接序列化为 JSON）。"""
    return {
        "name": "aasegs.task.v1",
        "states": ["NEW", "RUNNING", "PAUSED", "DELIVERED", "FAILED",
                   "CLOSED", "CANCELLED"],
        "terminal": list(TERMINAL_STATES),
        "transitions": [
            {"from": "NEW", "to": "RUNNING", "roles": ["agent", "human_owner"],
             "requires": ["contract_ref"], "retryable": False},
            {"from": "RUNNING", "to": "PAUSED", "roles": ["agent", "human_owner"],
             "requires": ["pause_reason"], "retryable": False},
            # 解除暂停只允许人类治理角色：Agent 不得自行解除（AUD-007 验收项）
            {"from": "PAUSED", "to": "RUNNING", "roles": list(HUMAN_GOVERNANCE_ROLES),
             "requires": ["resume_authorization"], "retryable": False,
             "pause_release": True},
            {"from": "RUNNING", "to": "DELIVERED", "roles": ["agent", "human_owner"],
             "requires": ["delivery_report"], "retryable": False},
            {"from": "DELIVERED", "to": "CLOSED", "roles": ["human_owner"],
             "requires": ["review_record"], "retryable": False},
            {"from": "DELIVERED", "to": "RUNNING", "roles": ["human_owner"],
             "requires": ["rework_reason"], "retryable": True},
            {"from": "RUNNING", "to": "FAILED", "roles": ["agent", "human_owner"],
             "requires": ["failure_reason"], "retryable": True},
            {"from": "FAILED", "to": "RUNNING", "roles": ["human_owner"],
             "requires": ["remediation_ref"], "retryable": True},
            {"from": "FAILED", "to": "CLOSED", "roles": ["human_owner"],
             "requires": ["review_record"], "retryable": False},
            {"from": "RUNNING", "to": "CANCELLED", "roles": ["human_owner"],
             "requires": ["cancel_reason"], "retryable": False},
            {"from": "PAUSED", "to": "CANCELLED", "roles": ["human_owner"],
             "requires": ["cancel_reason"], "retryable": False},
        ],
    }


class StateMachine:
    def __init__(self, table, audit_path, state_path=None):
        self.table = table
        self.audit = AuditLog(audit_path)
        self.state_path = Path(state_path) if state_path else None
        self.states = set(table["states"])
        self.terminal = set(table.get("terminal") or [])
        self._index = {(t["from"], t["to"]): t for t in table["transitions"]}
        if not self.states:
            raise TransitionRejected("transition table declares no states")

    @classmethod
    def load(cls, table_path, audit_path, state_path=None):
        table = json.loads(Path(table_path).read_text(encoding="utf8"))
        return cls(table, audit_path, state_path)

    # ---- 查询 ----
    def allowed(self, from_state, to_state, role):
        t = self._index.get((from_state, to_state))
        if t is None:
            return False
        return role in t.get("roles", [])

    def transitions_from(self, state):
        return [t for t in self.table["transitions"] if t["from"] == state]

    # ---- 状态仓储（极简：一个 JSON 文件，仅用于并发 CAS 演示） ----
    def _states(self):
        if self.state_path is None:
            return {}
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf8"))

    def _persist(self, d):
        if self.state_path is not None:
            self.state_path.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                                       encoding="utf8")

    def current(self, task_id, initial="NEW"):
        return self._states().get(task_id, {"state": initial, "version": 0})

    # ---- 转换 ----
    def apply(self, task_id, from_state, to_state, actor, role, evidence=None,
              expect_version=None):
        evidence = dict(evidence or {})
        rec = {"task_id": task_id, "from": from_state, "to": to_state,
               "actor": actor, "role": role, "evidence": evidence}

        def reject(reason, **extra):
            payload = {k: v for k, v in rec.items() if k != "task_id"}
            payload.update(extra)        # extra 覆盖同名键，避免重复关键字
            self.audit.append("state.rejected", task_id=task_id, reason=reason,
                              **payload)
            raise TransitionRejected(f"{reason}: {from_state}->{to_state}")

        # 0) 状态必须存在
        if from_state not in self.states or to_state not in self.states:
            reject("unknown_state")
        # 1) 终态不可重开
        if from_state in self.terminal:
            reject("terminal_state_reopen")
        # 2) 未声明的转换一律拒绝（含同态）
        t = self._index.get((from_state, to_state))
        if t is None:
            reject("undeclared_transition")
        # 3) 角色
        if role not in t.get("roles", []):
            if t.get("pause_release") and role in AGENT_ROLES:
                reject("unauthorized_pause_release", role=role)
            reject("role_not_allowed", role=role, allowed=t.get("roles"))
        # 4) 证据
        missing = [k for k in t.get("requires", [])
                   if not evidence.get(k)]
        if missing:
            reject("missing_evidence", missing=missing)
        # 5) 并发 CAS
        store = self._states()
        cur = store.get(task_id, {"state": from_state, "version": 0})
        if cur.get("state") != from_state:
            reject("stale_state", actual=cur.get("state"))
        if expect_version is not None and cur.get("version") != expect_version:
            payload = {k: v for k, v in rec.items() if k != "task_id"}
            self.audit.append("state.rejected", task_id=task_id,
                              reason="concurrent_overwrite",
                              expected=expect_version, actual=cur.get("version"),
                              **payload)
            raise ConcurrentOverwrite(
                f"concurrent_overwrite: {task_id} v{cur.get('version')}")

        store[task_id] = {"state": to_state, "version": cur.get("version", 0) + 1}
        self._persist(store)
        payload = {k: v for k, v in rec.items() if k != "task_id"}
        self.audit.append("state.transition", task_id=task_id, decision="ALLOWED",
                          retryable=t.get("retryable", False), **payload)
        return {"task_id": task_id, "state": to_state,
                "version": store[task_id]["version"],
                "retryable": t.get("retryable", False)}

    # ---- 补偿：新任务，而不是把终态改回去 ----
    def open_compensation(self, of_task_id, reason, actor):
        if not reason or not actor:
            raise TransitionRejected("compensation_needs_reason_and_actor")
        new_id = f"{of_task_id}#comp"
        store = self._states()
        if new_id in store:
            raise TransitionRejected("compensation_already_open")
        store[new_id] = {"state": "NEW", "version": 0,
                         "compensates": of_task_id}
        self._persist(store)
        self.audit.append("state.compensation_opened", task_id=new_id,
                          compensates=of_task_id, actor=actor, reason=reason)
        return {"task_id": new_id, "state": "NEW", "compensates": of_task_id}
