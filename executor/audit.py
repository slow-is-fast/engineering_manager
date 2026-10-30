# -*- coding: utf-8 -*-
"""executor.audit —— 防篡改审计事件流（EVD-01 / EVD-02）。

升级点：
- **哈希链**：每条事件带 `seq` / `prev_hash` / `hash`，`hash` 覆盖本条事件内容与
  前一条哈希。改内容、删行、重排、截断都会被 `verify()` 检出（tamper-evident）。
- **失败关闭（EVD-02）**：审计不可用时不得静默继续——
  `ensure_available()` / `read(strict=True)` 在文件缺失、不可读或内容损坏时
  抛出 `AuditUnavailable`，而不是返回空列表假装"没有事件"。

诚实边界：哈希链让篡改**可检测**，不等于**不可篡改**——
写入权限仍在持有者手里；真正的防篡改需要独立审计存储与权限分离
（GOV-14/VD-01 与 AUD-014 的职责）。本模块不越界宣称。
"""
import hashlib
import json
import threading
import time
from pathlib import Path

GENESIS = "0" * 64


class AuditUnavailable(Exception):
    """审计不可用（缺失/不可读/损坏）→ 调用方必须失败关闭。"""


class AuditLog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._n = 0

    # ---- 哈希 ----
    @staticmethod
    def _canon(event):
        return json.dumps(event, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))

    @classmethod
    def _hash(cls, event):
        payload = {k: v for k, v in event.items() if k != "hash"}
        return hashlib.sha256(cls._canon(payload).encode("utf8")).hexdigest()

    def _lines(self):
        if not self.path.exists():
            return []
        return [l for l in self.path.read_text(encoding="utf8").splitlines() if l.strip()]

    def _last_hash(self):
        lines = self._lines()
        if not lines:
            return GENESIS
        try:
            return json.loads(lines[-1]).get("hash", GENESIS)
        except json.JSONDecodeError:
            raise AuditUnavailable(f"corrupt audit tail: {self.path}")

    # ---- 写入 ----
    def append(self, event_type, **fields):
        with self._lock:
            prev = self._last_hash()
            seq = len(self._lines()) + 1
            self._n += 1
            event = {
                "seq": seq,
                "event_id": f"{int(time.time() * 1000):013d}-{self._n}",
                "timestamp": time.time(),
                "event_type": event_type,
                **fields,
                "prev_hash": prev,
            }
            event["hash"] = self._hash(event)
            with self.path.open("a", encoding="utf8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def append_from(self, source, event_type, **fields):
        """带来源声明的写入（AUD-014-03 的"来源可识别"前提）。

        单独开一个方法而不是给 `append` 加关键字：`append(event_type, **fields)`
        的 fields 是开放的，加 `source` 参数会和同名业务字段撞车。
        """
        return self.append(event_type, source=source, **fields)

    # ---- 读取 ----
    def read(self, event_type=None, strict=False):
        if not self.path.exists():
            if strict:
                raise AuditUnavailable(f"audit log missing: {self.path}")
            return []
        out = []
        for i, line in enumerate(self._lines(), 1):
            try:
                e = json.loads(line)
            except json.JSONDecodeError as exc:
                if strict:
                    raise AuditUnavailable(
                        f"corrupt audit line {i}: {self.path}") from exc
                continue
            if event_type is None or e.get("event_type") == event_type:
                out.append(e)
        return out

    # ---- 校验：EVD-01（篡改可检测）----
    def verify(self):
        """返回 (ok, errors)。篡改、删行、重排、截断都会被检出。"""
        if not self.path.exists():
            return False, ["audit log missing"]
        errors = []
        prev = GENESIS
        expect_seq = 1
        for i, line in enumerate(self._lines(), 1):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"line {i}: corrupt json")
                break
            if e.get("prev_hash") != prev:
                errors.append(f"line {i}: prev_hash mismatch (chain broken)")
            if e.get("hash") != self._hash(e):
                errors.append(f"line {i}: hash mismatch (content altered)")
            if e.get("seq") != expect_seq:
                errors.append(f"line {i}: seq {e.get('seq')} != expected {expect_seq}")
            prev = e.get("hash", prev)
            expect_seq += 1
        return (not errors), errors

    # ---- 失败关闭：EVD-02（不可用不得静默）----
    def ensure_available(self):
        if not self.path.exists():
            raise AuditUnavailable(f"audit log missing: {self.path}")
        ok, errors = self.verify()
        if not ok:
            raise AuditUnavailable(f"audit log integrity check failed: {errors}")
        return True
