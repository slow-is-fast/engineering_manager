# -*- coding: utf-8 -*-
"""executor.remote —— 远端能力协商与漂移/补偿失败处置（AUD-009-03 / AUD-010-03）。

与既有模块的边界（避免重复计费）：
  - `ledger.py`（EFF-01）管**我方台账**：我知不知道这个操作的结果。
    → 它假设"可以去对账"。
  - 本模块管**远端能不能配合**：对账这个动作本身是否可行。
    → 补的正是 EFF-01 没覆盖的那一半：目标系统不支持幂等、且查询不可用。
  - `retrypolicy.py`（REC-02）管**破坏性操作能不能重试**（人类重授权 + 状态核对）。
    → 它的 `state_check` 需要一个核对结论，本模块的 `reconcile` 正好提供它。
    能力不足时连"重试"这个选项都不该出现，直接人工。

决策表（失败关闭：未登记的系统按最保守处理）：

  | 幂等支持 | 查询可用 | 决策                            |
  |---------|---------|--------------------------------|
  | key     | *       | REPLAY_WITH_KEY（可安全重放）      |
  | none    | yes     | RECONCILE_FIRST（先查真实状态）    |
  | none    | no      | MANUAL_REMEDIATION_REQUIRED      |
  | 未登记   | -       | MANUAL_REMEDIATION_REQUIRED      |

漂移与补偿：
  - 远端实际状态与预期不符 → DRIFT_DETECTED，禁止基于旧快照继续恢复
  - 补偿操作失败或部分成功 → MANUAL_REMEDIATION_REQUIRED，不得静默重试，
    也**不得当作已补偿**继续推进

诚实边界：本模块做的是**决策**，不真的调用远端。远端能力是调用方声明的——
声明错了（明明不支持却说支持），策略拦不住。
"""
from .audit import AuditLog

IDEMPOTENCY_MODES = ("key", "none")
QUERY_MODES = ("available", "unavailable")

MANUAL = "MANUAL_REMEDIATION_REQUIRED"


class RemoteRejected(Exception):
    pass


