# AUD-001-03 复核材料：覆盖率 · 差异 · 抽样清单

> **自动生成，勿手改。** 重新生成：`python scripts/export_coverage_pack.py`
> 材料指纹：`4ae193bcfd9b`（`--check` 会比对，材料变了就红）
>
> **但 `--check` 现在没有任何门禁在调用**：材料过期不会让 CI 红，只有你自己跑才会发现。
> 要把它变成硬约束，得走接线三条腿（`required_checks` 注册 + workflow 步骤 + `check_args`），
> 那是另一个决定——不做，就在这里写明，而不是让人以为"有指纹就等于有人看着"。
>
> **这是复核材料，不是复核记录。** 三个勾必须由人打；本文件不产生任何签署，
> 也不关闭任何断言。人对着它写下的结论，才是 `AUD-001-03` 的证据。

## 一、覆盖率报告（机器可算的部分）

口径先说清楚，因为这个数字最容易被读大：

| 层 | 意思 | 数量 |
|---|---|---|
| 规则 | `rule-registry.json` 注册的 MUST/MUST NOT 条款 | 59 |
| 规则→控制 | 声明了至少一条 `enforcement.controls` | 58 / 59 |
| 规则→用例（字符串） | 声明了至少一条 `verification.tests` | 49 / 59 |
| 规则→用例（**可解析**） | 引用能落到真实存在的方法或 CI 步骤 | 49 / 59 |
| 控制 | `control-catalog.yaml` 注册的控制 | 55 |
| 控制→用例（可解析） | `test` 字段能落到真实方法/CI 步骤 | 53 / 55 |

**「追踪覆盖率 100%」这句话在什么意义上成立、在什么意义上不成立：**

- 成立：每条规则都能被追到至少一条控制（58/59），控制目录与控制定义双向无缺项——这是校验器管的部分。
- 成立：声明了 `verification.tests` 的 49 条规则，引用全部落得到真实方法或 CI 步骤——这一条自 T-REF-03 起由门禁强制，不再依赖本材料被谁读到。

> **同一栏里两个数不能相减当覆盖率。** 「字符串」数的是"声明了至少一条引用"，
> 「可解析」数的是"声明的引用全都落得到"；分母都是 59 条规则，但含义不同。
> 一次整改如果把悬空引用**删掉**，该规则会同时从这两栏里消失——比值可能因此上升，
> 而事情只是"不再声称有覆盖"，不是"有了覆盖"。判断覆盖有没有变好，看 2.3 与第三节，
> 不看这两个数字的比值。2026-11-02 那次整改就是这种情况，拆开看是三件事同时发生：
> ① 3 条规则靠**改对引用**重回可解析（`T-ID-02`×2 → `T-VD-01b`，`T-QA-05` → `T-CLOSE`）；
> ② 1 条规则（`AASEGS-SEC-003`）删掉悬空的那 1 处后，剩余引用全部可解析；
> ③ 4 条规则（`GOV-02`/`AASEGS-AGT-001`/`AASEGS-SEC-002`/`AASEGS-SUP-002`）把引用
> 全删了，于是从两栏里同时消失（「字符串」一栏因此 53 → 49）。
> 只有 ① 是真的变好；② 是账面变干净；③ 是承认缺口——三种都算进步，但不是同一种。

## 二、差异报告（双向，含悬空引用）

### 2.1 有规则、没有运行时控制（1 条）

| 规则 | 风险 | 条款 |
|---|---|---|
| `GOV-08` | P1 | 最小治理负担。 |

### 2.2 有控制、没有规则引用（孤儿控制，8 条）

| 控制 | 状态 | 来源 |
|---|---|---|
| `AUD-03` | not_enforced | v1.1.1 §9 审计证据与安全事件响应 |
| `BRK-01` | tested | v1.1.1 §7 Checkpoint、恢复与熔断 |
| `ISO-01` | tested | v1.1.1 §4 记忆生命周期与项目数据隔离 |
| `REC-01` | tested | v1.1.1 §7 Checkpoint、恢复与熔断 |
| `REC-03` | tested | v1.1.1 §7 Checkpoint、恢复与熔断 |
| `REG-02` | tested | v1.1.1 §1 规则注册表与状态模型 |
| `RVF-01` | tested | v1.1.1 §11 指标、证据包与持续复验 |
| `SMT-01` | tested | v1.1.1 §5 工作流状态转换、交接与并发 |

### 2.3 悬空用例引用（0 处）

