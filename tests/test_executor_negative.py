# -*- coding: utf-8 -*-
"""治理执行器负向用例（v1.1.1 §13 的可执行版本）。

每个用例 = 一次真实注入 + 断言"被拒绝/被阻断"。
正向对照保证组件不是"永远拒绝"的假门禁。
"""
import json, tempfile, unittest
from pathlib import Path

from executor.lock import LockService, LockDenied, StaleFence
from executor.ledger import EffectLedger, DuplicateRejected, UnknownResult
from executor.memory import MemoryStore, InvalidTransition, CasConflict
from executor.checkpoint import CheckpointStore, Corrupted, BaselineChanged
from executor.breaker import CircuitBreaker, BreakerOpen
from executor.handoff import HandoffValidator, Rejected
from executor.contract import (TaskContractValidator, DeliveryReportValidator,
                               Rejected as ContractRejected)
from executor.attestation import (ApprovalAttestationValidator,
                                  Rejected as AttestationRejected)
from executor.change import RunRegistry, ChangeEvaluator, Rejected as ChangeRejected
from executor.approval import ApprovalGate, Rejected as ApprovalRejected
from executor.audit import AuditLog, AuditUnavailable


class ExecutorNegativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aasegs-exec-"))

    # ---- T-WF-05：任务契约要素缺失/占位/自批 → REJECT ----
    def _task(self):
        return {
            "task_id": "t-100", "owner": "agent-alpha", "risk_level": "R1",
            "objective": "把执行器契约校验接入 CI", "in_scope": ["executor/"],
            "out_of_scope": ["docs/"], "acceptance_criteria": ["负向用例全绿"],
            "dependencies": ["t-099"], "budget": "2h",
            "failure_policy": "fail_closed",
            "approval_proof": {"approver": "slow-is-fast",
                               "policy_hash": "policy-v1.1.1",
                               "expires_at": "2026-10-30T00:00:00Z"},
        }

    def test_t_wf_05_task_contract_rejects_incomplete(self):
        v = TaskContractValidator(self.tmp / "audit.jsonl")
        t = self._task()
        with self.assertRaises(ContractRejected):        # 缺必需字段
            v.validate({k: x for k, x in t.items() if k != "acceptance_criteria"})
        with self.assertRaises(ContractRejected):        # 占位值"TBD"
            v.validate({**t, "budget": "TBD"})
        with self.assertRaises(ContractRejected):        # 风险等级非法
            v.validate({**t, "risk_level": "R9"})
        with self.assertRaises(ContractRejected):        # 批准证明不完整
            v.validate({**t, "approval_proof": {"approver": "slow-is-fast"}})
        with self.assertRaises(ContractRejected):        # 作者自批（GOV-17/AGT-001）
            v.validate({**t, "approval_proof": {**t["approval_proof"],
                                                "approver": "agent-alpha"}})
        self.assertEqual(v.validate(t), "READY_FOR_APPROVAL")   # 正向对照

    # ---- T-WF-06：交付报告要素缺失/假 SHA/非法结案 → REJECT ----
    def _report(self):
        return {
            "task_id": "t-100", "run_id": "r-42",
            "change_summary": "新增契约校验模块", "paths": ["executor/contract.py"],
            "tests": ["tests/test_executor_negative.py"], "ci": "run 40843384135",
            "commit_sha": "71e2fd5" + "a" * 33,
            "review_verdict": "APPROVED by slow-is-fast",
            "known_risks": [], "approval_or_exception": "approval APR-7",
            "closure_result": "CLOSED",
        }

    def test_t_wf_06_delivery_report_rejects_incomplete(self):
        v = DeliveryReportValidator(self.tmp / "audit.jsonl")
        r = self._report()
        with self.assertRaises(ContractRejected):        # 缺 commit_sha
            v.validate({k: x for k, x in r.items() if k != "commit_sha"})
        with self.assertRaises(ContractRejected):        # 伪造 SHA
            v.validate({**r, "commit_sha": "zzz"})
        with self.assertRaises(ContractRejected):        # 结案结果非法
            v.validate({**r, "closure_result": "DONE"})
        with self.assertRaises(ContractRejected):        # known_risks 类型不对
            v.validate({**r, "known_risks": "none"})
        self.assertEqual(v.validate(r), "DELIVERED")     # 正向对照（空列表合法）

    # ---- T-WF-01：交接契约缺 policy_hash / 终态任务 → REJECT ----
    def test_t_wf_01_handoff_rejects_incomplete_contract(self):
        h = HandoffValidator("policy-v1.1.1", self.tmp / "audit.jsonl")
        base = {"handoff_id": "h-1", "task_id": "t-1", "source_run": "r-1",
                "destination_role": "Developer", "artifact_manifest": [],
                "policy_hash": "policy-v1.1.1", "validity": "2026-12-31"}
        with self.assertRaises(Rejected):                       # 缺 policy_hash
            h.validate({k: v for k, v in base.items() if k != "policy_hash"})
        with self.assertRaises(Rejected):                       # policy 不符
            h.validate({**base, "policy_hash": "policy-v1.0"})
        with self.assertRaises(Rejected):                       # 终态任务
            h.validate(base, task_state="CLOSED")
        self.assertEqual(h.validate(base), "ACCEPT")            # 正向对照

    # ---- T-WF-02：同一资源并发第二写者被拒 ----
    def test_t_wf_02_concurrent_holder_denied(self):
        lock = LockService(self.tmp / "locks.json", self.tmp / "audit.jsonl", ttl_seconds=30)
        f1 = lock.acquire("repo/main", "run-A")
        with self.assertRaises(LockDenied):                     # 未过期时不放锁
            lock.acquire("repo/main", "run-B")
        lock.validate_write("repo/main", f1)                    # 持有者写入合法

    # ---- T-CNC-01：锁过期/损坏时，旧持有者写不进、服务失败关闭 ----
    def test_t_cnc_01_stale_fence_and_fail_closed(self):
        lock = LockService(self.tmp / "locks.json", self.tmp / "audit.jsonl", ttl_seconds=30)
        f1 = lock.acquire("repo/main", "run-A")
        d = lock._load()
        d["repo/main"]["expires_at"] = 0
        lock.path.write_text(json.dumps(d), encoding="utf8")    # 模拟锁过期
        f3 = lock.acquire("repo/main", "run-B")                 # B 抢到更大 fence
        self.assertGreater(f3, f1)
        with self.assertRaises(StaleFence):                     # A 的旧 fence 写入被拒
            lock.validate_write("repo/main", f1)
        lock.path.write_text("{corrupted", encoding="utf8")     # 锁服务损坏
        with self.assertRaises(Exception):                      # 失败关闭：报错而非放行
            lock.acquire("repo/main", "run-C")
        with self.assertRaises(Exception):
            lock.validate_write("repo/main", f3)

    # ---- T-WF-03：幂等键重复投递被拒 ----
    def test_t_wf_03_duplicate_delivery_rejected(self):
        led = EffectLedger(self.tmp / "ledger.json", self.tmp / "audit.jsonl")
        led.submit("pr-create/task-7", {"title": "x"})
        led.confirm("pr-create/task-7")
        with self.assertRaises(DuplicateRejected):              # CONFIRMED 后重投
            led.submit("pr-create/task-7", {"title": "x"})
        rec, replayed = led.submit("pr-create/task-8", {"title": "y"})
        rec2, replayed2 = led.submit("pr-create/task-8", {"title": "y"})
        self.assertTrue(replayed2)                              # 并发重复返回既有，不重放

    # ---- T-EFF-01：UNKNOWN 后不得盲重放 ----
    def test_t_eff_01_unknown_blocks_replay(self):
        led = EffectLedger(self.tmp / "ledger.json", self.tmp / "audit.jsonl")
        led.submit("deploy/svc-1", {"env": "prod"})
        led.mark_unknown("deploy/svc-1")
        with self.assertRaises(UnknownResult):                  # 未知结果重放被阻断
            led.submit("deploy/svc-1", {"env": "prod"})
        led.reconcile("deploy/svc-1", confirmed=True)           # 核对真实结果后闭环
        led.reconcile is not None

    # ---- T-CTX-02：REVOKED 记忆不得进入规范性检索 ----
    def test_t_ctx_02_revoked_memory_not_returned(self):
        m = MemoryStore(self.tmp / "mem.json", self.tmp / "audit.jsonl")
        m.create("mem-1", author="agent-A", content="跳过测试以提速")
        m.submit_for_review("mem-1", 1)
        m.approve("mem-1", approver="human-owner")
        self.assertIn("mem-1", m.search("agent-B"))             # 撤销前可见
        m.revoke("mem-1", actor="human-owner")
        self.assertNotIn("mem-1", m.search("agent-B"))          # 撤销后即不可见

    # ---- T-CTX-03：未审核晋升被拒、作者自批被拒 ----
    def test_t_ctx_03_unreviewed_promotion_rejected(self):
        m = MemoryStore(self.tmp / "mem.json", self.tmp / "audit.jsonl")
        m.create("mem-2", author="agent-A", content="关闭扫描")
        with self.assertRaises(InvalidTransition):              # DRAFT 直接晋升被拒
            m.approve("mem-2", approver="human-owner")
        v = m.submit_for_review("mem-2", 1)
        with self.assertRaises(InvalidTransition):              # 作者自批被拒
            m.approve("mem-2", approver="agent-A")
        m.approve("mem-2", approver="human-owner")
        with self.assertRaises(CasConflict):                    # 过期版本 CAS 冲突
            m.submit_for_review("mem-2", 1)

    # ---- T-REC-01：基线变化的快照恢复被暂停 ----
    def test_t_rec_01_baseline_mismatch_pauses_restore(self):
        cp = CheckpointStore(self.tmp / "cp.json", self.tmp / "audit.jsonl")
        cp.save("cp-1", task="t-1", baseline="sha-aaa", payload={"step": 3})
        with self.assertRaises(Corrupted):                      # 不存在的快照
            cp.restore("cp-404", "sha-aaa", authorized=True)
        payload = cp.restore("cp-1", "sha-aaa", authorized=True)
        self.assertEqual(payload["step"], 3)
        with self.assertRaises(BaselineChanged):                # 基线变化 → 暂停
            cp.restore("cp-1", "sha-bbb", authorized=True)
        with self.assertRaises(BaselineChanged):                # 授权失效 → 暂停
            cp.restore("cp-1", "sha-aaa", authorized=False)

    # ---- T-REC-03：连续错误超阈值 → 熔断，拒绝新副作用 ----
    def test_t_rec_03_threshold_opens_breaker(self):
        b = CircuitBreaker(self.tmp / "brk.json", self.tmp / "audit.jsonl",
                           thresholds={"network_error": 3})
        for _ in range(2):
            self.assertFalse(b.record("network_error"))
        self.assertTrue(b.allow("call-api"))                    # 阈值内仍放行
        self.assertTrue(b.record("network_error"))              # 第 3 次 → 熔断
        with self.assertRaises(BreakerOpen):                    # 新副作用被拒
            b.allow("call-api")

    # ---- T-BRK-01：严重越权立即熔断，不等阈值 ----
    def test_t_brk_01_severe_violation_opens_immediately(self):
        b = CircuitBreaker(self.tmp / "brk.json", self.tmp / "audit.jsonl")
        self.assertTrue(b.allow("write-file"))                  # 初始放行
        self.assertTrue(b.record("privilege_escalation", severity="severe"))
        with self.assertRaises(BreakerOpen):                    # 单次即熔断
            b.allow("write-file")

    # ---- T-ATT-01：同一 Agent 假扮人工批准 / 带内证明 / 未知主体 → REJECT ----
    def _att(self):
        return {
            "task_id": "t-200", "approver_principal": "slow-is-fast",
            "principal_type": "human", "decision": "APPROVED",
            "attestation_ref": "https://github.com/slow-is-fast/engineering_manager/pull/4",
            "channel": "pr_review", "issued_at": "2026-10-29T16:00:00Z",
            "policy_hash": "policy-v1.1.1",
        }

    def test_t_att_01_fake_human_approval_rejected(self):
        v = ApprovalAttestationValidator({"slow-is-fast", "reviewer-b"},
                                         "policy-v1.1.1",
                                         self.tmp / "audit.jsonl")
        a = self._att()
        with self.assertRaises(AttestationRejected):      # Agent 冒充人类主体
            v.validate({**a, "approver_principal": "agent-alpha"})
        with self.assertRaises(AttestationRejected):      # 主体类型非人类
            v.validate({**a, "principal_type": "agent"})
        with self.assertRaises(AttestationRejected):      # 主体不在人类白名单
            v.validate({**a, "approver_principal": "someone-else"})
        with self.assertRaises(AttestationRejected):      # 带内（自证）通道
            v.validate({**a, "channel": "self"})
        with self.assertRaises(AttestationRejected):      # 旁证不可核查
            v.validate({**a, "attestation_ref": "trust me"})
        with self.assertRaises(AttestationRejected):      # 缺字段
            v.validate({k: x for k, x in a.items() if k != "issued_at"})
        with self.assertRaises(AttestationRejected):      # 策略不符
            v.validate({**a, "policy_hash": "policy-v1.0"})
        self.assertEqual(v.validate(a), "APPROVED_BY_HUMAN")   # 正向对照

    # ---- T-CHG-01：变更策略未处置活动 Run / 重大热修复仍 continue / 重授权不符 → REJECT ----
    def _registry(self):
        reg = RunRegistry(self.tmp / "audit.jsonl")
        reg.register("r-1", "t-300", "policy-v1.1.0", owner="agent-alpha")
        reg.register("r-2", "t-301", "policy-v1.1.0", owner="agent-beta")
        reg.register("r-3", "t-302", "policy-v1.1.1", owner="agent-gamma")  # 已是新策略，不受影响
        return reg

    def test_t_chg_01_change_without_disposition_rejected(self):
        reg = self._registry()
        ev = ChangeEvaluator(reg, self.tmp / "audit.jsonl")
        new = "policy-v1.1.1"
        with self.assertRaises(ChangeRejected):            # 完全不给处置决定
            ev.evaluate(new, {}, change_id="chg-1")
        with self.assertRaises(ChangeRejected):            # 只处置了一个 Run，漏了另一个
            ev.evaluate(new, {"r-1": "pause"}, change_id="chg-1")
        with self.assertRaises(ChangeRejected):            # 处置值非法
            ev.evaluate(new, {"r-1": "whatever", "r-2": "pause"}, change_id="chg-1")
        # 重大安全热修复：continue 不被允许（GOV-16 核心）
        with self.assertRaises(ChangeRejected):
            ev.evaluate(new, {"r-1": "continue", "r-2": "pause"},
                        severe=True, change_id="chg-hotfix")
        # reauthorize 缺审批证明 / 策略不符 / Agent 自批
        with self.assertRaises(ChangeRejected):
            ev.evaluate(new, {"r-1": "reauthorize", "r-2": "pause"}, change_id="chg-2")
        with self.assertRaises(ChangeRejected):
            ev.evaluate(new, {"r-1": {"decision": "reauthorize",
                                      "approval": {"approver": "slow-is-fast",
                                                   "policy_hash": "policy-v1.0"}},
                              "r-2": "pause"}, change_id="chg-3")
        with self.assertRaises(ChangeRejected):
            ev.evaluate(new, {"r-1": {"decision": "reauthorize",
                                      "approval": {"approver": "agent-alpha",
                                                   "policy_hash": new}},
                              "r-2": "pause"}, change_id="chg-4")
        # 正向对照：合法处置全部给出
        res = ev.evaluate(new, {"r-1": {"decision": "reauthorize",
                                        "approval": {"approver": "slow-is-fast",
                                                     "policy_hash": new}},
                                "r-2": "pause"}, change_id="chg-ok")
        self.assertEqual(res["result"], "PUBLISHED")
        self.assertEqual(res["affected"], ["r-1", "r-2"])   # r-3 已是新策略，不在列


    # ---- T-APR-01：审批过期/绑定漂移/范围扩张/风险升级/吊销/R3 仅 AI PASS → REJECT ----
    def _gate(self):
        g = ApprovalGate({"slow-is-fast"}, self.tmp / "audit.jsonl")
        g.grant("apr-1", "slow-is-fast", "t-400", "R1", ["executor/", "tests/"],
                "policy-v1.1.1", commit_sha="abc1234",
                expires_at="2026-10-30T00:00:00+00:00", channel="pr_review")
        return g

    def _req(self, **over):
        base = {"task_id": "t-400", "risk": "R1", "scope": ["executor/"],
                "policy_hash": "policy-v1.1.1", "commit_sha": "abc1234"}
        base.update(over)
        return base

    def test_t_apr_01_approval_gate_rejects_drift(self):
        g = self._gate()
        now = "2026-10-29T12:00:00+00:00"
        with self.assertRaises(ApprovalRejected):            # 未知审批
            g.validate("apr-999", self._req(), now=now)
        with self.assertRaises(ApprovalRejected):            # 过期
            g.validate("apr-1", self._req(), now="2026-11-01T00:00:00+00:00")
        with self.assertRaises(ApprovalRejected):            # commit 漂移
            g.validate("apr-1", self._req(commit_sha="def5678"), now=now)
        with self.assertRaises(ApprovalRejected):            # 范围扩张
            g.validate("apr-1", self._req(scope=["executor/", "infra/"]), now=now)
        with self.assertRaises(ApprovalRejected):            # 风险升级未重批
            g.validate("apr-1", self._req(risk="R3"), now=now)
        with self.assertRaises(ApprovalRejected):            # 策略版本漂移
            g.validate("apr-1", self._req(policy_hash="policy-v1.0"), now=now)
        with self.assertRaises(ApprovalRejected):            # task 漂移
            g.validate("apr-1", self._req(task_id="t-401"), now=now)
        g.revoke("apr-1", reason="drill")
        with self.assertRaises(ApprovalRejected):            # 吊销
            g.validate("apr-1", self._req(), now=now)
        # 签发给非人类主体（GOV-17）
        g2 = ApprovalGate({"slow-is-fast"}, self.tmp / "audit.jsonl")
        with self.assertRaises(ApprovalRejected):
            g2.grant("apr-2", "agent-alpha", "t-400", "R1", ["executor/"],
                     "policy-v1.1.1")
        # SEC-009：R3 仅 AI Reviewer PASS 不放行（须人类通道）
        g3 = ApprovalGate({"slow-is-fast"}, self.tmp / "audit.jsonl")
        g3.grant("apr-3", "slow-is-fast", "t-500", "R3", ["prod/"],
                 "policy-v1.1.1", channel="prompt")
        with self.assertRaises(ApprovalRejected):
            g3.validate("apr-3", {"task_id": "t-500", "risk": "R3",
                                  "scope": ["prod/"], "policy_hash": "policy-v1.1.1"},
                        now=now, ai_verdict="PASS")
        # 正向对照：绑定一致 + 人类带外通道（R3 亦放行）
        g4 = ApprovalGate({"slow-is-fast"}, self.tmp / "audit.jsonl")
        g4.grant("apr-4", "slow-is-fast", "t-400", "R3", ["executor/"],
                 "policy-v1.1.1", channel="pr_review")
        self.assertEqual(g4.validate("apr-4", {"task_id": "t-400", "risk": "R3",
                                               "scope": ["executor/"],
                                               "policy_hash": "policy-v1.1.1"},
                                     now=now, ai_verdict="PASS"), "APPROVED")


    # ---- T-EVD-01：审计哈希链篡改/删行/截断必须被检出 ----
    def test_t_evd_01_chain_tamper_detected(self):
        path = self.tmp / "audit.jsonl"
        log = AuditLog(path)
        log.append("a.one", x=1)
        log.append("a.two", x=2)
        log.append("a.three", x=3)
        ok, errs = log.verify()
        self.assertTrue(ok, f"原始链应通过: {errs}")          # 正向对照

        lines = path.read_text(encoding="utf8").splitlines()

        # ① 篡改中间一条的内容
        e = json.loads(lines[1]); e["x"] = 999
        lines[1] = json.dumps(e, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf8")
        ok, errs = log.verify()
        self.assertFalse(ok, "篡改内容未被检出")
        self.assertTrue(any("hash mismatch" in x for x in errs), errs)

        # ② 删除中间一条（链断裂）
        lines = path.read_text(encoding="utf8").splitlines()
        del lines[1]
        path.write_text("\n".join(lines) + "\n", encoding="utf8")
        ok, errs = log.verify()
        self.assertFalse(ok, "删行未被检出")

        # ③ 重排两条
        lines = path.read_text(encoding="utf8").splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        path.write_text("\n".join(lines) + "\n", encoding="utf8")
        ok, _ = log.verify()
        self.assertFalse(ok, "重排未被检出")

    # ---- T-EVD-02：审计不可用/损坏时失败关闭，不得静默 ----
    def test_t_evd_02_audit_unavailable_fails_closed(self):
        missing = AuditLog(self.tmp / "nope" / "audit.jsonl")
        with self.assertRaises(AuditUnavailable):              # 文件缺失 + strict
            missing.read(strict=True)
        with self.assertRaises(AuditUnavailable):
            missing.ensure_available()

        path = self.tmp / "audit2.jsonl"
        log = AuditLog(path)
        log.append("b.one", y=1)
        log.append("b.two", y=2)
        self.assertTrue(log.ensure_available())                # 正向对照

        path.write_text('{"broken":\n', encoding="utf8")       # 损坏
        with self.assertRaises(AuditUnavailable):
            log.read(strict=True)
        ok, errs = log.verify()
        self.assertFalse(ok, "损坏未被检出")
        self.assertTrue(any("corrupt" in x for x in errs), errs)


if __name__ == "__main__":
    unittest.main(verbosity=2)

    # ---- T-ATT-01：同一 Agent 假扮人工批准 / 带内证明 / 未知主体 → REJECT ----
    def _att(self):
        return {
            "task_id": "t-200", "approver_principal": "slow-is-fast",
            "principal_type": "human", "decision": "APPROVED",
            "attestation_ref": "https://github.com/slow-is-fast/engineering_manager/pull/4",
            "channel": "pr_review", "issued_at": "2026-10-29T16:00:00Z",
            "policy_hash": "policy-v1.1.1",
        }

    def test_t_att_01_fake_human_approval_rejected(self):
        v = ApprovalAttestationValidator({"slow-is-fast", "reviewer-b"},
                                         "policy-v1.1.1",
                                         self.tmp / "audit.jsonl")
        a = self._att()
        with self.assertRaises(AttestationRejected):      # Agent 冒充人类主体
            v.validate({**a, "approver_principal": "agent-alpha"})
        with self.assertRaises(AttestationRejected):      # 主体类型非人类
            v.validate({**a, "principal_type": "agent"})
        with self.assertRaises(AttestationRejected):      # 主体不在人类白名单
            v.validate({**a, "approver_principal": "someone-else"})
        with self.assertRaises(AttestationRejected):      # 带内（自证）通道
            v.validate({**a, "channel": "self"})
        with self.assertRaises(AttestationRejected):      # 旁证不可核查
            v.validate({**a, "attestation_ref": "trust me"})
        with self.assertRaises(AttestationRejected):      # 缺字段
            v.validate({k: x for k, x in a.items() if k != "issued_at"})
        with self.assertRaises(AttestationRejected):      # 策略不符
            v.validate({**a, "policy_hash": "policy-v1.0"})
        self.assertEqual(v.validate(a), "APPROVED_BY_HUMAN")   # 正向对照
