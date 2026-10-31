# -*- coding: utf-8 -*-
"""executor.auditlifecycle —— 审计生命周期：保留策略、来源识别、恢复（AUD-014-03）。

与 `audit.py` 的边界（避免重复计费）：
  - `audit.py`（EVD-01/EVD-02）管**写入与完整性**：哈希链让篡改可检测，
    不可用即失败关闭。它回答"这条链有没有被动过"。
  - 本模块管**写完之后**：这些事件该留多久（保留）、谁写的（来源）、
    坏了之后怎么接着用（恢复）。

诚实边界（重要，别越界宣称）：
**单个审计文件内部无法证明写入者是谁**——持有写权限的人可以写出任意来源
字段。本模块能做的是**内部一致性层面的伪造识别**：来源缺失、未登记、seq
回放、事件类型越出该来源声明的范围。真正"来源独立可证"依赖审计后端的
权限分离与独立存储（AUD-014-04，manual）。把一致性检查说成身份证明，
正是本规范一直在防的那种夸大。

三件事共有的原则：**不得静默**。超期没删要说、来源可疑要说、恢复丢掉的
段落要原样交出来——沉默等于把问题擦掉。
"""
import json
import time

SECONDS_PER_DAY = 86400
GENESIS = "0" * 64


class LifecycleRejected(Exception):
    pass


class ProvenanceRegistry:
    """来源登记表：谁被允许往这条审计流里写什么。

    未登记的来源按可疑处理——"没登记过"不等于"允许"。
    """

    def __init__(self):
        # name -> {"writer": str|None, "event_types": frozenset|None}
        self.sources = {}

    def declare(self, name, writer=None, event_types=None):
        if not name:
            raise LifecycleRejected("provenance source name must be non-empty")
        allowed = (frozenset(event_types) if event_types is not None else None)
        self.sources[name] = {"writer": writer, "event_types": allowed}
        return self.sources[name]

    def check(self, events):
        """返回 {"ok": bool, "findings": [...]}。

        五类可疑：来源缺失 / 未登记 / 事件类型越界 / 序号缺失 / 同一来源 seq 回放。

        序号缺失也算可疑：没有序号的事件既排不进顺序，也**检测不了重放**——
        把它静默放过，等于给重放留了一条检测不到的通道。
        """
        findings = []
        last_seq = {}
        for e in events:
            seq, etype = e.get("seq"), e.get("event_type")
            src = e.get("source")
            if src is None:
                findings.append({"seq": seq, "kind": "missing_source",
                                 "verdict": "FORGED_SUSPECT",
                                 "detail": "事件没有声明来源，无法归因"})
                continue
            if src not in self.sources:
                findings.append({"seq": seq, "kind": "undeclared_source",
                                 "verdict": "FORGED_SUSPECT", "source": src,
                                 "detail": "来源未登记，按可疑处理"})
                continue
            if isinstance(seq, bool) or not isinstance(seq, int):
                # 没有可用序号：排不进顺序，也检测不了重放。按可疑处理，
                # 而不是"检测不到就算干净"——那正是重放想要的待遇。
                findings.append({"seq": None, "kind": "missing_seq",
                                 "verdict": "FORGED_SUSPECT", "source": src,
                                 "detail": "事件没有可用序号，无法排序也无法检测重放"})
                continue
            allowed = self.sources[src]["event_types"]
            if allowed is not None and etype not in allowed:
                findings.append({"seq": seq, "kind": "event_type_out_of_scope",
                                 "verdict": "FORGED_SUSPECT", "source": src,
                                 "detail": f"{src} 未被授权写 {etype}"})
            prev = last_seq.get(src)
            if prev is not None and seq <= prev:
                findings.append({"seq": seq, "kind": "source_seq_replay",
                                 "verdict": "FORGED_SUSPECT", "source": src,
                                 "detail": f"该来源 seq 回退（{prev} → {seq}），疑似重放"})
            last_seq[src] = seq
        return {"ok": not findings, "findings": findings}


