# -*- coding: utf-8 -*-
"""executor.audit —— 最小审计事件流（EVD-01 简化实现）。

所有组件的状态变更都追加事件。事件文件为 append-only：
组件只提供 append 与 read，不提供修改/删除接口。
"""
import json, threading, time
from pathlib import Path


class AuditLog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._n = 0

    def append(self, event_type, **fields):
        self._n += 1
        event = {
            "event_id": f"{int(time.time() * 1000):013d}-{self._n}",
            "timestamp": time.time(),
            "event_type": event_type,
            **fields,
        }
        with self._lock:
            with self.path.open("a", encoding="utf8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def read(self, event_type=None):
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if event_type is None or e["event_type"] == event_type:
                out.append(e)
        return out
