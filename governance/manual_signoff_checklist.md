# 21 条 manual 断言 · 独立复核签署证据清单矩阵

> 配套脚手架：`scripts/record_signoff.py` + `governance/signoffs.jsonl`（append-only）
> 配套人用指南：`evidence/signoff_template.md`
> 机制说明：`evidence/signoff_scaffold_20261031T224100Z.md`

## 0. 用途与诚实边界

本矩阵是 **EXC-01（独立第二主体不可达）脚手架的"照表填"指南**。它把 21 条
`manual` 断言各自"复核时该看什么、要什么证据、以什么角色签"具体化，让真实复核
主体用 `record_signoff.py` 时直接照表填，而不是凭感觉。

**本文件不关闭任何断言。** 它只让"人类独立复核"这一步变得可操作、可追溯、可审计。
在 `governance/signoffs.jsonl` 出现对应 `assertion_id` 的 `approved` 签署之前，该
断言在 `acceptance_matrix.json` 中仍记为 `manual`（未关闭、未 verified）。这是治理
铁律：机器不可判定的人工项，必须由独立人类主体显式落证，Agent 不得代签、不得用
文档声明替代机器/人类判定。

## 1. 使用前置（每次签署前都要做）

1. 确认执行主体身份已声明（Agent 侧，用于防自签比对）：
   ```bash
   export GOV_ACTING_IDENTITY=slow-is-fast   # 与本项目实际执行主体一致
   ```
2. 复核人必须是**不同于** `GOV_ACTING_IDENTITY` 的真实人类 / 独立账号。
3. 先准备证据物，落盘到 `evidence/manual/<ASSERTION_ID>.md`（多份证据可逗号分隔）。
4. 运行脚手架：
   ```bash
   python scripts/record_signoff.py \
     --assertion-id <ASSERTION_ID> \
     --reviewer "<复核人实名>" \
     --role <independent-reviewer|owner|security-owner> \
     --verdict approved \
     --evidence evidence/manual/<ASSERTION_ID>.md \
     --basis "<本次复核的要点：看了什么、为何给 approved>"
   ```
5. 工具硬约束（不通过即拒绝，不写文件）：
   - 签署人 `== GOV_ACTING_IDENTITY` → 拒绝（防自签）
   - `role` 不在 `{independent-reviewer, owner, security-owner}` → 拒绝
   - `assertion_id` / `verdict` 为空或非法 → 拒绝
   - 至少 1 条 `--evidence`（逗号分隔也行）→ 拒绝
   - `--basis` 少于 10 字 → 拒绝

> 注意：本清单给出的"建议角色"是缺省推荐。若某条断言的关闭条件明确指向特定
> 责任人（如 Security Owner），请以关闭条件为准；`owner` 与 `independent-reviewer`
> 可由同一项目的不同责任人担任，但**不得与 `GOV_ACTING_IDENTITY`（Agent 执行方）为
> 同一身份**。

## 2. 矩阵（21 条，按严重度/问题编号排序）

### AUD-001-03 — 覆盖率完备性人工抽样复核
- **所属问题 / 严重度**：AUD-001 / P0
- **关闭条件**：提交覆盖率报告、差异报告和人工抽样复核记录。
- **复核类型**：`sampling_review`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-001-03.md`
- **`--basis` 应覆盖**：抽样方法（抽了哪些控制/规则）、抽样比例、是否发现遗漏、
  覆盖率报告与差异报告的一致性结论。
- **复核清单**：
  - [ ] 覆盖率报告存在且指向当前 commit
  - [ ] 差异报告（注册表↔控制目录双向差异=0）结论与报告一致
  - [ ] 抽样记录可追溯（抽了什么、何时、谁抽）
  - [ ] 抽样未发现未覆盖的强制条款

### AUD-002-03 — 报告可区分六种状态的独立复核
- **所属问题 / 严重度**：AUD-002 / P0
- **关闭条件**：状态机测试和负向测试通过；报告可区分六种状态。
- **复核类型**：`six_state_report_review`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-002-03.md`
- **`--basis` 应覆盖**：报告是否真能区分六种状态、负向用例是否覆盖状态误转换、
  结论是否独立得出（非照搬 Agent 自述）。
