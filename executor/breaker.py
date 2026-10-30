# -*- coding: utf-8 -*-
"""executor.breaker —— 按原因码的熔断器（REC-03 / BRK-01 简化实现）。

规则（v1.1.1 §7）：
- 每种熔断原因有独立阈值与观察窗口；
- 严重越权（severity=severe 的原因码）**立即**熔断，不累计；
- 熔断后拒绝一切新的副作用，直到人工解除（本实现不提供自动解除）。
"""
import json, time
from pathlib import Path
from .audit import AuditLog


class BreakerOpen(Exception):
    pass


class CircuitBreaker:
    def __init__(self, path, audit_path, thresholds=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(audit_path)
        self.thresholds = thresholds or {"generic": 3}
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf8")

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf8"))

    def _save(self, d):
        self.path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf8")

    def record(self, cause, severity="normal"):
        """记录一次异常。severe 立即熔断；普通按阈值累计（窗口内）。"""
        d = self._load()
        now = time.time()
        if d.get("open"):
            return True
        if severity == "severe":
            d["open"] = {"cause": cause, "at": now, "trigger": "severe_immediate",
                         "count": None}
            self._save(d)
            self.audit.append("breaker.opened", cause=cause, trigger="severe_immediate")
            return True
        c = d.setdefault("counters", {}).setdefault(cause, [])
        c.append(now)
        window = [t for t in c if now - t < 300]     # 5 分钟观察窗口
        d["counters"][cause] = window
        if len(window) >= self.thresholds.get(cause, 3):
            d["open"] = {"cause": cause, "at": now, "trigger": "threshold",
                         "count": len(window)}
            self._save(d)
            self.audit.append("breaker.opened", cause=cause, trigger="threshold",
                              count=len(window))
            return True
        self._save(d)
        self.audit.append("breaker.recorded", cause=cause, count=len(window))
        return False

    def allow(self, operation):
        """副作用前置校验：熔断打开时一律拒绝。"""
        if self._load().get("open"):
            self.audit.append("side_effect.rejected_breaker_open", operation=operation)
            raise BreakerOpen(f"circuit open: {self._load()['open']['cause']}")
        return True

    # ---- 事件乱序（AUD-011 验收项）----
    def apply_event(self, seq, cause, severity="normal"):
        """带序号的事件摄入：旧事件（seq ≤ 已处理最大序号）一律忽略。

        乱序重放会让同一个失败被计两次，把阈值提前打满；也会让一条迟到的
        "普通事件"把刚打开的熔断器状态搅乱。因此序号必须单调，旧事件只记录
        不生效——**忽略也是一种明确决策，要留痕**。
        """
        d = self._load()
        last = d.get("last_seq", 0)
        if seq <= last:
            self.audit.append("breaker.event_reordered", seq=seq,
                              last_seq=last, cause=cause, action="ignored")
            return {"action": "IGNORED", "seq": seq, "last_seq": last}
        d["last_seq"] = seq
        self._save(d)
        opened = self.record(cause, severity=severity)
        self.audit.append("breaker.event_applied", seq=seq, cause=cause,
                          severity=severity, opened=bool(opened))
        return {"action": "APPLIED", "seq": seq, "last_seq": seq,
                "opened": bool(opened)}