class RemoteGateway:
    def __init__(self, audit_path, capabilities=None):
        self.audit = AuditLog(audit_path)
        # {system: {"idempotency": "key"|"none", "query": "available"|"unavailable"}}
        self.capabilities = dict(capabilities or {})

    def register(self, system, idempotency, query):
        if idempotency not in IDEMPOTENCY_MODES:
            raise RemoteRejected(f"unknown idempotency mode: {idempotency}")
        if query not in QUERY_MODES:
            raise RemoteRejected(f"unknown query mode: {query}")
        self.capabilities[system] = {"idempotency": idempotency, "query": query}

    def capability(self, system):
        """未登记的系统按最保守处理：既不支持幂等、也查不了。

        "没听说过"不等于"能配合"——这与 retrypolicy 里未知操作按破坏性处理
        是同一条原则。
        """
        c = self.capabilities.get(system)
        if c is None:
            return {"idempotency": "none", "query": "unavailable",
                    "registered": False}
        return {**c, "registered": True}

    # ---- AUD-009-03：能力不足时不得默认重放 ----
    def plan(self, op_id, system, idempotency_key=None):
        cap = self.capability(system)
        idem, query = cap["idempotency"], cap["query"]

        def decide(verdict, reason):
            self.audit.append("remote.replay_decision", op_id=op_id,
                              system=system, verdict=verdict, reason=reason,
                              idempotency=idem, query=query,
                              registered=cap["registered"])
            return {"decision": verdict, "reason": reason,
                    "op_id": op_id, "system": system,
                    "capability": {k: v for k, v in cap.items()}}

        if idem == "key":
            if not idempotency_key:
                return decide(MANUAL, "idempotent_replay_requires_key")
            return decide("REPLAY_WITH_KEY", "idempotency_key_supported")
        if query == "available":
            return decide("RECONCILE_FIRST", "query_available_check_before_replay")
        return decide(MANUAL, "no_idempotency_and_query_unavailable")

    RECONCILE_FIRST = "RECONCILE_FIRST"

    def replay(self, op_id, system, idempotency_key=None, reconcile_result=None):
        """真正发起重放前必须过这一关；能力不足直接拒绝（不是"建议"）。

        RECONCILE_FIRST 不是"可以重放"的许可证，而是"先去查"的命令：
        拿不出 reconcile 的 MATCH 结论就不许重放。否则这条分支形同虚设——
        调用方完全可以无视它直接重放，AUD-009-03 就没拦住任何东西。
        """
        p = self.plan(op_id, system, idempotency_key=idempotency_key)
        if p["decision"] == MANUAL:
            raise RemoteRejected(f"{p['reason']}: {op_id} on {system}")
        if p["decision"] == self.RECONCILE_FIRST:
            if not isinstance(reconcile_result, dict) or \
                    reconcile_result.get("result") != "MATCH":
                raise RemoteRejected(
                    f"replay_requires_verified_reconcile: {op_id} on {system}")
            # 结论必须与**本次**操作、同一个系统绑定。
            # 少了这一步，"先去核对"就变成"随便找一份核对过的结论"：
            # 拿 A 操作在安全系统上对上的 MATCH，可以放行 B 操作在危险系统
            # 上的重放——两个系统的决策都是 RECONCILE_FIRST，检查照样过。
            if reconcile_result.get("op_id") != op_id or \
                    reconcile_result.get("system") != system:
                raise RemoteRejected(
                    f"reconcile_result_not_for_this_operation: "
                    f"{op_id} on {system}")
            self.audit.append("remote.replay_after_reconcile", op_id=op_id,
                              system=system, state=reconcile_result.get("state"))
            return {**p, "decision": "REPLAY_AFTER_RECONCILE",
                    "reason": "reconciled_match"}
        return p

    # ---- AUD-010-03：漂移检测与补偿失败 ----
    def reconcile(self, op_id, system, expected, actual=None):
        cap = self.capability(system)
        # 拿不到实际值、或远端查不了，都算"无法核对"——不是"没漂移"。
        # （查不了却塞了个 actual 进来，来源不可信，同样不能采信。）
        if actual is None or cap["query"] == "unavailable":
            self.audit.append("remote.reconcile_unverifiable", op_id=op_id,
                              system=system, expected=expected,
                              reason="no_actual" if actual is None
                                     else "query_unavailable")
            return {"result": "UNVERIFIABLE", "op_id": op_id,
                    "system": system,
                    "reason": "no_actual" if actual is None
                              else "query_unavailable",
                    "next": MANUAL}
        if actual != expected:
            self.audit.append("remote.drift_detected", op_id=op_id, system=system,
                              expected=expected, actual=actual)
            return {"result": "DRIFT_DETECTED", "op_id": op_id,
                    "system": system,
                    "expected": expected, "actual": actual, "next": MANUAL}
        self.audit.append("remote.reconciled", op_id=op_id, system=system,
                          state=expected)
        # 结论必须自带 op_id 与 system：下游 replay 要靠这两个字段核对
        # "这个结论是不是为**本次**操作做的"。缺了它们就只能看 result，
        # 于是别处对上的一次结论可以拿来放行这里的高危重放。
        return {"result": "MATCH", "op_id": op_id, "system": system,
                "state": expected}

    def compensate(self, op_id, plan_ref, result):
        """补偿结果只有"完全成功"才算成功。

        partial 是最危险的返回值：看起来补偿过了，实际遗留了一半副作用。
        把它当成功继续推进，等于把不一致悄悄固化。
        """
        if not plan_ref:
            raise RemoteRejected(f"compensation_requires_plan_ref: {op_id}")
        if result == "ok":
            self.audit.append("remote.compensated", op_id=op_id, plan_ref=plan_ref)
            return {"result": "COMPENSATED", "op_id": op_id}
        if result in ("failed", "partial"):
            self.audit.append("remote.compensation_failed", op_id=op_id,
                              plan_ref=plan_ref, result=result)
            return {"result": "COMPENSATION_FAILED", "op_id": op_id,
                    "detail": result, "next": MANUAL}
        raise RemoteRejected(f"unknown_compensation_result: {result}")