- **复核清单**：
  - [ ] 取出报告样本，逐条核对六种状态标记互不混淆
  - [ ] 状态机负向测试存在且通过（篡改→拒绝）
  - [ ] 复核人独立重算/重读，非仅引用机器输出

### AUD-003-03 — schema 与校验器合并评审
- **所属问题 / 严重度**：AUD-003 / P1
- **关闭条件**：schema、校验器及正反例测试合并。
- **复核类型**：`schema_review`
- **建议签署角色**：`owner`（或 `independent-reviewer`）
- **建议证据物**：`evidence/manual/AUD-003-03.md`
- **`--basis` 应覆盖**：schema 与校验器是否同源、正反例是否覆盖非法输入。
- **复核清单**：
  - [ ] schema 定义与校验逻辑指向同一来源
  - [ ] 至少一个正例 + 一个反例测试
  - [ ] 人工确认反例确实被拒

### AUD-004-05 — 隔离环境集成测试 + 资源端拒绝证据
- **所属问题 / 严重度**：AUD-004 / P0
- **关闭条件**：隔离环境集成测试通过并留存资源端拒绝证据。
- **复核类型**：`isolated_env_integration_test`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-004-05.md`（附资源端拒绝日志/截图）
- **`--basis` 应覆盖**：隔离环境真实性、集成测试通过证据、资源端（如云厂商/外部
  服务）明确拒绝越权操作的回执。
- **复核清单**：
  - [ ] 集成测试在隔离环境（非本机 mock）执行
  - [ ] 测试通过产物可追溯（构建号/日志）
  - [ ] 资源端拒绝证据是真实回执，非本地模拟

### AUD-005-03 — Claude Code / Codex 实际配置验证记录
- **所属问题 / 严重度**：AUD-005 / P1
- **关闭条件**：能力矩阵、校验规则和实际配置验证记录通过复核。
- **复核类型**：`tool_config_verification`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-005-03.md`
- **`--basis` 应覆盖**：实际配置（非设计文档）与能力矩阵/校验规则是否一致。
- **复核清单**：
  - [ ] 读取真实配置文件（非草案）
  - [ ] 比对能力矩阵声明与实际开启的能力
  - [ ] 校验规则生效性被实际验证

### AUD-006-05 — 记忆状态机与检索/缓存集成测试
- **所属问题 / 严重度**：AUD-006 / P1
- **关闭条件**：记忆状态机与检索/缓存集成测试通过。
- **复核类型**：`memory_integration_test`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-006-05.md`
- **`--basis` 应覆盖**：集成测试是否覆盖状态迁移 + 检索/缓存一致性。
- **复核清单**：
  - [ ] 集成测试存在且通过
  - [ ] 覆盖记忆状态迁移边界
  - [ ] 检索/缓存一致性被验证（陈旧缓存被剔除）

### AUD-007-03 — 日志 from/to/actor/decision/evidence 完整性抽查
- **所属问题 / 严重度**：AUD-007 / P1
- **关闭条件**：状态机测试通过且日志完整记录 from/to/actor/decision/evidence。
- **复核类型**：`transition_log_review`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-007-03.md`
- **`--basis` 应覆盖**：抽查若干状态迁移，五个字段是否齐全、是否可追溯。
- **复核清单**：
  - [ ] 抽 3+ 条真实迁移日志，五字段齐全
  - [ ] actor 非匿名、decision 有依据、evidence 有指向
  - [ ] 缺失字段被标记而非掩盖