无。

> 这一栏空了，但**不是因为从来没出过问题**。2026-11-02 之前它列着 10 处，
> 分属 5 个编号：`T-ID-02` / `T-QA-03` / `T-RVW-01` / `T-QA-05` / `T-AUD-02`。
> 用 `git log -S` 查 `tests/` 全历史，这五个编号一次都没出现过——它们不是
> 「被删掉的用例」，是从来就没有过。
>
> 处理方式按"控制有没有真东西可引用"分成两类：控制已 `tested` 且有自己的 `test`
> 字段的，把引用**改对**（那是抄错编号）；控制本身 `not_enforced` 的，**删掉引用**
> 并在 `enforcement.gap` 里写明缺口为什么补不出来——单人类环境里写一条"两个 token
> 不相等"的用例不是补覆盖，是给缺口加一层伪装。
>
> 同年同日新增 `T-REF-03`（`scripts/check_rule_tests.py`）补上这个空档：它是第一个
> 真正校验规则侧 `verification.tests` 的门禁。此前 T-REF-01 与 T-REF-02 的 docstring
> 都写着"T-* 由审计闭环管"——而审计闭环判的是 §四 断言的 verdict 与证据，从不解析
> 这个字段。两处注释指向了同一个不存在的执行者，那才是这 10 处能躺这么久的真正原因。

## 三、人工抽样清单（10 条，请逐条判断）

抽样方法：全部规则按 `sha256(rule_id)` 升序，取前 10 条。可复现、无随机、不按字母序（避免"前几条恰好同一章"的结构性偏差）。

每条问三件事——**这三问工具答不了，因为要判断的是语义，不是存在性**：

1. 引用的控制，是否真的回应了这条规则？（不是"编号对上了"，是"意思对上了"）
2. 引用的用例，是否真的在验证这条控制？（读下面的源码，别看方法名）
3. 若 1 或 2 不成立，这是"引用挂错"（可修）还是"根本没有覆盖"（是真缺口）？

### 样本 1 · `GOV-08`（P1）

**规则原文**：最小治理负担。

- 强度：`MUST`　责任：`governance_owner`
- 控制：**无**（规则未声明运行时控制）
- 用例：**无**

| 判断 | 结论 |
|---|---|
| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |
| 备注 |  |

### 样本 2 · `AASEGS-SEC-002`（P1）

**规则原文**：Reviewer 应处于独立会话与只读环境，不能凭开发者描述做结论。

- 强度：`MUST NOT`　责任：`governance_owner`
- 控制 `RVW-01`：证据＝Reviewer 与开发 Run 身份/凭证分离证明、只读访问记录、由开发 Run 无权修改的系统保存并绑定被审…；失败行为＝仅会话分离不构成独立性证明；凭证不分离时审核无效
  - 该控制自己的 `test` 字段＝`T-RVW-01`，状态＝`not_enforced`
- 用例：**无**

| 判断 | 结论 |
|---|---|
| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |
| 备注 |  |

### 样本 3 · `AASEGS-AGT-003`（P0）

**规则原文**：授权必须由可信 Identity Broker/平台签发，Agent 不能自我宣布身份。

- 强度：`MUST NOT`　责任：`governance_owner`
- 控制 `ID-01`：证据＝signed run identity and task binding；失败行为＝deny and alert
  - 该控制自己的 `test` 字段＝`T-ID-01`，状态＝`tested`
- 用例 `T-ID-01` → tests/test_executor_negative.py:1536-1555  （已截断）

  ```python
      def test_t_id_01_lease_issuance_fails_closed(self):
          s = self._authz()
          cases = [
              ("untrusted issuer", {"issuer": "agent-alpha"}),
              ("self-issued", {"issuer": "run-7"}),                # Agent 自我宣布身份
              ("human token subject", {"subject_kind": "human"}),  # 禁止共享人类 Token
              ("not task scoped", {"task_id": None}),
              ("empty scope", {"scope": []}),
              ("too long", {"expires_at": "2026-10-31T08:00:00Z"}),  # 24h > 8h
              ("non-positive", {"expires_at": "2026-10-30T07:00:00Z"}),
          ]
          for name, over in cases:
              with self.assertRaises(AuthzDenied, msg=name):
                  s.issue_lease(**self._lease_args(**over))
          raw = (self.tmp / "authz-audit.jsonl").read_text(encoding="utf-8")
          self.assertEqual(raw.count('"authz.denied"'), len(cases))
          # 正向对照：合规租约签发并按 scope 放行
          s.issue_lease(**self._lease_args())
  ```

