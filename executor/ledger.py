# -*- coding: utf-8 -*-
"""executor.ledger —— 外部副作用台账（EFF-01 / WF-03 简化实现）。

规则（v1.1.1 §6）：
- 外部副作用必须以幂等键登记，台账先于副作用写入（PREPARED）；
- 同一幂等键重复投递不产生第二次副作用，返回既有记录；
- 响应丢失进入 UNKNOWN：唯一合法动作是核对真实结果（reconcile），不得盲重放；
- 台账文件只追加状态变更，不可改写历史。
"""
import json, threading
from pathlib import Path
from .audit import AuditLog


class DuplicateRejected(Exception):
    """同一幂等键在 CONFIRMED 后再次请求投递。"""


class UnknownResult(Exception):
    """副作用状态为 UNKNOWN：必须先 reconcile，不得重放。"""


class EffectLedger:
    def __init__(self, path, audit_path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(audit_path)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf8")

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf8"))

    def _save(self, d):
        self.path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf8")

    def submit(self, key, payload):
        """按幂等键登记副作用。返回 (record, replayed: bool)。"""
        with self._lock:
            d = self._load()
            rec = d.get(key)
            if rec:
                if rec["state"] in ("CONFIRMED",):
                    self.audit.append("effect.duplicate_rejected", key=key,
                                      state=rec["state"])
                    raise DuplicateRejected(key)
                if rec["state"] in ("SUBMITTED",):
                    return rec, True           # 并发重复：返回既有，不重放
                if rec["state"] in ("UNKNOWN", "RECONCILIATION_REQUIRED"):
                    self.audit.append("effect.unknown_blocked_replay", key=key)
                    raise UnknownResult(key)
                if rec["state"] == "PREPARED":
                    rec["state"] = "SUBMITTED"
                    rec["payload"] = payload
                    self._save(d)
                    self.audit.append("effect.submitted", key=key)
                    return rec, False
            rec = {"state": "SUBMITTED", "payload": payload, "history": ["SUBMITTED"]}
            d[key] = rec
            self._save(d)
            self.audit.append("effect.submitted", key=key)
            return rec, False

    def confirm(self, key):
        with self._lock:
            d = self._load()
            rec = d[key]
            rec["state"] = "CONFIRMED"
            rec["history"].append("CONFIRMED")
            self._save(d)
            self.audit.append("effect.confirmed", key=key)

    def mark_unknown(self, key):
        """远端可能成功但响应丢失：进入 UNKNOWN，等待核对。"""
        with self._lock:
            d = self._load()
            rec = d[key]
            rec["state"] = "UNKNOWN"
            rec["history"].append("UNKNOWN")
            self._save(d)
            self.audit.append("effect.unknown", key=key)

    def reconcile(self, key, confirmed: bool):
        """核对真实结果：唯一合法的走出 UNKNOWN 的方式。"""
        with self._lock:
            d = self._load()
            rec = d[key]
            rec["state"] = "CONFIRMED" if confirmed else "RECONCILIATION_REQUIRED"
            rec["history"].append(rec["state"])
            self._save(d)
            self.audit.append("effect.reconciled", key=key, state=rec["state"])
            return rec

    # ---- 未接收超时（AUD-008 验收项）----
    def declare_dispatched(self, key, deadline):
        """登记"已发出但未收到回执"的请求及其超时时刻。

        这里的关键不是计时，而是**超时之后算什么状态**：未收到回执
        既不能当成功，也不能当失败——它只能进 UNKNOWN，必须核对。
        """
        with self._lock:
            d = self._load()
            rec = d.get(key)
            if rec is None:
                raise UnknownResult(f"unknown_effect: {key}")
            if rec["state"] != "SUBMITTED":
                raise DuplicateRejected(f"{key}: {rec['state']} 不可再次派发")
            rec["deadline"] = deadline
            rec["history"].append("DISPATCHED")
            self._save(d)
            self.audit.append("effect.dispatched", key=key, deadline=deadline)
            return rec

    def sweep_timeouts(self, now):
        """超时未回执 → UNKNOWN，并返回超时清单（调用方必须逐条核对）。"""
        timed_out = []
        with self._lock:
            d = self._load()
            for key, rec in d.items():
                if rec["state"] != "SUBMITTED":
                    continue
                dl = rec.get("deadline")
                if dl is None or now <= dl:
                    continue
                rec["state"] = "UNKNOWN"
                rec["history"].append("UNKNOWN")
                timed_out.append(key)
            if timed_out:
                self._save(d)
                self.audit.append("effect.receipt_timeout", keys=timed_out,
                                  now=now, next_step="reconcile")
        return timed_out