### AUD-009-04 — 真实代表性副作用端到端 + 远端结果证据
- **所属问题 / 严重度**：AUD-009 / P0
- **关闭条件**：至少一个真实代表性副作用端到端测试通过并保存远端结果证据。
- **复核类型**：`real_side_effect_e2e`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-009-04.md`（附远端结果回执）
- **`--basis` 应覆盖**：副作用是真实代表（非玩具）、端到端打通、远端结果可验证。
- **复核清单**：
  - [ ] 选取的副作用具代表性（与风险登记匹配）
  - [ ] 端到端链路真实执行（非单元测试拼装）
  - [ ] 远端结果证据是外部系统真实回执

### AUD-010-04 — 恢复演练 + 检查点与决策可追溯关联
- **所属问题 / 严重度**：AUD-010 / P0
- **关闭条件**：恢复演练通过；检查点与恢复决策可追溯关联。
- **复核类型**：`recovery_drill`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-010-04.md`
- **`--basis` 应覆盖**：演练是否真实执行、检查点能否关联到具体恢复决策。
- **复核清单**：
  - [ ] 恢复演练记录含时间戳与执行人
  - [ ] 检查点 ID 可回溯到恢复动作
  - [ ] 演练结论明确"通过/未通过"

### AUD-011-04 — 隔离环境演练记录
- **所属问题 / 严重度**：AUD-011 / P1
- **关闭条件**：配置、测试结果和隔离环境演练记录齐全。
- **复核类型**：`breaker_drill`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-011-04.md`
- **`--basis` 应覆盖**：配置/测试/演练三件套是否齐全且指向同一环境。
- **复核清单**：
  - [ ] 配置记录、测试结果、演练记录三者齐备
  - [ ] 演练确在隔离环境执行
  - [ ] 断路器触发/恢复行为被实际观测

### AUD-012-03 — 真实试点仓库配置独立检查（分支保护 + SHA 绑定）
- **所属问题 / 严重度**：AUD-012 / P0
- **关闭条件**：真实试点仓库配置经独立检查，负向测试证据齐全。
- **复核类型**：`pilot_repo_inspection`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-012-03.md`
- **`--basis` 应覆盖**：独立检查人身份、分支保护设置、SHA 绑定是否生效、负向证据。
- **复核清单**：
  - [ ] 检查人独立于配置方
  - [ ] 分支保护规则截图/导出
  - [ ] SHA 绑定被验证（篡改即拒）
  - [ ] 负向测试证据留存

### AUD-013-04 — 权限矩阵评审与高风险复核可追溯
- **所属问题 / 严重度**：AUD-013 / P1
- **关闭条件**：权限矩阵和负向测试通过；高风险人工复核可追溯。
- **复核类型**：`permission_matrix_review`
- **建议签署角色**：`independent-reviewer`（或 `owner`）
- **建议证据物**：`evidence/manual/AUD-013-04.md`
- **`--basis` 应覆盖**：权限矩阵完整性、高风险操作是否要求人工复核且可追溯。
- **复核清单**：
  - [ ] 权限矩阵覆盖所有角色×操作
  - [ ] 负向测试（越权被拒）通过
  - [ ] 高风险复核留痕可查

