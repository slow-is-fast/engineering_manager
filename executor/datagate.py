# -*- coding: utf-8 -*-
"""executor.datagate —— 数据生命周期闸门（AUD-016-03）。

三件事，各自对应一条常见事故：
  1. **删除后再现**：删了的东西从别的路径又出来了（导出、缓存、重新入库）。
  2. **超期保留**：该删的没删，理由是"没人说过要删"。
  3. **未经批准的传输**：数据被搬到没登记过的目的地。

与既有模块的边界：
  - `approval.py`（APR-01）验证**审批记录与请求是否一致**；本模块不重复实现
    审批，只做一件它没做的事：**自批隔离**（批准人不得是发起者）。
  - `auditlifecycle.py`（ALC-01）的 `RetentionPolicy` 直接复用，不重写。
  - `credential.py`（CRT-01）管凭证泄露与轮换；本模块管数据本身。

设计取向（失败关闭）：
  - 删除是**真的删**：content 置空并立 tombstone，不是打个标记留着。
  - tombstone 生效后，**所有出口都不得交出内容**——读、导出、传输都不行。
    这是"删除后再现"唯一的拦法：逐条出口去堵是堵不完的，堵在数据层。
  - 想让它重现必须走**显式的 `resurrect`**，带批准，且批准人不得是当初
    批准删除的那个人；同时留一条独立审计事件。静默重入 = 删除形同虚设。
  - 目的地必须**先登记**再传；没登记过 ≠ 允许。

诚实边界：本模块管的是"我们自己的数据平面行为"。它管不到已经离开本系统的
副本（对端留存、下游缓存、已发出的导出产物）——那属于传输协议与合约层面的
职责，不在本模块范围内。
"""
import time

from .audit import AuditLog
from .auditlifecycle import RetentionPolicy

SOURCE = "datagate"


class DataGateRejected(Exception):
    pass


