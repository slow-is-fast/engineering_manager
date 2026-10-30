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
from executor.scope import ScopeGuard, Denied as ScopeDenied
from executor.credential import CredentialGuard, Denied as CredDenied
from executor.incident import IncidentWorkflow, Rejected as IncidentRejected
from executor.gate import AdmissionGate, GateInputError, AdmissionDenied
from datetime import date

from executor.checkpoint import (CheckpointStore, BaselineChanged,
                                 PausedForReevaluation as CkpPaused,
                                 ManualRemediationRequired as CkpManual)


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


    # ---- T-ISO-01：跨项目/跨租户访问默认拒绝，未绑定与通配范围亦拒绝 ----
    def test_t_iso_01_cross_project_access_denied(self):
        g = ScopeGuard(self.tmp / "audit.jsonl")
        g.bind("r-10", "proj-a", "repo-a", "tenant-1")

        with self.assertRaises(ScopeDenied):          # 未绑定的 Run
            g.access("r-unknown", {"project_id": "proj-a", "tenant_id": "tenant-1"})
        with self.assertRaises(ScopeDenied):          # 跨项目读制品/记忆
            g.access("r-10", {"project_id": "proj-b", "tenant_id": "tenant-1",
                              "path": "memory/shared.md"})
        with self.assertRaises(ScopeDenied):          # 跨租户
            g.access("r-10", {"project_id": "proj-a", "tenant_id": "tenant-2"})
        with self.assertRaises(ScopeDenied):          # 跨仓库
            g.access("r-10", {"project_id": "proj-a", "tenant_id": "tenant-1",
                              "repository_id": "repo-b"})
        with self.assertRaises(ScopeDenied):          # 通配范围（越权常见手法）
            g.access("r-10", {"project_id": "*", "tenant_id": "tenant-1"})
        with self.assertRaises(ScopeDenied):          # 目标缺租户标识
            g.access("r-10", {"project_id": "proj-a"})
        # 正向对照：同项目/同租户/同仓库，未分类数据按最高敏感处理
        self.assertEqual(g.access("r-10", {"project_id": "proj-a",
                                           "tenant_id": "tenant-1",
                                           "repository_id": "repo-a",
                                           "path": "artifacts/x.json"}), "ALLOWED")
        ev = AuditLog(self.tmp / "audit.jsonl").read()
        kinds = [e["event_type"] for e in ev]
        self.assertIn("boundary_violation", kinds)              # 违规已记录
        self.assertIn("data.unclassified_defaults_to_max", kinds)  # 未分类按最高


    # ---- T-CKP-01：恢复前四项校验，任一不成立即暂停；不可补偿则人工处置 ----
    def test_t_ckp_01_pre_restore_checks(self):
        store = CheckpointStore(self.tmp / "cp.json", self.tmp / "audit.jsonl")
        store.save("cp-1", "t-600", "base-AAA", {"step": 3}, policy_hash="policy-v1.1.1")

        ok_ctx = {"baseline": "base-AAA", "authorization_valid": True,
                  "policy_hash": "policy-v1.1.1",
                  "side_effects": [{"status": "CONFIRMED"}], "compensable": True}
        self.assertEqual(store.pre_restore_check("cp-1", ok_ctx), "RESUME")  # 正向对照

        with self.assertRaises(CkpPaused):        # 基线漂移（T-CKP-01 用例原文）
            store.pre_restore_check("cp-1", {**ok_ctx, "baseline": "base-BBB"})
        with self.assertRaises(CkpPaused):        # 授权失效
            store.pre_restore_check("cp-1", {**ok_ctx, "authorization_valid": False})
        with self.assertRaises(CkpPaused):        # 策略漂移
            store.pre_restore_check("cp-1", {**ok_ctx, "policy_hash": "policy-v1.1.2"})
        with self.assertRaises(CkpPaused):        # 外部副作用未决（UNKNOWN）
            store.pre_restore_check("cp-1", {**ok_ctx,
                                             "side_effects": [{"status": "UNKNOWN"}]})
        with self.assertRaises(CkpManual):        # 不可补偿 + 条件不成立 → 人工处置
            store.pre_restore_check("cp-1", {**ok_ctx, "baseline": "base-BBB",
                                             "compensable": False})
        # 暂停后不得续写：restore 仍会因基线不符拒绝
        with self.assertRaises(BaselineChanged):
            store.restore("cp-1", "base-BBB", authorized=True)
        # 条件恢复后可正常恢复
        self.assertEqual(store.restore("cp-1", "base-AAA", authorized=True)["step"], 3)


    # ---- T-GATE-01：准入门槛机器判定（GATE-01 / AUD-020） ----
    # 夹具为自包含的合成治理仓库，不依赖任何真实仓库路径（控制面 CI 无数据面检出）。
    _seq = 0
    _NOW = date(2026, 10, 30)

    def _ctl(self, cid, risk, tested=True, verified=True,
             evidence_at="2026-10-30", **over):
        c = {
            "id": cid, "requirement_ref": cid, "source_ref": "fixture",
            "risk_level": risk, "addresses": [],
            "owner": "human_owner", "enforcer": "fixture_enforcer",
            "evidence": "fixture evidence", "failure": "deny (fail closed)",
            "test": "T-" + cid, "status": "tested",
            "state": {"documented": True, "configured": True,
                      "tested": tested, "verified": verified,
                      "degraded": False, "excepted": False},
            "integration_evidence_uri": "evidence/fixture.md",
            "evidence_at": evidence_at,
        }
        c.update(over)
        return c

    def _exc(self, cid, *, requirement=("tested",), approver_type="human",
             expires="2027-01-01", compensating=("fixture 补偿控制",),
             status="ACTIVE", revocation="fixture revocation condition"):
        return {"id": "EXC-T", "status": status, "approver": "slow-is-fast",
                "approver_type": approver_type, "created": "2026-10-01",
                "expires": expires, "scope": "fixture",
                "waives": {"controls": [cid], "audit_issues": [],
                           "requirement": list(requirement)},
                "compensating_controls": list(compensating),
                "revocation": revocation}

    def _gate_repo(self, *, issue_status=("CLOSED", "CLOSED", "CLOSED"),
                   sec2a_sev=("P0", "P0", "P1"), exceptions=None,
                   controls=None, drop=(), sec12=None):
        type(self)._seq += 1
        base = self.tmp / ("gate-repo-%d" % type(self)._seq)
        (base / "governance").mkdir(parents=True)
        (base / ".github" / "workflows").mkdir(parents=True)

        spec = {"REG-01": "P1", "CTA-01": "P0", "GATE-01": "P0",
                "CTB-01": "P1", "CTX-01": "P0", "MTR-01": "P2"}
        ctl_list = []
        for cid, risk in spec.items():
            kw = dict((controls or {}).get(cid, {}))
            ctl_list.append(self._ctl(cid, risk, **kw))

        matrix = {
            "version": "1.0.0",
            "evaluation_model": {"unwaivable": ["GATE-01"]},
            "evidence_ttl_days": {"P0": 30, "P1": 90, "P2": 180, "_unknown": 30},
            "levels": {
                "G0": {"title": "指令", "criteria": {}},
                "G1": {"title": "流程+CI", "criteria": {
                    "catalog_schema_valid": True, "ci_gate_present": True,
                    "controls_tested": ["REG-01"]}},
                "G2": {"title": "身份/隔离/审批", "criteria": {
                    "controls_tested": ["CTA-01", "GATE-01"],
                    "require_fresh_evidence": True, "max_open_p0_issues": 0}},
                "G3": {"title": "审计/恢复", "criteria": {
                    "controls_tested": ["CTB-01"],
                    "require_fresh_evidence": True,
                    "all_p0_controls_tested": True, "max_open_p1_issues": 0}},
                "G4": {"title": "持续改进", "criteria": {
                    "controls_tested": ["MTR-01"],
                    "require_fresh_evidence": True,
                    "all_p0_controls_verified": True,
                    "all_p1_controls_tested": True,
                    "max_active_exceptions": 0, "max_open_issues_total": 0}},
            },
            "risk_admission": {
                "R0": {"min_level": "G2", "case_review": False},
                "R1": {"min_level": "G2", "case_review": False},
                "R2": {"min_level": "G3", "case_review": True},
                "R3": {"min_level": "G4", "case_review": True},
            },
        }

        rows = "\n".join(
            "| AUD-10%d | %s | %s | fixture |" % (i + 1, sec2a_sev[i], issue_status[i])
            for i in range(3))
        sec4_sev = ("P0", "P0", "P1")
        blocks = "\n\n".join(
            "### AASEGS-AUD-10%d --- fixture issue\n\n"
            "-   **问题 ID：** AASEGS-AUD-10%d\n"
            "-   **严重程度：** **%s**" % (i + 1, i + 1, sec4_sev[i])
            for i in range(3))
        audit_md = (
            "# 审计问题清单（合成夹具）\n\n登记 3 个问题。\n\n"
            "## 二·A · Owner 分配记录\n\n"
            "| 问题 ID | 严重程度 | 状态 | 备注 |\n|---|---|---|---|\n"
            + rows + "\n\n## 三、严重程度准入关系\n\n（略）\n\n"
            "## 四、逐项问题登记\n\n" + blocks + "\n")

        def write(rel, text):
            if rel in drop:
                return
            p = base / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")

        write("governance/maturity_matrix.json",
              json.dumps(matrix, ensure_ascii=False, indent=2))
        write("control-catalog.yaml",
              json.dumps({"version": "1.1.1", "controls": ctl_list},
                         ensure_ascii=False, indent=2))
        write("rule-registry.json",
              json.dumps({"version": "1.1.1",
                          "rules": [{"rule_id": "GOV-09", "risk_level": "P1"}]},
                         ensure_ascii=False, indent=2))
        write("AASEGS_Audit_Issues_Full.md", audit_md)
        if exceptions is not None:
            write("governance/exception_register.json",
                  json.dumps({"exceptions": exceptions}, ensure_ascii=False, indent=2))
        if sec12 is not None:
            write("AASEGS_v1.1.1_实施完整性修订版.md",
                  "### 12.1 条款到控制的映射\n\n"
                  "| 审计问题 | 严重度 | 标题 | 补充条款 | Control ID | 条款覆盖 | 关闭状态 |\n"
                  "|---|---|---|---|---|---|---|\n" + sec12 + "\n\n### 12.2 覆盖不等于关闭\n")
        write(".github/workflows/governance.yml",
              "name: governance\nsteps:\n- run: python scripts/validate_controls.py\n")
        return base

    def test_t_gate_01_untested_p0_control_blocks_r0(self):
        base = self._gate_repo(controls={"CTA-01": {"tested": False}})
        g = AdmissionGate(base, now=self._NOW).load()
        d = g.admit("R0")
        self.assertEqual(d["decision"], "DENY")
        self.assertTrue(any("level_insufficient" in r for r in d["reasons"]))
        self.assertIn("CTA-01", [b["id"] for b in d["blockers"]])

    def test_t_gate_01_open_p0_issue_blocks_admission(self):
        base = self._gate_repo(issue_status=("OPEN", "CLOSED", "CLOSED"))
        g = AdmissionGate(base, now=self._NOW).load()
        d = g.admit("R0")
        self.assertEqual(d["decision"], "DENY")
        self.assertIn("AUD-101", [b["id"] for b in d["blockers"]])

    def test_t_gate_01_invalid_exceptions_not_honored(self):
        # 例外缺任一要件（到期/无补偿控制/Agent 批准人/无撤销条件）→ 一律不采信
        bad = [
            self._exc("CTA-01", expires="2020-01-01"),
            self._exc("CTA-01", compensating=()),
            self._exc("CTA-01", approver_type="agent"),
            self._exc("CTA-01", revocation=""),
        ]
        for exc in bad:
            base = self._gate_repo(controls={"CTA-01": {"tested": False}},
                                   exceptions=[exc])
            g = AdmissionGate(base, now=self._NOW).load()
            d = g.admit("R0")
            self.assertEqual(d["decision"], "DENY", f"exception wrongly honored: {exc}")
            self.assertIn("CTA-01", [b["id"] for b in d["blockers"]])
            self.assertEqual(d["waivers"], [])

    def test_t_gate_01_valid_exception_restores_admission(self):
        # 有效例外豁免 tested 要求 → R0 恢复 ALLOW；但 verified 未豁免 → R3 仍 DENY
        base = self._gate_repo(controls={"CTA-01": {"tested": False,
                                                    "verified": False}},
                               exceptions=[self._exc("CTA-01")])
        g = AdmissionGate(base, now=self._NOW).load()
        d0 = g.admit("R0")
        self.assertEqual(d0["decision"], "ALLOW")
        self.assertEqual(d0["actual_level"], "G3")
        self.assertEqual(d0["waivers"],
                         [{"control": "CTA-01", "requirement": "tested",
                           "by": "EXC-T", "level": "G2"}])
        d3 = g.admit("R3", case_review={"approval_ref": "CR-1",
                                        "approver": "slow-is-fast",
                                        "principal_type": "human"})
        self.assertEqual(d3["decision"], "DENY")
        self.assertIn("CTA-01", [b["id"] for b in d3["blockers"]])

    def test_t_gate_01_gate_control_unwaivable(self):
        # 例外试图豁免 GATE-01（判定器自身）→ 不予采信，仍阻断
        base = self._gate_repo(controls={"GATE-01": {"tested": False}},
                               exceptions=[self._exc("GATE-01")])
        g = AdmissionGate(base, now=self._NOW).load()
        d = g.admit("R0")
        self.assertEqual(d["decision"], "DENY")
        self.assertIn("GATE-01", [b["id"] for b in d["blockers"]])
        self.assertEqual(d["waivers"], [])

    def test_t_gate_01_verified_waiver_cannot_satisfy_tested(self):
        # waives.requirement=["verified"] 的例外不得用于豁免 tested 要求
        base = self._gate_repo(controls={"CTA-01": {"tested": False,
                                                    "verified": False}},
                               exceptions=[self._exc("CTA-01",
                                                     requirement=("verified",))])
        g = AdmissionGate(base, now=self._NOW).load()
        d = g.admit("R0")
        self.assertEqual(d["decision"], "DENY")
        self.assertIn("CTA-01", [b["id"] for b in d["blockers"]])

    def test_t_gate_01_stale_evidence_not_counted(self):
        # tested 但证据过期（P0 TTL=30 天，age=40 天）→ 不计入
        base = self._gate_repo(controls={"CTA-01": {"evidence_at": "2026-09-20"}})
        g = AdmissionGate(base, now=self._NOW).load()
        d = g.admit("R0")
        self.assertEqual(d["decision"], "DENY")
        stale = [b for b in d["blockers"] if b["id"] == "CTA-01"]
        self.assertTrue(stale)
        self.assertEqual(stale[0]["reason"], "stale_evidence")

    def test_t_gate_01_missing_inputs_fail_closed(self):
        # 任一必填输入缺失 → 失败关闭，不给出准入结论
        for rel in ("governance/maturity_matrix.json", "control-catalog.yaml",
                    "rule-registry.json", "AASEGS_Audit_Issues_Full.md"):
            base = self._gate_repo(drop=(rel,))
            with self.assertRaises(GateInputError):
                AdmissionGate(base, now=self._NOW).load()

    def test_t_gate_01_severity_conflict_fails_closed(self):
        # 同一问题在三处事实源严重程度不一致 → 失败关闭，而非任选其一
        base = self._gate_repo(sec2a_sev=("P1", "P0", "P1"))
        with self.assertRaises(GateInputError) as cm:
            AdmissionGate(base, now=self._NOW).load()
        self.assertIn("AUD-101", str(cm.exception))

        base2 = self._gate_repo(sec12="| AUD-102 | P1 | t | s | c | y | z |")
        with self.assertRaises(GateInputError) as cm2:
            AdmissionGate(base2, now=self._NOW).load()
        self.assertIn("AUD-102", str(cm2.exception))

    def test_t_gate_01_r2_r3_require_human_case_review(self):
        base = self._gate_repo()
        g = AdmissionGate(base, now=self._NOW).load()
        # 等级达标但缺逐案评审 → 拒绝
        d1 = g.admit("R2")
        self.assertEqual(d1["decision"], "DENY")
        self.assertTrue(any("case_review_required" in r for r in d1["reasons"]))
        # 逐案评审由 Agent 主体批准 → 拒绝
        d2 = g.admit("R3", case_review={"approval_ref": "CR-1",
                                        "approver": "agent-alpha",
                                        "principal_type": "agent"})
        self.assertEqual(d2["decision"], "DENY")
        self.assertTrue(any("case_review" in r for r in d2["reasons"]))
        # 人类主体逐案评审 → 放行
        d3 = g.admit("R2", case_review={"approval_ref": "CR-1",
                                        "approver": "slow-is-fast",
                                        "principal_type": "human"})
        self.assertEqual(d3["decision"], "ALLOW")

    def test_t_gate_01_green_snapshot_reaches_g4(self):
        # 正向对照：全绿快照达到 G4、R3 放行——门槛不是"永远拒绝"的假门禁
        base = self._gate_repo()
        g = AdmissionGate(base, now=self._NOW).load()
        a = g.evaluate()
        self.assertEqual(a["level"], "G4")
        self.assertEqual(a["blockers"], [])
        d = g.admit("R3", case_review={"approval_ref": "CR-2",
                                       "approver": "slow-is-fast",
                                       "principal_type": "human"})
        self.assertEqual(d["decision"], "ALLOW")
        self.assertEqual(d["actual_level"], "G4")

    def test_t_gate_01_unknown_risk_denied(self):
        base = self._gate_repo()
        g = AdmissionGate(base, now=self._NOW).load()
        with self.assertRaises(AdmissionDenied):
            g.admit("R9")


    # ---- T-INC-01：安全事件响应工作流（INC-01 / AUD-015） ----
    # 核心失败行为：涉事 Agent 不得批准自己的恢复或关闭事件。

    def _incident(self):
        w = IncidentWorkflow({"slow-is-fast", "sec-owner", "sec-backup"},
                             self.tmp / "incident-audit.jsonl")
        w.declare("INC-42", "SEV2", "Agent 越权写入控制面",
                  implicated=["agent-alpha"],
                  primary_owner="sec-owner", backup_owner="sec-backup",
                  credential_exposure=True, declared_at="2026-10-30T08:00:00Z")
        return w

    def test_t_inc_01_implicated_agent_cannot_approve(self):
        w = self._incident()
        # 涉事 Agent 依次尝试隔离/恢复/关闭 → 全部拒绝并写告警
        for method, kwargs in (("contain", {"quarantined": ["agent-alpha"],
                                            "evidence_preserved": True}),
                               ("recover", {"impact_assessed": True,
                                            "credential_rotated": True}),
                               ("close", {"reverified": True,
                                          "postmortem_ref": "pm-1"})):
            with self.assertRaises(IncidentRejected):
                getattr(w, method)("INC-42", "agent-alpha", **kwargs)
        # 告警事件已落审计：self_approval_attempt ×3
        raw = (self.tmp / "incident-audit.jsonl").read_text(encoding="utf-8")
        self.assertEqual(raw.count("self_approval_attempt"), 3)
        # 事件仍处 OPEN，未被越权推进
        self.assertEqual(w.incidents["INC-42"]["state"], "OPEN")

    def test_t_inc_01_implicated_human_and_non_responder_rejected(self):
        w = IncidentWorkflow({"slow-is-fast", "sec-owner", "sec-backup"},
                             self.tmp / "incident-audit.jsonl")
        # 涉事主体是人类（本人凭证泄露）→ 同样不得批准
        w.declare("INC-43", "SEV1", "Owner 凭证泄露",
                  implicated=["slow-is-fast"],
                  primary_owner="sec-owner", backup_owner="sec-backup",
                  credential_exposure=True)
        with self.assertRaises(IncidentRejected):
            w.contain("INC-43", "slow-is-fast", ["cred-1"], True)
        # 未涉事但不在负责人名单 → 拒绝
        with self.assertRaises(IncidentRejected):
            w.recover("INC-43", "someone-else", True, True)

    def test_t_inc_01_declare_validates_owners_and_severity(self):
        w = IncidentWorkflow({"slow-is-fast", "sec-owner"},
                             self.tmp / "incident-audit.jsonl")
        with self.assertRaises(IncidentRejected):   # Agent 当负责人
            w.declare("INC-1", "SEV2", "t", ["agent-a"],
                      primary_owner="agent-beta", backup_owner="sec-owner")
        with self.assertRaises(IncidentRejected):   # 负责人本人涉事
            w.declare("INC-1", "SEV2", "t", ["sec-owner"],
                      primary_owner="sec-owner", backup_owner="slow-is-fast")
        with self.assertRaises(IncidentRejected):   # 主责与替代相同
            w.declare("INC-1", "SEV2", "t", ["agent-a"],
                      primary_owner="sec-owner", backup_owner="sec-owner")
        with self.assertRaises(IncidentRejected):   # 未知分级
            w.declare("INC-1", "SEV9", "t", ["agent-a"],
                      primary_owner="sec-owner", backup_owner="slow-is-fast")

    def test_t_inc_01_containment_requires_quarantine_and_evidence(self):
        w = self._incident()
        with self.assertRaises(IncidentRejected):   # 空隔离清单
            w.contain("INC-42", "sec-owner", [], True)
        with self.assertRaises(IncidentRejected):   # 未保全证据
            w.contain("INC-42", "sec-owner", ["agent-alpha"], False)
        w.contain("INC-42", "sec-owner", ["agent-alpha", "run-9"], True)
        # CONTAINED 状态下重复隔离 → 非法跃迁
        with self.assertRaises(IncidentRejected):
            w.contain("INC-42", "sec-backup", ["x"], True)

    def test_t_inc_01_recovery_requires_impact_and_rotation(self):
        w = self._incident()
        w.contain("INC-42", "sec-owner", ["agent-alpha"], True)
        with self.assertRaises(IncidentRejected):   # 未做影响面排查
            w.recover("INC-42", "sec-backup", False, True)
        with self.assertRaises(IncidentRejected):   # 涉凭证但未轮换
            w.recover("INC-42", "sec-backup", True, False)
        with self.assertRaises(IncidentRejected):   # 涉凭证但轮换记录缺省
            w.recover("INC-42", "sec-backup", True, None)
        w.recover("INC-42", "sec-backup", True, True)

    def test_t_inc_01_close_requires_notify_reverify_postmortem(self):
        w = self._incident()
        w.contain("INC-42", "sec-owner", ["agent-alpha"], True)
        w.recover("INC-42", "sec-backup", True, True)
        with self.assertRaises(IncidentRejected):   # 未记录通知
            w.close("INC-42", "sec-owner", True, "pm-1")
        w.notify("INC-42", "2026-10-30T09:00:00Z")
        with self.assertRaises(IncidentRejected):   # 未复验
            w.close("INC-42", "sec-owner", False, "pm-1")
        with self.assertRaises(IncidentRejected):   # 缺复盘报告
            w.close("INC-42", "sec-owner", True, None)
        self.assertEqual(w.close("INC-42", "sec-owner", True, "pm-1")["state"],
                         "CLOSED")

    def test_t_inc_01_skip_recovery_cannot_close(self):
        w = self._incident()
        w.contain("INC-42", "sec-owner", ["agent-alpha"], True)
        w.notify("INC-42", "2026-10-30T08:30:00Z")
        # OPEN→CONTAINED 后直接关闭（跳过恢复审批）→ 非法跃迁
        with self.assertRaises(IncidentRejected):
            w.close("INC-42", "sec-owner", True, "pm-1")

    def test_t_inc_01_late_notification_recorded_honestly(self):
        w = self._incident()   # SEV2 时限 24h；08:00 宣告
        w.contain("INC-42", "sec-owner", ["agent-alpha"], True)
        w.recover("INC-42", "sec-backup", True, True)
        # 33 小时后才通知 → 照实记录 late=True，不伪装准时，也不静默放行
        late = w.notify("INC-42", "2026-10-31T17:00:00Z")
        self.assertTrue(late)
        rec = w.close("INC-42", "sec-owner", True, "pm-late")
        self.assertEqual(rec["state"], "CLOSED")
        self.assertTrue(rec["notification_late"])
        raw = (self.tmp / "incident-audit.jsonl").read_text(encoding="utf-8")
        self.assertIn('"late": true', raw)

    def test_t_inc_01_unknown_incident_and_full_happy_path(self):
        w = self._incident()
        with self.assertRaises(IncidentRejected):   # 未知事件 → 失败关闭
            w.recover("INC-404", "sec-owner", True, True)
        # 正向对照：SEV1 涉凭证全流程闭环（隔离→通知→恢复→复验→关闭）
        w2 = IncidentWorkflow({"slow-is-fast", "sec-owner", "sec-backup"},
                              self.tmp / "incident-audit2.jsonl")
        w2.declare("INC-7", "SEV1", "凭证进入提示文本",
                   implicated=["agent-g"],
                   primary_owner="sec-owner", backup_owner="sec-backup",
                   credential_exposure=True, declared_at="2026-10-30T08:00:00Z")
        w2.contain("INC-7", "sec-owner",
                   ["agent-g", "cred-77"], True)
        w2.notify("INC-7", "2026-10-30T08:40:00Z")   # 40min ≤ 1h，准时
        w2.recover("INC-7", "sec-backup", True, True)
        rec = w2.close("INC-7", "sec-owner", True, "postmortem/inc-7.md")
        self.assertEqual(rec["state"], "CLOSED")
        self.assertFalse(rec["notification_late"])


    # ---- T-CRED-01：凭证边界策略（CRED-01 / SEC-006/007/008） ----

    def _cred(self):
        g = CredentialGuard({"slow-is-fast"}, self.tmp / "cred-audit.jsonl")
        return g

    def test_t_cred_01_agent_cannot_read_protected_credentials(self):
        g = self._cred()
        for target in ({"path": "/etc/prod/db.env", "classification": "production_credential"},
                       {"path": "~/.ssh/id_ed25519", "classification": "ssh_private"},
                       {"path": "arn:aws:iam::admin", "classification": "cloud_admin_token"}):
            with self.assertRaises(CredDenied):
                g.access("agent-alpha", "agent", target)
        raw = (self.tmp / "cred-audit.jsonl").read_text(encoding="utf-8")
        self.assertEqual(raw.count("credential.access_denied"), 3)

    def test_t_cred_01_unclassified_target_defaults_to_protected(self):
        g = self._cred()
        # 未分类目标 + Agent 主体 → 按受保护处理（不因为"没标"就放宽）
        with self.assertRaises(CredDenied):
            g.access("agent-alpha", "agent", {"path": "data/unknown.bin"})

    def test_t_cred_01_human_access_and_unknown_human(self):
        g = self._cred()
        # 白名单内的人类可访问受保护目标（正向对照）
        self.assertEqual(
            g.access("slow-is-fast", "human",
                     {"path": "/etc/prod/db.env",
                      "classification": "production_credential"}),
            "ALLOWED")
        # 自称 human 但不在白名单 → 拒绝（主体声明不构成授权）
        with self.assertRaises(CredDenied):
            g.access("stranger", "human",
                     {"path": "/etc/prod/db.env",
                      "classification": "production_credential"})

    def test_t_cred_01_credential_patterns_in_text_detected(self):
        g = self._cred()
        # 各类凭证形态进入提示文本/日志 → 全部检出
        cases = [
            ("prompt", "please use github_pat_11AEW2Z3Q0JM1oWtIag3DF_JRAdOQxl5L4NcYW8CXsp"),
            ("log", "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA"),
            ("prompt", "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"),
            ("chat", "my token is ghp_16C7e42F292c6912E271264cCw557awledReRU"),
            ("log", "bot creds: xoxb-1538374892abcdef"),
            ("prompt", "api key sk-proj4abcdefghijklmn9qrstuvwxyz012345"),
        ]
        for context, text in cases:
            hits = g.scan_text(text, context)
            self.assertTrue(hits, f"漏检：{context} -> {text[:40]}")
        raw = (self.tmp / "cred-audit.jsonl").read_text(encoding="utf-8")
        self.assertEqual(raw.count("credential.exposure_detected"), 6)
        # 干净文本不误报（正向对照）
        self.assertEqual(g.scan_text("正常任务说明：读取 README 并总结要点。", "prompt"), [])

    def test_t_cred_01_exposure_remediation_fails_closed(self):
        g = self._cred()
        g.scan_text("token ghp_" + "A" * 36, "prompt")
        exposure_id = next(iter(g.exposures))
        # 未确认轮换 → 失败关闭
        with self.assertRaises(CredDenied):
            g.confirm_remediation(exposure_id, rotated=False,
                                  incident_declared=True)
        # 未登记事件 → 失败关闭
        with self.assertRaises(CredDenied):
            g.confirm_remediation(exposure_id, rotated=True,
                                  incident_declared=False)
        # 未知暴露 ID → 失败关闭
        with self.assertRaises(CredDenied):
            g.confirm_remediation("EXP-404", rotated=True, incident_declared=True)
        # 轮换 + 事件登记齐备 → 闭环（正向对照）
        self.assertEqual(g.confirm_remediation(exposure_id, rotated=True,
                                               incident_declared=True),
                         "REMEDIATED")

    def test_t_cred_01_suspend_requests_always_rejected(self):
        g = self._cred()
        # Agent 请求停用审计 / 跳过质量检查 / 压制告警 → 一律拒绝
        for action in ("disable_audit", "skip_quality_checks", "suppress_alerts"):
            with self.assertRaises(CredDenied):
                g.request("agent-alpha", "agent", action)
        # 人类经由本守卫请求同样拒绝——正确通道是变更管理（CHG-01）
        with self.assertRaises(CredDenied):
            g.request("slow-is-fast", "human", "disable_audit")
        raw = (self.tmp / "cred-audit.jsonl").read_text(encoding="utf-8")
        self.assertEqual(raw.count("credential.request_rejected"), 4)
        # 合法请求（如主动轮换）正常处理（正向对照）
        self.assertEqual(g.request("slow-is-fast", "human",
                                   "rotate_credential"), "PROCESSED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