### AUD-014-04 — 审计后端配置与完整性报告
- **所属问题 / 严重度**：AUD-014 / P0
- **关闭条件**：审计后端配置、完整性报告、恢复演练及故障关闭测试通过。
- **复核类型**：`audit_backend_review`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-014-04.md`
- **`--basis` 应覆盖**：后端配置真实、完整性报告可信、恢复与故障关闭测试通过。
- **复核清单**：
  - [ ] 审计后端真实配置证据
  - [ ] 完整性报告产出自该后端
  - [ ] 恢复演练 + 故障关闭测试通过证据

### AUD-015-04 — 响应手册经 Security Owner 批准
- **所属问题 / 严重度**：AUD-015 / P0
- **关闭条件**：Security Owner 批准响应手册，演练问题已分派并验证关闭。
- **复核类型**：`security_owner_approval`
- **建议签署角色**：`security-owner`（**必须**为该角色，关闭条件硬性要求）
- **建议证据物**：`evidence/manual/AUD-015-04.md`
- **`--basis` 应覆盖**：批准人确为 Security Owner、手册版本、演练问题分派与关闭证明。
- **复核清单**：
  - [ ] 批准人身份为 Security Owner（非普通 owner）
  - [ ] 手册版本号明确
  - [ ] 演练发现的问题已分派且有验证关闭记录

### AUD-016-04 — 数据矩阵经责任人批准
- **所属问题 / 严重度**：AUD-016 / P0
- **关闭条件**：数据矩阵获责任人批准，隔离和删除测试通过。
- **复核类型**：`data_matrix_approval`
- **建议签署角色**：`owner`（数据矩阵责任人）
- **建议证据物**：`evidence/manual/AUD-016-04.md`
- **`--basis` 应覆盖**：批准人确为数据矩阵责任人、隔离/删除测试通过证据。
- **复核清单**：
  - [ ] 批准人身份与责任人一致
  - [ ] 数据隔离测试通过
  - [ ] 数据删除测试通过（可验证擦除）

### AUD-017-04 — 记录绑定版本/审批/回滚证据
- **所属问题 / 严重度**：AUD-017 / P1
- **关闭条件**：变更状态机与测试通过，记录绑定版本、审批和回滚证据。
- **复核类型**：`change_evidence_review`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-017-04.md`
- **`--basis` 应覆盖**：变更记录是否同时绑定版本号、审批记录、回滚方案。
- **复核清单**：
  - [ ] 变更记录含版本号
  - [ ] 审批链路可追溯
  - [ ] 回滚证据存在且可执

