# -*- coding: utf-8 -*-
"""executor.lock —— 可信写锁 + fencing token（WF-02 / CNC-01 简化实现）。

规则（v1.1.1 §5）：
- 同一资源同一时刻至多一个持有者；
- 每次授予的 fencing token 单调递增；
- 写入必须携带 fence，fence < 当前值的一律拒绝（旧持有者写不进去）；
- 锁过期后必须重新 acquire 获得更大 fence；
- 锁服务不可用时禁止并发写入（失败关闭：本模块任何内部异常都抛错，调用方不得降级为"无锁继续写"）。
"""
import json, threading, time
from pathlib import Path
from .audit import AuditLog


class LockDenied(Exception):
    pass


class StaleFence(Exception):
    pass


class LockService:
    def __init__(self, state_path, audit_path, ttl_seconds=30):
        self.path = Path(state_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(audit_path)
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf8")

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf8"))

    def _save(self, d):
        self.path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf8")

    def acquire(self, resource, holder):
        with self._lock:
            d = self._load()
            cur = d.get(resource)
            now = time.time()
            if cur and cur["expires_at"] > now:
                self.audit.append("lock.denied", resource=resource,
                                  holder=holder, current_holder=cur["holder"])
                raise LockDenied(f"resource '{resource}' held by {cur['holder']}")
            fence = (cur["fence"] + 1) if cur else 1
            d[resource] = {"holder": holder, "fence": fence,
                           "expires_at": now + self.ttl}
            self._save(d)
            self.audit.append("lock.acquired", resource=resource,
                              holder=holder, fence=fence)
            return fence

    def validate_write(self, resource, fence):
        """写入前置校验：fence 过期即拒绝（旧持有者拿旧 token 写不进）。"""
        cur = self._load().get(resource)
        if not cur or fence < cur["fence"]:
            self.audit.append("write.rejected_stale_fence",
                              resource=resource, fence=fence,
                              current_fence=cur["fence"] if cur else None)
            raise StaleFence(f"fence {fence} is stale for '{resource}'")
        return True
