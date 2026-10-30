# -*- coding: utf-8 -*-
"""executor.metrics —— 治理指标字典与超限动作（MTR-01）。

规则：
- AASEGS-SUP-003（P2，MUST NOT）：**不得以代码行数 / Token 数等单维指标排名 Agent**。
- MTR-01：每项治理指标必须有公式、数据源、窗口、owner、阈值、超限动作与恢复条件；
  **缺少公式或超限动作的指标不得作为治理判定依据**。

语义（失败关闭）：
  1. `is_admissible` 逐字段检查；缺任何一项 → 该指标不能用于判定，`evaluate` 直接拒绝，
     而不是"算个大概"；
  2. 计算必须**可复现**：同样的样本与公式得到同样的值，并把输入摘要写进结果
     （`input_digest`），供事后核对"这个数是怎么来的"；
  3. 分母为 0 / 样本为空 → `INSUFFICIENT`，**不得**折成 0 或 1 蒙过去；
  4. 超限 → 同时产生告警与复核工单（`alert_id` / `review_id`），不是只打一行日志；
  5. `rank_agents` 至少需要两个不同维度的指标，单维排名一律拒绝（SUP-003）。

诚实边界：本模块只保证"定义齐全 + 计算可复现 + 超限有动作"，
不保证样本本身真实、不保证工单真的被人处理——那属于流程执行层。
"""
import hashlib
import json

from .audit import AuditLog

REQUIRED_FIELDS = ("formula", "formula_ref", "source", "window", "owner",
                   "threshold", "on_exceed", "recovery")
DIRECTIONS = ("max", "min")          # max: 越大越坏；min: 越小越坏
STATUSES = ("OK", "EXCEED", "INSUFFICIENT")


class MetricRejected(Exception):
    pass


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf8")).hexdigest()[:16]


class MetricRegistry:
    def __init__(self, audit_path):
        self.audit = AuditLog(audit_path)
        self.metrics = {}
        self.alerts = []
        self.reviews = []

    # ---------------- 注册 ----------------
    def register(self, name, formula, formula_ref, source, window, owner,
                 threshold, on_exceed, recovery, direction="max"):
        if not callable(formula):
            raise MetricRejected(f"{name}: formula must be callable")
        if not formula_ref or not isinstance(formula_ref, str):
            raise MetricRejected(f"{name}: formula_ref required (可人读的公式)")
        if direction not in DIRECTIONS:
            raise MetricRejected(f"{name}: direction must be one of {DIRECTIONS}")
        if on_exceed not in ("alert_and_review", "alert_only", "block"):
            # 未登记的处置动作不得冒充"超限动作"
            raise MetricRejected(f"{name}: unknown on_exceed action {on_exceed}")
        self.metrics[name] = {
            "name": name, "formula": formula, "formula_ref": formula_ref,
            "source": source, "window": window, "owner": owner,
            "threshold": threshold, "on_exceed": on_exceed,
            "recovery": recovery, "direction": direction,
        }
        self.audit.append("metric.registered", metric=name, owner=owner,
                          threshold=threshold, action=on_exceed)
        return self.metrics[name]

    # ---------------- 可用性 ----------------
    def missing_fields(self, name):
        m = self.metrics.get(name)
        if m is None:
            return ["<not_registered>"]
        return [f for f in REQUIRED_FIELDS if m.get(f) in (None, "", [])]

    def is_admissible(self, name):
        """缺字段的指标不得作为治理判定依据。"""
        return self.metrics.get(name) is not None and not self.missing_fields(name)

    def _require(self, name):
        if self.metrics.get(name) is None:
            raise MetricRejected(f"{name}: metric not registered")
        missing = self.missing_fields(name)
        if missing:
            self.audit.append("metric.inadmissible", metric=name, missing=missing)
            raise MetricRejected(f"{name}: 定义不完整 {missing}，不得用于治理判定")

    # ---------------- 计算 ----------------
    def evaluate(self, name, samples):
        self._require(name)
        m = self.metrics[name]
        samples = list(samples or [])
        if not samples:
            return {"metric": name, "status": "INSUFFICIENT",
                    "reason": "no_samples", "value": None}
        try:
            value = m["formula"](samples)
        except ZeroDivisionError:
            # 分母为 0 不得折成 0 或 1：样本不足就是样本不足
            return {"metric": name, "status": "INSUFFICIENT",
                    "reason": "zero_denominator", "value": None}
        if value is None:
            return {"metric": name, "status": "INSUFFICIENT",
                    "reason": "formula_returned_none", "value": None}
        digest = _digest({"name": name, "formula": m["formula_ref"],
                          "window": m["window"], "samples": samples})
        th = m["threshold"]
        exceed = (value > th) if m["direction"] == "max" else (value < th)
        result = {"metric": name, "value": value, "threshold": th,
                  "direction": m["direction"],
                  "status": "EXCEED" if exceed else "OK",
                  "window": m["window"], "source": m["source"],
                  "owner": m["owner"], "input_digest": digest,
                  "formula_ref": m["formula_ref"]}
        if exceed:
            alert_id = f"alert:{name}:{digest}"
            self.alerts.append({"alert_id": alert_id, "metric": name,
                                "value": value, "threshold": th,
                                "owner": m["owner"]})
            result["alert_id"] = alert_id
            if m["on_exceed"] in ("alert_and_review", "block"):
                review_id = f"review:{name}:{digest}"
                self.reviews.append({"review_id": review_id, "metric": name,
                                     "alert_id": alert_id,
                                     "owner": m["owner"],
                                     "recovery": m["recovery"]})
                result["review_id"] = review_id
            if m["on_exceed"] == "block":
                result["blocked"] = True
            self.audit.append("metric.exceeded", metric=name, value=value,
                              threshold=th, alert=result.get("alert_id"),
                              review=result.get("review_id"))
        return result

    # ---------------- 排名（SUP-003：禁单维） ----------------
    def rank_agents(self, rows, metrics, reverse=False):
        """多维度排名。

        注意：这里按各维度原始值求和，**不是**一个"公平"的绩效模型——
        它存在的唯一目的是**拦住单维排名**（SUP-003）。真实排名需要
        先做量纲归一并与责任人确认权重，本模块不做那个声明。
        """
        metrics = list(metrics or [])
        if len(set(metrics)) < 2:
            self.audit.append("metric.ranking_rejected", metrics=metrics,
                              reason="single_dimension")
            raise MetricRejected("single_dimension_ranking_forbidden")
        for m in metrics:
            self._require(m)
        weighted = []
        for r in rows:
            score = sum(float(r.get(m, 0)) for m in metrics)
            weighted.append({"agent": r.get("agent"), "score": score,
                             "dimensions": metrics})
        return sorted(weighted, key=lambda x: x["score"], reverse=reverse)
