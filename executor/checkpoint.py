# -*- coding: utf-8 -*-
"""executor.checkpoint —— Checkpoint 存储与恢复前校验（CKP-01 简化实现）。

规则（v1.1.1 §7）：
- 保存时对 (baseline, payload) 计算完整性摘要，摘要与内容绑定；
- 摘要不匹配 = 快照损坏 → 拒绝恢复；
- 恢复前必须核对：当前基线与快照基线一致、授权仍有效；
- 基线/授权/策略变化 → 暂停（PAUSE），不得直接续写。
"""
import hashlib, json
from pathlib import Path
from .audit import AuditLog


class Corrupted(Exception):
    pass


class BaselineChanged(Exception):
    pass


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

    def save(self, cp_id, task, baseline, payload):
        d = json.loads(self.path.read_text(encoding="utf8"))
        d[cp_id] = {"task": task, "baseline": baseline,
                    "payload": payload, "digest": self.digest(baseline, payload)}
        self.path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf8")
        self.audit.append("checkpoint.saved", cp_id=cp_id, task=task, baseline=baseline)
        return d[cp_id]["digest"]

    def restore(self, cp_id, current_baseline, authorized: bool):
        d = json.loads(self.path.read_text(encoding="utf8"))
        cp = d.get(cp_id)
        if not cp:
            self.audit.append("checkpoint.restore_denied", cp_id=cp_id, reason="missing")
            raise Corrupted(f"checkpoint '{cp_id}' not found")
        if self.digest(cp["baseline"], cp["payload"]) != cp["digest"]:
            self.audit.append("checkpoint.restore_denied", cp_id=cp_id, reason="corrupted")
            raise Corrupted(f"checkpoint '{cp_id}' digest mismatch")
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