class RetentionPolicy:
    """保留策略：每类数据允许留多久，超期即违规。

    未登记的类别按**没有保留授权**处理（UNDECLARED），而不是按"随便留"。
    "没人说过要留"不等于"可以一直留"。
    """

    def __init__(self, policy=None):
        self.policy = dict(policy or {})

    def declare(self, category, days):
        if not category:
            raise LifecycleRejected("retention category must be non-empty")
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise LifecycleRejected(f"retention days must be a positive int: {days!r}")
        self.policy[category] = days

    @staticmethod
    def category_of(event):
        return event.get("category") or event.get("event_type")

    def expired(self, events, now=None):
        """找出超期（或没有保留授权）仍留在流里的事件。"""
        now = time.time() if now is None else now
        out = []
        for e in events:
            cat = self.category_of(e)
            limit = self.policy.get(cat)
            if limit is None:
                out.append({"event": e, "category": cat,
                            "verdict": "UNDECLARED",
                            "detail": "该类别没有登记保留期，不得无限期保留"})
                continue
            ts = e.get("timestamp")
            if not isinstance(ts, (int, float)):
                out.append({"event": e, "category": cat,
                            "verdict": "UNKNOWN_AGE",
                            "detail": "时间戳缺失或不可解析，无法判断是否超期"})
                continue
            age = (now - ts) / SECONDS_PER_DAY
            if age > limit:
                out.append({"event": e, "category": cat,
                            "verdict": "EXPIRED",
                            "age_days": round(age, 4), "limit_days": limit})
        return out

    def plan_purge(self, expired, approver=None, requester=None):
        """超期事件要删——但删除本身必须有批准，且不得由提出者自批。

        没有批准的删除计划不生成：保留违规是合规问题，但"顺手删掉"会
        把审计流变成可以随便修剪的东西，那是更大的问题。

        自批隔离**由代码执行，不是由文档声明**：`requester` 与 `approver`
        同一人即拒绝。此前这一条只写在 docstring 里而函数不收 requester，
        等于承诺了一件根本没检查的事——正是本规范要防的那种记账失真。
        """
        if not approver:
            raise LifecycleRejected(
                f"purge requires an approver: {len(expired)} expired events")
        if requester and approver == requester:
            raise LifecycleRejected(
                f"purge requester cannot be the approver: {requester}")
        return {"approver": approver, "requester": requester,
                "count": len(expired),
                "items": [{"seq": x["event"].get("seq"),
                           "category": x["category"],
                           "verdict": x["verdict"]} for x in expired]}


def recover(audit_log):
    """从损坏/截断的审计流恢复到最后一个链完整的点。

    返回：
      recovered         —— 从头到第一个坏点之前、链完整的事件
      dropped           —— 第一个坏点及其之后的所有原始行（**原样返回**）
      last_trusted_seq  —— 最后一个可信事件的 seq
      reason            —— 为什么停

    `dropped` 必须交出来而不是丢掉：**静默丢弃被篡改的段落，等于替篡改者
    擦掉痕迹。** 恢复的意义是"能接着用"，不是"当作没发生过"。
    """
    raw_lines = audit_log._lines()
    recovered, dropped, started = [], [], False
    prev = GENESIS
    expect_seq = 1
    reason = None

    for i, line in enumerate(raw_lines, 1):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            bad = f"line {i}: 不可解析（截断或损坏）"
        else:
            if not isinstance(e, dict):
                # 能解析但不是对象（如裸 123/"x"/[]）——它不是"损坏"，
                # 而是根本不参与链校验；得报出来，不能让 AttributeError
                # 把恢复本身搞崩：恢复失败 = 审计流彻底不可用。
                bad = f"line {i}: 不是 JSON 对象，无法参与链校验"
            elif e.get("prev_hash") != prev:
                bad = f"line {i}: prev_hash 不接（链断）"
            elif e.get("hash") != audit_log._hash(e):
                bad = f"line {i}: hash 不匹配（内容被改）"
            elif e.get("seq") != expect_seq:
                bad = f"line {i}: seq {e.get('seq')} != 期望 {expect_seq}"
            else:
                bad = None
        if bad is not None:
            # 只记**第一个**坏点：诊断要指向出事的那一行。
            # 否则后面每一行都会把 reason 顶掉，最后报出来的是末尾那条
            # 无关的"链断"，事故定位被直接带偏。
            if not started:
                reason = bad
            started = True
        if started:
            dropped.append(line)
            continue
        recovered.append(e)
        prev = e.get("hash", prev)
        expect_seq += 1

    last = recovered[-1].get("seq") if recovered else 0
    return {"recovered": recovered, "dropped": dropped,
            "last_trusted_seq": last, "reason": reason,
            "complete": not dropped}
