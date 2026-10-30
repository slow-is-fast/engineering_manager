# -*- coding: utf-8 -*-
"""executor.incident —— 安全事件响应工作流（INC-01）。

服务的规则（v1.1.1 §9 审计证据与安全事件响应 / AUD-015）：
- 安全事件必须有**分级、主责/替代负责人、通知时限、隔离、凭证轮换、
  受影响 Run/commit/数据排查、证据保全、恢复审批、复验与复盘**；
- **涉事 Agent 不得批准自己的恢复或关闭事件**，尝试时拒绝并告警。

工作流语义（全部失败关闭）：
  1. 事件分级 SEV1/SEV2/SEV3；主责与替代负责人必须是人类且不得是涉事主体；
  2. 通知时限：SEV1 ≤1h / SEV2 ≤24h / SEV3 ≤72h；关闭前必须有通知记录，
     超时通知**照实记录**为 late（不伪装准时，也不因此静默放行）；
  3. 隔离（contain）要求：隔离对象清单 + 证据保全标记；缺任一 → 拒绝；
  4. 恢复（recover）要求：已隔离；影响面排查（受影响 run/commit/数据）
     已完成；涉凭证事件必须有轮换记录；
  5. 关闭（close）要求：已恢复 + 复验记录 + 复盘报告引用 + 通知已记录；
  6. 恢复与关闭必须由**未涉事的人类负责人**批准：涉事主体（无论 Agent
     还是人类，如本人凭证泄露）或 Agent 类型主体尝试 → 拒绝并写
     `self_approval_attempt` 告警事件；
  7. 未知事件、非法状态跃迁、审批人不在负责人名单 → 一律拒绝。

诚实边界：本模块强制的是**响应流程的完备性与独立性**；
它不证明隔离在真实基础设施上生效（那是运行时的职责），
也不代替 Security Owner 对响应手册内容的实质审查（AUD-015 关闭条件）。
"""
from .audit import AuditLog

SEVERITIES = ("SEV1", "SEV2", "SEV3")
NOTIFICATION_DEADLINE_HOURS = {"SEV1": 1, "SEV2": 24, "SEV3": 72}

STATES = ("OPEN", "CONTAINED", "RECOVERED", "CLOSED")
ACTIONS = ("contain", "recover", "close")


class Rejected(Exception):
    pass