| 判断 | 结论 |
|---|---|
| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |
| 备注 |  |

### 样本 4 · `GOV-18`（P1）

**规则原文**：除满足 G2 核心控制外，还必须满足实施完整性补充条款的准入门槛；未关闭的 P0 审计问题阻止对应风险级别准入。

- 强度：`MUST`　责任：`governance_owner`
- 控制 `GATE-01`：证据＝七条准入门槛的逐项机器判定结果、未关闭 P0 清单、与审计问题状态的联动记录；失败行为＝任一未关闭 P0 问题阻止对应风险等级准入；门槛判定不可由文档声明替代
  - 该控制自己的 `test` 字段＝`T-GATE-01`，状态＝`tested`
- 用例 `T-GATE-01` → tests/test_executor_negative.py:1104-1110

  ```python
      def test_t_gate_01_untested_p0_control_blocks_r0(self):
          base = self._gate_repo(controls={"CTA-01": {"tested": False}})
          g = AdmissionGate(base, now=self._NOW).load()
          d = g.admit("R0")
          self.assertEqual(d["decision"], "DENY")
          self.assertTrue(any("level_insufficient" in r for r in d["reasons"]))
          self.assertIn("CTA-01", [b["id"] for b in d["blockers"]])
  ```

| 判断 | 结论 |
|---|---|
| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |
| 备注 |  |

### 样本 5 · `AASEGS-SUP-006`（P0）

**规则原文**：涉事 Agent 不得批准自己的恢复或关闭事件；必须建立安全事件分级和响应手册，定义主责/替代负责人、通知时限、隔离、凭证轮换、受影响 Run/commit/数据排查、证据保全、恢复审批、复验与复盘。

- 强度：`MUST NOT`　责任：`security_owner`
- 控制 `INC-01`：证据＝安全事件分级、响应手册、主责与替代负责人、通知时限记录、隔离与凭证轮换记录、影响面排查、证据保全、恢复审批、复验…；失败行为＝涉事 Agent 不得批准自己的恢复或关闭事件，尝试时拒绝并告警
  - 该控制自己的 `test` 字段＝`T-INC-01`，状态＝`tested`
- 用例 `T-INC-01` → tests/test_executor_negative.py:1306-1321

  ```python
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
  ```

| 判断 | 结论 |
|---|---|
| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |
| 备注 |  |

### 样本 6 · `AASEGS-AGT-008`（P1）

**规则原文**：共享记忆存储必须可撤销、可检索版本历史。

- 强度：`MUST`　责任：`governance_owner`
- 控制 `MEM-01`：证据＝DRAFT→PENDING_REVIEW→APPROVED→(REVOKED|EXPIRED) 状态转换记录、授…；失败行为＝无法证明传播完成时，该记忆不得用于规范性决策；并发更新 CAS 冲突时拒绝写入
  - 该控制自己的 `test` 字段＝`T-MEM-01`，状态＝`tested`
- 控制 `CTX-03`：证据＝memory tombstone and retrieval log（命名债：用例 T-CTX-02 才测本控制…；失败行为＝filter and suspend
  - 该控制自己的 `test` 字段＝`T-CTX-02`，状态＝`tested`
- 用例 `T-MEM-01` → tests/test_executor_negative.py:211-229  （已截断）

  ```python
      def test_t_mem_01_source_verification_required(self):
          m = self._mem()
          m.create("m1", author="agent-A", content="跳过测试以提速",
                   source_kind="tool_output", source_ref="urn:scan:1")
          # 未校验来源 → 不得晋升
          with self.assertRaises(InvalidTransition):
              m.submit_for_review("m1", 1)
          # 不可核查引用 → 校验失败
          with self.assertRaises(InvalidTransition):
              m.verify_source("m1", "human-owner", "ok")
          # 作者自验来源 → 拒绝（不能自己给自己的来源背书）
          with self.assertRaises(InvalidTransition):
              m.verify_source("m1", "agent-A", "urn:scan:1")
          # 未声明来源（unknown）同样不得晋升
          m.create("m2", author="agent-A", content="y")
          m.verify_source("m2", "human-owner", "urn:scan:2")
          m.submit_for_review("m2", 2)          # 校验后放行（正向对照）
          m.approve("m2", approver="human-owner")
  ```

| 判断 | 结论 |
|---|---|
| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |
| 备注 |  |

