# -*- coding: utf-8 -*-
"""executor.evidencepack —— 试点证据包与报告可复现性（PKG-01）。

规则：AASEGS-GOV-19（P1）要求十项试点任务可核验；PKG-01 要求每次试点产出一个
统一证据包：**环境与版本、风险范围、控制状态快照、用例结果、原始证据引用、
失败与例外、owner、复验记录、批准结论**。

语义（失败关闭）：
  1. 九类必填段落缺一 → 不得构建证据包（`PackRejected`）；
  2. 每条用例结果必须带 `evidence_ref` 与 `reproduce_cmd`——"报告可复现每项测试"；
     缺一即拒；
  3. 每条失败必须映射到 `issue_id` + `owner`——"失败映射到问题 ID/负责人"；
  4. **无证据不得通过**：`claim_pass()` 必须基于已封存且校验通过的证据包，
     没有证据包就宣称试点通过 → 拒绝；
  5. 封存用内容哈希（`seal`），改动任何字段后 `verify_seal` 必须失败——
     防止"先封存再悄悄改结论"。

诚实边界：哈希封存只保证**可检测**篡改，不保证不可篡改（写权限仍在持有者手里）；
本模块不判定证据内容真假，只判定"该有的都有、引用对得上、封存后没被动过"。
"""
import hashlib
import json

from .audit import AuditLog

REQUIRED_SECTIONS = ("environment", "versions", "risk_scope", "control_snapshot",
                     "test_results", "failures", "exceptions", "reverification",
                     "approval")
RESULT_VERDICTS = ("PASS", "FAIL", "SKIPPED")


class PackRejected(Exception):
    pass


def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


class EvidencePack:
    def __init__(self, payload, audit_path):
        self.payload = dict(payload)
        self.audit = AuditLog(audit_path)
        self.sealed_digest = None

    # ---------------- 构建即校验 ----------------
    @classmethod
    def build(cls, payload, audit_path):
        # 注意：`failures`/`exceptions` 允许为空列表（"本次没有失败"是合法结论），
        # 但**键必须存在**——用"缺键"和"空"区分"没写"和"没有"。
        missing = []
        for s in REQUIRED_SECTIONS:
            if s not in payload or payload[s] is None or payload[s] == "":
                missing.append(s)
            elif isinstance(payload[s], dict) and not payload[s]:
                missing.append(s)
        if missing:
            raise PackRejected(f"missing_sections: {missing}")
        pack = cls(payload, audit_path)
        pack._validate_results()
        pack._validate_failures()
        pack.audit.append("pack.built", sections=len(REQUIRED_SECTIONS),
                          tests=len(payload["test_results"]),
                          failures=len(payload["failures"]))
        return pack

    def _validate_results(self):
        seen = set()
        for r in self.payload["test_results"]:
            rid = r.get("id")
            if not rid:
                raise PackRejected("test_result_without_id")
            if rid in seen:
                raise PackRejected(f"duplicate_test_result: {rid}")
            seen.add(rid)
            if r.get("verdict") not in RESULT_VERDICTS:
                raise PackRejected(f"{rid}: unknown verdict {r.get('verdict')}")
            # 报告可复现每项测试：必须有证据引用与复现命令
            if not r.get("evidence_ref"):
                raise PackRejected(f"{rid}: evidence_ref required")
            if not r.get("reproduce_cmd"):
                raise PackRejected(f"{rid}: reproduce_cmd required")
            if r["verdict"] == "PASS" and r.get("evidence_ref") in ("none", "-"):
                raise PackRejected(f"{rid}: PASS without real evidence")

    def _validate_failures(self):
        for f in self.payload["failures"]:
            if not f.get("issue_id"):
                raise PackRejected("failure_without_issue_id")
            if not f.get("owner"):
                raise PackRejected(f"{f.get('issue_id')}: failure_without_owner")

    # ---------------- 封存与校验 ----------------
    def seal(self):
        body = {k: v for k, v in self.payload.items() if k != "seal"}
        self.sealed_digest = hashlib.sha256(_canon(body).encode("utf8")).hexdigest()
        self.payload["seal"] = self.sealed_digest
        self.audit.append("pack.sealed", digest=self.sealed_digest)
        return self.sealed_digest

    def verify_seal(self):
        if not self.payload.get("seal"):
            raise PackRejected("pack_not_sealed")
        body = {k: v for k, v in self.payload.items() if k != "seal"}
        actual = hashlib.sha256(_canon(body).encode("utf8")).hexdigest()
        if actual != self.payload["seal"]:
            self.audit.append("pack.tampered", expected=self.payload["seal"],
                              actual=actual)
            raise PackRejected("seal_mismatch")
        return True

    # ---------------- 结论 ----------------
    def claim_pass(self, conclusion):
        """无证据不得通过：必须基于封存且校验通过的证据包。"""
        if self.payload.get("seal") is None:
            raise PackRejected("claim_pass_without_sealed_pack")
        self.verify_seal()
        blocking = [r["id"] for r in self.payload["test_results"]
                    if r.get("verdict") == "FAIL"]
        if blocking:
            raise PackRejected(f"cannot_claim_pass_with_failures: {blocking}")
        blocked_issues = [f["issue_id"] for f in self.payload["failures"]]
        if blocked_issues:
            raise PackRejected(f"cannot_claim_pass_with_open_failures: {blocked_issues}")
        self.payload["approval"] = {**dict(self.payload.get("approval") or {}),
                                    "conclusion": conclusion}
        self.audit.append("pack.pass_claimed", conclusion=conclusion,
                          digest=self.payload["seal"])
        return {"conclusion": conclusion, "digest": self.payload["seal"]}

    def to_json(self):
        return json.dumps(self.payload, ensure_ascii=False, indent=2)