class DataGate:
    def __init__(self, audit_path, retention=None):
        self.audit = AuditLog(audit_path)
        self.items = {}                 # id -> {content, category, created_at}
        self.tombstones = {}            # id -> {deleted_at, approver, reason}
        self.destinations = {}          # dest -> {"requires_approval": bool}
        self.retention = retention if retention is not None else RetentionPolicy()

    # ---- 登记与读取 ----
    def put(self, item_id, content, category, created_at=None):
        if item_id in self.tombstones:
            # 已删除的 id 不能悄悄重新入库——那是最常见的"删除后再现"
            raise DataGateRejected(
                f"resurrect requires explicit approval: {item_id}")
        if item_id in self.items:
            # 活数据也不许静默覆盖。覆盖能顺手改掉 `category`：把 pii
            # （保留 30 天）改成 public（保留 3650 天），"超期保留"这条控制
            # 就被绕过去了，而且一条审计都不留。宁可拒绝，要改走显式通道。
            raise DataGateRejected(
                f"item already exists, silent overwrite rejected: {item_id}")
        self.items[item_id] = {
            "content": content, "category": category,
            "created_at": time.time() if created_at is None else created_at,
        }
        return {"item_id": item_id, "state": "LIVE"}

    def get(self, item_id):
        """删除后即便内容还在内存里也不得交出来——这是出口，不是查询。"""
        if item_id in self.tombstones:
            t = self.tombstones[item_id]
            return {"item_id": item_id, "state": "TOMBSTONE",
                    "deleted_at": t["deleted_at"], "reason": t["reason"]}
        it = self.items.get(item_id)
        if it is None:
            raise DataGateRejected(f"unknown item: {item_id}")
        return {"item_id": item_id, "state": "LIVE",
                "content": it["content"], "category": it["category"]}

    # ---- 删除与再现 ----
    def delete(self, item_id, approval):
        approval = approval or {}
        approver = approval.get("approver")
        if not approver:
            raise DataGateRejected(f"delete requires an approver: {item_id}")
        it = self.items.get(item_id)
        if it is None and item_id not in self.tombstones:
            raise DataGateRejected(f"unknown item: {item_id}")
        if item_id in self.tombstones:
            # 再删一次本该是空操作，但在这里"允许"会把原来的删除批准人顶掉——
            # 于是 A 批删、B 再删一次、A 批恢复就绕开了双人隔离。宁可拒绝。
            raise DataGateRejected(f"already deleted: {item_id}")
        self.audit.append_from(SOURCE, "datagate.item_deleted", item_id=item_id,
                               approver=approver, reason=approval.get("reason"),
                               category=(it or {}).get("category"))
        self.tombstones[item_id] = {
            "deleted_at": time.time(), "approver": approver,
            "reason": approval.get("reason"),
            # 记住它原本的产生时刻：恢复时保留时钟得接着算，
            # 不能让"删掉再恢复"把数据年龄清零（见 resurrect）。
            "created_at": (it or {}).get("created_at"),
        }
        if it is not None:
            it["content"] = None            # 真的删，不是打标
        return {"item_id": item_id, "state": "TOMBSTONE"}

    def resurrect(self, item_id, content, category, approval):
        """显式再现：必须批准，且批准人不得是当初批准删除的那个人。

        同一人既能批删又能批准恢复，等于一个人就能让删除失效。
        """
        t = self.tombstones.get(item_id)
        if t is None:
            raise DataGateRejected(f"not deleted, nothing to resurrect: {item_id}")
        approval = approval or {}
        approver = approval.get("approver")
        if not approver:
            raise DataGateRejected(f"resurrect requires an approver: {item_id}")
        if approver == t["approver"]:
            raise DataGateRejected(
                f"same approver cannot both delete and resurrect: {item_id}")
        self.tombstones.pop(item_id)
        # 保留时钟按数据**产生**的时刻算，不按恢复的时刻算：
        # 否则"删掉再恢复"就能把年龄清零，超期保留这条控制形同虚设。
        original = t.get("created_at")
        self.items[item_id] = {
            "content": content, "category": category,
            "created_at": time.time() if original is None else original,
        }
        self.audit.append_from(SOURCE, "datagate.item_resurrected",
                               item_id=item_id, approver=approver,
                               earlier_deletion_approver=t["approver"])
        return {"item_id": item_id, "state": "LIVE"}

    # ---- 保留：复用 RetentionPolicy ----
    def sweep_retention(self, now=None):
        """扫**活**数据：已删（有 tombstone）的不在此列。

        已删项的内容已经清空，把它当活数据报超期，得到的是一条无法处置的
        噪音——你不能再去删一个墓碑。

        诚实边界：tombstone 自身的保留期**本模块不做治理**。它必须留着，
        否则无法证明"删过"、也无法阻止未经授权的 resurrect；它没有登记
        保留期并不意味着"可以一直留"，而是这个决定属于保留策略层
        （ALC-01 的 RetentionPolicy），不该由数据闸门自己拍。
        """
        pseudo = []
        for i, (k, it) in enumerate(sorted(self.items.items()), 1):
            if k in self.tombstones:
                continue
            pseudo.append({"seq": i, "event_type": it["category"],
                           "timestamp": it["created_at"]})
        return self.retention.expired(pseudo, now=now)

    # ---- 传输 ----
    def declare_destination(self, dest, requires_approval=True):
        if not dest:
            raise DataGateRejected("destination must be non-empty")
        self.destinations[dest] = {"requires_approval": bool(requires_approval)}
        return self.destinations[dest]

    def transfer(self, item_ids, destination, approval=None, requester=None):
        """搬数据出境：目的地必须登记，且批准人不得是发起者。"""
        if destination not in self.destinations:
            raise DataGateRejected(f"undeclared destination: {destination}")
        if self.destinations[destination]["requires_approval"]:
            approval = approval or {}
            approver = approval.get("approver")
            if not approver:
                raise DataGateRejected(
                    f"transfer to {destination} requires an approver")
            if requester and approver == requester:
                raise DataGateRejected(
                    f"requester cannot approve own transfer: {requester}")
        payload = []
        for i in item_ids:
            got = self.get(i)             # 走同一出口：删过的一律带不出去
            if got["state"] != "LIVE":
                raise DataGateRejected(f"cannot transfer non-live item: {i}")
            payload.append({"item_id": i, "content": got["content"]})
        self.audit.append_from(SOURCE, "datagate.transferred",
                               destination=destination, items=list(item_ids),
                               approver=(approval or {}).get("approver"),
                               requester=requester)
        return {"destination": destination, "count": len(payload)}
