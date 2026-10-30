# -*- coding: utf-8 -*-
"""executor.checkpoint —— Checkpoint 存储与恢复前校验（CKP-01）。

规则（v1.1.1 §7 / AUD-010）：
- 保存时对 (baseline, payload) 计算完整性摘要，摘要与内容绑定；
- 摘要不匹配 = 快照损坏 → 拒绝恢复；
- **恢复前四项校验**（CKP-01 核心）：
    1) 授权仍有效        2) 策略版本一致
    3) 工作区基线一致    4) 外部副作用状态无 UNKNOWN/未决
- 任一不符 → **暂停并重新评估**（不得直接续写）；
- 不可补偿（不可逆）操作 → 进入 `MANUAL_REMEDIATION_REQUIRED`，交人工处置。

诚实边界：本模块判定"**恢复条件是否仍成立**"；
它不保证快照内容本身正确（那取决于保存时的正确性），也不替代备份/存储层完整性。
"""
import hashlib
import json
from pathlib import Path

from .audit import AuditLog


class Corrupted(Exception):
    pass


class BaselineChanged(Exception):
    pass


class PausedForReevaluation(Exception):
    """CKP-01：恢复条件不成立 → 暂停，不得续写。"""


class ManualRemediationRequired(Exception):
    """不可补偿（不可逆）操作 + 条件不成立 → 人工处置。"""


class CheckpointStore:
    def __init__(self, path, audit_path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(audit_path)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf8")

    @staticmethod
    def digest(baseline, payload):
        blob = json.dumps({"b": baseline, "p": payload},
                          ensure_ascii=False, sort_keys=True).encode("utf8")
        return hashlib.sha256(blob).hexdigest()

    def save(self, cp_id, task, baseline, payload, policy_hash=None):
        d = json.loads(self.path.read_text(encoding="utf8"))
        d[cp_id] = {"task": task, "baseline": baseline, "payload": payload,
                    "policy_hash": policy_hash,
                    "digest": self.digest(baseline, payload)}
        self.path.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                             encoding="utf8")
        self.audit.append("checkpoint.saved", cp_id=cp_id, task=task,
                          baseline=baseline, policy_hash=policy_hash)
        return d[cp_id]["digest"]

    def _load(self, cp_id):
        d = json.loads(self.path.read_text(encoding="utf8"))
        cp = d.get(cp_id)
        if not cp:
            self.audit.append("checkpoint.restore_denied", cp_id=cp_id, reason="missing")
            raise Corrupted(f"checkpoint '{cp_id}' not found")
        if self.digest(cp["baseline"], cp["payload"]) != cp["digest"]:
            self.audit.append("checkpoint.restore_denied", cp_id=cp_id, reason="corrupted")
            raise Corrupted(f"checkpoint '{cp_id}' digest mismatch")
        return cp

    def restore(self, cp_id, current_baseline, authorized: bool):
        cp = self._load(cp_id)
        if not authorized:
            self.audit.append("checkpoint.restore_denied", cp_id=cp_id, reason="unauthorized")
            raise BaselineChanged(f"checkpoint '{cp_id}': authorization invalid")
        if cp["baseline"] != current_baseline:
            self.audit.append("checkpoint.paused_baseline_mismatch", cp_id=cp_id,
                              saved=cp["baseline"], current=current_baseline)
            raise BaselineChanged(
                f"checkpoint '{cp_id}' baseline {cp['baseline']} != current {current_baseline}")
        self.audit.append("checkpoint.restored", cp_id=cp_id)
        return cp["payload"]

    # ---- CKP-01：恢复前四项校验 ----
    def pre_restore_check(self, cp_id, context):
        """
        context: {
            baseline,                 # 当前工作区基线 SHA
            authorization_valid: bool, # 授权仍有效（未过期/未吊销）
            policy_hash,              # 当前策略版本
            side_effects: [{"status": "CONFIRMED"|"UNKNOWN"|...}],
            compensable: bool         # 操作是否可补偿（不可逆=False）
        }
        返回 "RESUME"；条件不成立则暂停（不可补偿则升级为人工处置）。
        """
        cp = self._load(cp_id)
        problems = []

        if not context.get("authorization_valid"):
            problems.append("authorization_invalid")
        if cp.get("policy_hash") and context.get("policy_hash") != cp["policy_hash"]:
            problems.append(f"policy_drift:{cp['policy_hash']}->{context.get('policy_hash')}")
        if cp["baseline"] != context.get("baseline"):
            problems.append(f"baseline_drift:{cp['baseline']}->{context.get('baseline')}")
        for se in context.get("side_effects") or []:
            if se.get("status") != "CONFIRMED":
                problems.append(f"side_effect_{se.get('status', 'UNKNOWN')}")

        if not problems:
            self.audit.append("checkpoint.pre_restore_ok", cp_id=cp_id,
                              baseline=context.get("baseline"))
            return "RESUME"

        self.audit.append("checkpoint.paused_for_reevaluation", cp_id=cp_id,
                          problems=problems, compensable=bool(context.get("compensable")))
        if not context.get("compensable", True):
            self.audit.append("checkpoint.manual_remediation_required", cp_id=cp_id,
                              problems=problems)
            raise ManualRemediationRequired(
                f"checkpoint '{cp_id}' non-compensable and conditions unmet: {problems}")
        raise PausedForReevaluation(f"checkpoint '{cp_id}' paused: {problems}")