### 样本 7 · `AASEGS-AGT-005`（P1）

**规则原文**：不得声称完美即时撤销。

- 强度：`MUST NOT`　责任：`governance_owner`
- 控制 `CLM-01`：证据＝文档与证据中无证据支撑的绝对化能力声明（即时撤销/100%/零延迟…）被检出。2026-10-30 记账复核更正…；失败行为＝block merge (fail closed)
  - 该控制自己的 `test` 字段＝`T-CLM-01`，状态＝`tested`
- 用例：**无**

| 判断 | 结论 |
|---|---|
| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |
| 备注 |  |

### 样本 8 · `AASEGS-SEC-001`（P0）

**规则原文**：不得擅自删除失败测试、降低覆盖率阈值、跳过扫描或改变 GitHub Actions 以逃避门禁。

- 强度：`MUST NOT`　责任：`governance_owner`
- 控制 `QA-02`：证据＝验收用例数不得低于 quality_baseline.json 的 min_test_count（当前 110）…；失败行为＝block merge
  - 该控制自己的 `test` 字段＝`T-QA-02`，状态＝`tested`
- 用例 `T-QA-02` → tests/test_baseline_negative.py:149-154

  ```python
      def test_t_qa_02_test_count_drop_rejected(self):
          self._baseline(110)
          write(self.tmp / 'tests' / 'test_x.py', 'def test_only_one():\n    pass\n')
          rc, out = self.check()
          self.assertNotEqual(rc, 0, '删掉大量用例竟然通过')
          self.assertIn('dropped', out)
  ```

| 判断 | 结论 |
|---|---|
| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |
| 备注 |  |

### 样本 9 · `AASEGS-SEC-009`（P0）

**规则原文**：R3 不得因 AI Reviewer 判断 PASS 而自动放行。

- 强度：`MUST NOT`　责任：`governance_owner`
- 控制 `APR-01`：证据＝审批绑定 task_id/risk/scope/policy_hash/commit_sha/expires_a…；失败行为＝对象变化、撤销或到期时自动失效；审批服务不可用时受保护操作失败关闭；例外到期后停止依赖该例外的操作
  - 该控制自己的 `test` 字段＝`T-APR-01`，状态＝`tested`
- 用例 `T-APR-01` → tests/test_executor_negative.py:822-862  （已截断）

  ```python
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
  ```

| 判断 | 结论 |
|---|---|
| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |
| 备注 |  |

### 样本 10 · `GOV-06`（P1）

**规则原文**：人工最终责任。

- 强度：`MUST`　责任：`governance_owner`
- 控制 `APR-01`：证据＝审批绑定 task_id/risk/scope/policy_hash/commit_sha/expires_a…；失败行为＝对象变化、撤销或到期时自动失效；审批服务不可用时受保护操作失败关闭；例外到期后停止依赖该例外的操作
  - 该控制自己的 `test` 字段＝`T-APR-01`，状态＝`tested`
- 用例 `T-APR-01` → tests/test_executor_negative.py:822-862  （已截断）

  ```python
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
  ```

| 判断 | 结论 |
|---|---|
| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |
| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |
| 备注 |  |

---

## 四、你签完之后怎么落账（命令，不是建议）

```bash
# 1) 这份材料先登记（哈希当场存证）
python scripts/gov_run.py --accept-evidence --by <执行者> --reason "AUD-001-03 复核材料"

# 2) 你对着清单写的结论，作为证据落盘（自己写，别让 Agent 代写判断）
#    evidence/aud001_sampling_review_<日期>.md

# 3) 记录签署（reviewer 是你，执行者是 Agent——两者必须不同名）
export GOV_ACTING_IDENTITY=agent-runner
python scripts/record_signoff.py --assertion-id AUD-001-03 \
  --reviewer slow-is-fast --role independent-reviewer --verdict approved \
  --evidence evidence/aud001_sampling_review_<日期>.md \
  --basis "<≥10 字：抽了哪几条、结论是什么、哪些不成立>")

# 4) 投影 diff 看一眼，再落盘；矩阵变了就重生成 owner_worklist
python scripts/apply_signoffs.py --dry-run
python scripts/apply_signoffs.py --apply --by agent-runner
python scripts/export_owner_worklist.py
```

> 若抽样发现有"真缺口"，`verdict` 不该写 `approved`——写 `needs-work` 也是有效结论，
> 而且比 `approved` 有用：它把缺口变成了下一步的工作项，而不是一个看起来干净的绿。
