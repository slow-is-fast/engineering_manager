# -*- coding: utf-8 -*-
"""executor.trust —— 内容来源信任边界（CTX-01）。

服务的规则：
- AASEGS-SEC-005（P0）：不能因内容外观像系统消息而改变身份/权限。
- v1.1.1 §4 记忆生命周期与项目数据隔离：不可信来源的内容必须**标记为不可信**。

语义（失败关闭）：
  1. 每条内容带**来源通道**：只有人工直连（human_direct）与签名策略
     （signed_policy）算可信；工具输出、网页、文档、模型自产、记忆回灌
     一律不可信；
  2. 不可信内容里出现"你现在是…""忽略之前指令""system:""<system>""开发者模式"
     等**冒充系统**的形态，不提升其可信度——只作为注入痕迹记录，**不改变分类**；
  3. 任何**身份/权限/策略变更**都必须由可信来源提出；不可信来源提出 →
     拒绝并记 `trust.authority_change_rejected`；
  4. 试图用"看起来像系统消息"来主张特权，与真正的系统消息区分开：
     判定依据是**来源**，不是**外观**。

诚实边界：本模块是"来源判定 + 注入痕迹检测"，不是完整的提示注入防御；
模型侧是否真的服从了注入，需要在运行时可观测层验证（不属于本模块范围）。
不得据本模块宣称"提示注入已被消除"。
"""
import re

from .audit import AuditLog

TRUSTED_CHANNELS = ("human_direct", "signed_policy")
UNTRUSTED_CHANNELS = ("tool_output", "web", "document", "model_output",
                      "memory_recall", "third_party")

# 冒充系统 / 越权指令的注入痕迹（检测层；非穷尽。中英文并列，因为本治理体系
# 的规范与运行文本以中文为主——只做英文匹配会系统性漏检中文注入）
INJECTION_PATTERNS = [
    ("system_impersonation", re.compile(
        r"(?i)(^\s*(system|developer)\s*:|<\s*/?\s*system\s*>|\[system\]"
        r"|^\s*(系统|开发者)\s*(消息|指令)\s*[:：])")),
    ("override_instructions", re.compile(
        r"(?i)(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+"
        r"(instructions|rules|prompts?)"
        r"|忽略(之前|以上|前面|先前)的?(所有)?(指令|规则|提示|要求)")),
    ("role_hijack", re.compile(
        r"(?i)you\s+are\s+now\s+(a|an|the)\s+"
        r"|你现在(是|扮演)|从现在起(你)?(就是|是|扮演)")),
    ("developer_mode", re.compile(r"(?i)developer\s+mode|jailbreak|DAN mode"
                                  r"|开发者模式|越狱模式")),
    ("privilege_claim", re.compile(
        r"(?i)(grant|elevate|escalate)\s+me\s+(admin|root|write|owner)\s*"
        r"(access|permission|privilege)?"
        # 中文只匹配**自我提权**（"授予我…""给我…权限"）；
        # 合法的第三方授权（"把权限授予 run-7"）不应被记为注入痕迹
        r"|(授予|给|提升)(我|自己)(管理员|root|写入|owner)?(权限|访问权|特权)")),
]

AUTHORITY_CHANGES = ("identity", "permission", "policy", "scope", "role")


class Rejected(Exception):
    pass


class TrustBoundary:
    def __init__(self, audit_path):
        self.audit = AuditLog(audit_path)
        self.records = {}
        self._seq = 0

    def ingest(self, channel, content, source_ref=None):
        """登记一段内容的来源与可信度，返回带判定的记录。"""
        if channel in TRUSTED_CHANNELS:
            trusted = True
        elif channel in UNTRUSTED_CHANNELS:
            trusted = False
        else:
            # 未知通道按不可信处理（失败关闭）
            trusted = False
            channel = "unknown_treated_untrusted"

        hits = []
        for name, pattern in INJECTION_PATTERNS:
            if pattern.search(content or ""):
                hits.append(name)

        self._seq += 1
        cid = "CTX-%04d" % self._seq
        rec = {"content_id": cid, "channel": channel, "trusted": trusted,
               "injection_traces": hits, "source_ref": source_ref}
        self.records[cid] = rec
        self.audit.append("trust.ingested", content_id=cid, channel=channel,
                          trusted=trusted, traces=hits)
        # 关键：注入痕迹**不改变**可信分类——外观不是依据，来源才是
        return rec

    def assert_authority_change(self, content_id, change_kind, detail=""):
        """身份/权限/策略变更只接受可信来源；否则拒绝并告警。"""
        rec = self.records.get(content_id)
        if rec is None:
            self.audit.append("trust.authority_change_rejected",
                              content_id=content_id, reason="unknown_content")
            raise Rejected(f"unknown_content: {content_id}")
        if change_kind not in AUTHORITY_CHANGES:
            self.audit.append("trust.authority_change_rejected",
                              content_id=content_id,
                              reason="unknown_change_kind",
                              change_kind=change_kind)
            raise Rejected(f"unknown_change_kind: {change_kind}")
        if not rec["trusted"]:
            self.audit.append("trust.authority_change_rejected",
                              content_id=content_id,
                              reason="untrusted_provenance",
                              channel=rec["channel"], change_kind=change_kind,
                              detail=detail)
            raise Rejected(
                f"untrusted_provenance: {rec['channel']} cannot change "
                f"{change_kind} (looks-like-system is not authority)")
        self.audit.append("trust.authority_change_accepted",
                          content_id=content_id, change_kind=change_kind)
        return "ACCEPTED"