class IncidentWorkflow:
    def __init__(self, human_principals, audit_path):
        self.humans = set(human_principals)
        self.audit = AuditLog(audit_path)
        self.incidents = {}

    # ---- 事件登记：分级 + 双负责人（人类、非涉事、互不相同） ----
    def declare(self, incident_id, severity, title, implicated,
                primary_owner, backup_owner, credential_exposure=False,
                declared_at=None):
        if severity not in SEVERITIES:
            raise Rejected(f"unknown_severity: {severity}")
        implicated = list(implicated or [])
        if not implicated:
            raise Rejected("incident_without_implicated_principals")
        for who, role in ((primary_owner, "primary_owner"),
                          (backup_owner, "backup_owner")):
            if who not in self.humans:
                raise Rejected(f"non_human_{role}: {who}")
            if who in implicated:
                raise Rejected(f"implicated_{role}: {who}")
        if primary_owner == backup_owner:
            raise Rejected("primary_and_backup_must_differ")
        if incident_id in self.incidents:
            raise Rejected(f"duplicate_incident: {incident_id}")

        self.incidents[incident_id] = {
            "incident_id": incident_id, "severity": severity, "title": title,
            "implicated": implicated, "primary_owner": primary_owner,
            "backup_owner": backup_owner,
            "credential_exposure": bool(credential_exposure),
            "state": "OPEN", "declared_at": declared_at,
            "quarantined": [], "evidence_preserved": False,
            "rotated": False, "impact_assessed": False,
            "notified_at": None, "recovered_at": None,
            "reverified": False, "postmortem_ref": None,
        }
        self.audit.append("incident.declared", incident_id=incident_id,
                          severity=severity, implicated=implicated)
        return self.incidents[incident_id]

    def _reject(self, incident_id, action, reason, **extra):
        self.audit.append("incident.action_rejected", incident_id=incident_id,
                          action=action, reason=reason, **extra)
        raise Rejected(f"{reason}: {extra}")

    # ---- 审批人校验：核心失败行为（T-INC-01） ----
    def _check_approver(self, incident_id, action, approver):
        if incident_id not in self.incidents:
            self._reject(incident_id, action, "unknown_incident")
        record = self.incidents[incident_id]
        responders = (record["primary_owner"], record["backup_owner"])
        # 涉事主体（Agent 或人类）尝试批准 → 拒绝并告警（写专门事件）
        if approver in record["implicated"]:
            self.audit.append("self_approval_attempt", incident_id=incident_id,
                              action=action, approver=approver)
            raise Rejected(
                f"implicated_principal_cannot_approve_{action}: {approver}")
        # 审批必须是未被涉事的人类负责人
        if approver not in self.humans:
            self._reject(incident_id, action, "non_human_approver",
                         approver=approver)
        if approver not in responders:
            self._reject(incident_id, action, "approver_not_responder",
                         approver=approver)

    # ---- 通知：记录时间戳；超时照实标记，不伪装准时 ----
    def notify(self, incident_id, notified_at):
        if incident_id not in self.incidents:
            self._reject(incident_id, "notify", "unknown_incident")
        inc = self.incidents[incident_id]
        deadline_h = NOTIFICATION_DEADLINE_HOURS[inc["severity"]]
        inc["notified_at"] = notified_at
        inc["notification_late"] = False
        if inc["declared_at"] and notified_at:
            from datetime import datetime
            d = datetime.fromisoformat(str(inc["declared_at"]).replace("Z", "+00:00"))
            n = datetime.fromisoformat(str(notified_at).replace("Z", "+00:00"))
            late = (n - d).total_seconds() / 3600 > deadline_h
            inc["notification_late"] = bool(late)
        self.audit.append("incident.notified", incident_id=incident_id,
                          notified_at=notified_at,
                          late=inc["notification_late"])
        return inc["notification_late"]

    # ---- 隔离：隔离对象清单 + 证据保全，两者缺一不可 ----
    def contain(self, incident_id, approver, quarantined, evidence_preserved):
        self._check_approver(incident_id, "contain", approver)
        inc = self.incidents[incident_id]
        if inc["state"] != "OPEN":
            self._reject(incident_id, "contain", "invalid_transition",
                        state=inc["state"])
        if not quarantined:
            self._reject(incident_id, "contain", "empty_quarantine_list")
        if not evidence_preserved:
            self._reject(incident_id, "contain", "evidence_not_preserved")
        inc["state"] = "CONTAINED"
        inc["quarantined"] = list(quarantined)
        inc["evidence_preserved"] = True
        self.audit.append("incident.contained", incident_id=incident_id,
                          quarantined=inc["quarantined"], approver=approver)
        return inc

    # ---- 恢复：隔离完成 + 影响面排查 + （涉凭证时）轮换记录 ----
    def recover(self, incident_id, approver, impact_assessed,
                credential_rotated=None):
        self._check_approver(incident_id, "recover", approver)
        inc = self.incidents[incident_id]
        if inc["state"] != "CONTAINED":
            self._reject(incident_id, "recover", "invalid_transition",
                        state=inc["state"])
        if not impact_assessed:
            self._reject(incident_id, "recover", "impact_not_assessed")
        if inc["credential_exposure"] and credential_rotated is not True:
            self._reject(incident_id, "recover", "credential_rotation_missing")
        inc["state"] = "RECOVERED"
        inc["impact_assessed"] = True
        inc["rotated"] = inc["credential_exposure"]
        self.audit.append("incident.recovered", incident_id=incident_id,
                          approver=approver)
        return inc

    # ---- 关闭：已恢复 + 通知已记录 + 复验 + 复盘报告 ----
    def close(self, incident_id, approver, reverified, postmortem_ref):
        self._check_approver(incident_id, "close", approver)
        inc = self.incidents[incident_id]
        if inc["state"] != "RECOVERED":
            self._reject(incident_id, "close", "invalid_transition",
                        state=inc["state"])
        if not inc["notified_at"]:
            self._reject(incident_id, "close", "notification_not_recorded")
        if not reverified:
            self._reject(incident_id, "close", "not_reverified")
        if not postmortem_ref:
            self._reject(incident_id, "close", "missing_postmortem")
        inc["state"] = "CLOSED"
        inc["reverified"] = True
        inc["postmortem_ref"] = postmortem_ref
        self.audit.append("incident.closed", incident_id=incident_id,
                          approver=approver,
                          notification_late=inc.get("notification_late", False))
        return inc