### AUD-018-03 — 审批与仓库门禁集成测试，例外自动失效可审计
- **所属问题 / 严重度**：AUD-018 / P1
- **关闭条件**：审批/仓库门禁集成测试通过，例外自动失效且可审计。
- **复核类型**：`repo_gate_integration`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-018-03.md`
- **`--basis` 应覆盖**：集成测试通过、例外到期/失效是否自动、审计留痕。
- **复核清单**：
  - [ ] 集成测试通过证据
  - [ ] 例外自动失效机制被验证（到期即失效）
  - [ ] 失效事件可审计

### AUD-019-02 — 指标字典与阈值配置审核
- **所属问题 / 严重度**：AUD-019 / P2
- **关闭条件**：指标字典、阈值配置和超限演练完成审核。
- **复核类型**：`metric_dict_review`
- **建议签署角色**：`owner`（或 `independent-reviewer`）
- **建议证据物**：`evidence/manual/AUD-019-02.md`
- **`--basis` 应覆盖**：指标字典完整性、阈值合理、超限演练已做。
- **复核清单**：
  - [ ] 指标字典覆盖关键维度
  - [ ] 阈值有依据
  - [ ] 超限演练记录存在

### AUD-020-04 — 等级矩阵与试点评估报告独立复核
- **所属问题 / 严重度**：AUD-020 / P0
- **关闭条件**：等级矩阵和试点评估报告经独立复核。
- **复核类型**：`maturity_matrix_review`
- **建议签署角色**：`independent-reviewer`
- **建议证据物**：`evidence/manual/AUD-020-04.md`
- **`--basis` 应覆盖**：等级矩阵合理性、试点评估结论是否经独立得出。
- **复核清单**：
  - [ ] 等级矩阵维度与判定标准明确
  - [ ] 试点评估报告由独立方复核签字
  - [ ] 结论与数据一致

### AUD-021-03 — 受控真实仓库证据包 + 独立 Reviewer/Owner 签署
- **所属问题 / 严重度**：AUD-021 / P1
- **关闭条件**：一个受控真实仓库完成证据包并由独立 Reviewer/Owner 签署。
- **复核类型**：`signed_evidence_package`
- **建议签署角色**：`independent-reviewer` **且** `owner`（关闭条件要求双签）
- **建议证据物**：`evidence/manual/AUD-021-03.md`
- **`--basis` 应覆盖**：证据包完整性、签署双方身份独立且非执行主体。
- **复核清单**：
  - [ ] 证据包覆盖受控真实仓库全部断言
  - [ ] 至少两条签署：一条 `independent-reviewer`、一条 `owner`
  - [ ] 两签署人均 ≠ `GOV_ACTING_IDENTITY`

### AUD-022-04 — 周期/事件复验策略审批
- **所属问题 / 严重度**：AUD-022 / P1
- **关闭条件**：周期/事件触发复验策略及 CI 测试通过。
- **复核类型**：`reverify_policy_approval`
- **建议签署角色**：`owner`（策略责任人审批）
- **建议证据物**：`evidence/manual/AUD-022-04.md`
- **`--basis` 应覆盖**：复验策略触发条件、CI 中复验测试通过证据。
- **复核清单**：
  - [ ] 策略明确周期 + 事件两类触发
  - [ ] CI 中存在对应复验测试且通过
  - [ ] 审批人为策略责任人

## 3. 汇总视图

| # | Assertion ID | 问题 | 严重度 | 建议角色 | 复核类型 |
|---|--------------|------|--------|----------|----------|
| 1 | AUD-001-03 | AUD-001 | P0 | independent-reviewer | sampling_review |
| 2 | AUD-002-03 | AUD-002 | P0 | independent-reviewer | six_state_report_review |
| 3 | AUD-003-03 | AUD-003 | P1 | owner | schema_review |
| 4 | AUD-004-05 | AUD-004 | P0 | independent-reviewer | isolated_env_integration_test |
| 5 | AUD-005-03 | AUD-005 | P1 | independent-reviewer | tool_config_verification |
| 6 | AUD-006-05 | AUD-006 | P1 | independent-reviewer | memory_integration_test |
| 7 | AUD-007-03 | AUD-007 | P1 | independent-reviewer | transition_log_review |
| 8 | AUD-009-04 | AUD-009 | P0 | independent-reviewer | real_side_effect_e2e |
| 9 | AUD-010-04 | AUD-010 | P0 | independent-reviewer | recovery_drill |
| 10 | AUD-011-04 | AUD-011 | P1 | independent-reviewer | breaker_drill |
| 11 | AUD-012-03 | AUD-012 | P0 | independent-reviewer | pilot_repo_inspection |
| 12 | AUD-013-04 | AUD-013 | P1 | independent-reviewer | permission_matrix_review |
| 13 | AUD-014-04 | AUD-014 | P0 | independent-reviewer | audit_backend_review |
| 14 | AUD-015-04 | AUD-015 | P0 | security-owner | security_owner_approval |
| 15 | AUD-016-04 | AUD-016 | P0 | owner | data_matrix_approval |
| 16 | AUD-017-04 | AUD-017 | P1 | independent-reviewer | change_evidence_review |
| 17 | AUD-018-03 | AUD-018 | P1 | independent-reviewer | repo_gate_integration |
| 18 | AUD-019-02 | AUD-019 | P2 | owner | metric_dict_review |
| 19 | AUD-020-04 | AUD-020 | P0 | independent-reviewer | maturity_matrix_review |
| 20 | AUD-021-03 | AUD-021 | P1 | independent-reviewer + owner | signed_evidence_package |
| 21 | AUD-022-04 | AUD-022 | P1 | owner | reverify_policy_approval |

> 角色统计（建议）：independent-reviewer ×17、owner ×3（AUD-003/016/019/022 中
> 部分可兼任）、security-owner ×1（AUD-015，硬性）。AUD-021 需 independent-reviewer
> 与 owner 双签。所有签署人不得等于 `GOV_ACTING_IDENTITY`。

## 4. 仍受门控、本矩阵不解决的开放项（提醒，非本文件范围）

- **verified=0（EXC-02）**：需独立账号/主机，仅记录签署不足以 machine_complete。
- **10 个未关闭 P0 阻断（G2）**：需可复核证据 + 独立验证，仍需真实环境与资源。
- **显式未实现 6 条断言**：需真实远端/隔离环境/真实保留周期，超出脚手架范围。
- **EXC-01 到期日不一致**：报告记为 2027-01-31，基线记为 2027-04-30，待人工拍板统一。

本矩阵只解决"人工复核时照什么表填"，不替代上述任何关闭动作。
