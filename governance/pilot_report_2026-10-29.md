# AASEGS 试点阶段报告（2026-10-29）

**仓库**：slow-is-fast/engineering_manager（public）
**规范基线**：AASEGS v1.1.0 → v1.1.1（已于本报告批准日转正为正式生效，见 §8）
**报告性质**：PKG-01（试点证据包）首次履行。对照其八项要求逐项填写。
**读者**：Human Owner / Governance Owner——本报告是状态推进与版本转正的评审输入。

---

## 1 · 环境与版本

| 项 | 值 |
|---|---|
| 仓库 | public，分支保护已生效（required check strict + CODEOWNERS 1 审批 + 禁 force push/删除） |
| CI | `.github/workflows/governance.yml`（`governance / static-gate`），历次运行全绿 |
| 目录版本 | control-catalog **v1.1.1**（44 条控制）、rule-registry **v1.1.1**（52 条规则） |
| 审计基线 | AASEGS v1.1.0 审计问题清单 22 项 |
| 演练工具 | `scripts/validate_controls.py`、`tests/`（16 测试）、`tests/negative_static.py`、`executor/`（六组件） |
| 控制面 | `slow-is-fast/aasegs-gov-plane`（VD-01，2026-10-29 批准后部署，见 §10） |

## 2 · 风险范围

按 00-总纲 F 的试点准入：本次全部活动限定 **R0/R1**（文档、脚本、演练注入），未执行任何 R2/R3 生产风险操作。演练注入全部发生在独立分支，已删除，main 无违规内容合入（每轮演练后均校验）。

## 3 · 控制状态快照

**44 条控制：tested 15 / not_enforced 29。**（§10 批准后跟进：VD-01 登记后为 **45 条控制，tested 16 / not_enforced 28**）

| 类别 | 条目 | 状态 |
|---|---|---|
| 平台类（REG/QA 系） | REG-01、REG-02、AUD-01、QA-01、QA-02、QA-04 | tested 6 |
| 执行器类（WF/CNC/CTX/REC/EFF/BRK 系） | WF-01、WF-02、CNC-01、CTX-02、CTX-03、REC-01、REC-03、EFF-01、BRK-01 | tested 9 |
| 其余（身份、审计存储、事件响应、指标等） | 29 条 | not_enforced |

六态分布：tested 15、documented 29、verified **0**、configured 1（BASE-01 部分配置）。§10 后：tested 16（+VD-01，configured 1）、documented 28。

**tested 与 verified 的边界**：tested = 控制逻辑在负向用例中按预期拒绝注入；verified 需要独立信任域部署（GOV-14 gap 适用）。执行器与被治理代码同仓库，其 9 条 tested 属"逻辑验证"。

## 4 · 测试结果汇总

| 轮次 | 对象 | 结果 | 关键结论 |
|---|---|---|---|
| 静态负向 | T-REG-01/02、T-AUD-01 | ✅ 4/4（含阴性对照） | 未注册条款被检出、伪造 verified 被拒 |
| Round 1 | T-QA-01/02（无分支保护） | ❌ **注入成功** | 检测层对"删测试/篡改 CI"原理性失明；防线只剩人 |
| Round 2 | T-QA-01/02（分支保护生效） | ✅ 注入被拒 | "PR 作者不能自批"是关键机制；CODEOWNERS 改写无效 |
| Round 3 | T-QA-04（SHA 绑定） | ✅ | 三 SHA 三结果（绿→红→绿），旧结果不可复用，门禁精确 |
| 执行器 | 10 条负向用例 | ✅ 10/10 | 六组件全部按预期拒绝注入；抓到空 manifest 误判 bug |

## 5 · 证据索引

| 类型 | 位置 |
|---|---|
| 静态负向证据 | `evidence/static_negative_*.json` |
| Round 1（失败案例） | `evidence/runtime_drill_20261029T144000Z.md`、PR #1（已关） |
| Round 2 | `evidence/runtime_drill2_20261029T150500Z.md`、PR #2 / PR #3 |
| Round 3 | `evidence/runtime_drill3_20261029T151500Z.md`、PR #4、CI run 40832319336 / 40832439900 / 40832571407 |
| 执行器 | `evidence/executor_20261029T154500Z.md`、CI run 40837846884 |
| 差异核对与修补 | `AASEGS_v1.1_会话与本地文件差异核对报告.md`（第八节修补记录） |

每条 tested 控制的 `integration_evidence_uri` 均指向可核查的 PR 或 CI run。

## 6 · 失败与例外

如实登记，无粉饰：

1. **Round 1 注入成功**（T-QA-01/02）：根因 INFRA-01（免费私有仓库无分支保护）。已通过转公开解除，但该案例保留了完整记录——它是"检测层≠强制层"的实证。
2. **INFRA-01**：已解除（public + 分支保护）。教训：平台层强制是有真实成本的（付费或公开）。
3. **handoff 空 manifest 误判 bug**：`not value` vs `value is None`，由正向对照用例发现并修复。
4. **6 条规则无运行时控制**（GOV-08 原则性条款除外为 5 条）：GOV-14（信任域分离）、AGT-005、WFL-001/002、SUP-005，均有 gap 说明，待控制化决策。
5. **22 项审计问题 0 关闭**：tested ≠ closed；关闭需满足各自 closure_criteria 并经独立复核。
6. **未覆盖**：T-ID 系列（需身份服务）、T-QA-03（需第二凭证）、WFL-003 实测（Owner 凭证下 force push 不受限）、全部 R2/R3 演练。

## 7 · 复验要求

以下结论依赖当前配置，复验时必须重查：

- 分支保护配置未回退（`gh api repos/.../branches/main/protection`）
- `governance / static-gate` 仍为必需检查且 workflow 未被篡改
- 执行器测试在 CI 中持续通过
- 仓库保持 public（或升级 Pro 后等效配置）

## 8 · 批准结论（Owner 已于 2026-10-29 批准）

批准人：**slow-is-fast**（2026-10-29）

- [x] **确认试点范围与证据充分性**——批准。R0/R1 层 5 条运行时用例有结论（含 Round 1 失败案例），证据链 PR/CI 可核查。
- [x] **指派 22 项审计问题的 owner**——指派 **slow-is-fast**，全部 OPEN；分配记录见 `AASEGS_Audit_Issues_Full.md` §二·A。
- [x] **决策 5 条 gap 规则的控制化优先级**——批准按以下顺序推进：① GOV-14（新增 VD-01 信任域分离，verified 的前提）→ ② SUP-005（并入 identity attestation，随 WP-02）→ ③ WFL-001/002（执行器 handoff 准入检查承担，成本最低）→ ④ AGT-005（文档审查流程化，最低）。决策已写入 `rule-registry.json` 各规则的 `gap_uplift` 字段。
- [x] **v1.1.1 转正**——批准。从「实施完整性修订候选」转为**正式生效**，转正记录见规范头部。关闭门槛不变：未关闭 P0 仍阻止对应风险等级准入。
- [x] **批准下一批试点**——批准，范围与优先级：① 执行器独立信任域部署（解锁 GOV-14 gap 与 verified 授予）→ ② T-ID 系列 / T-QA-03（需身份服务与第二凭证）→ ③ WFL-001/002 准入检查扩展（基于现有 handoff 契约）。

## 9 · 对五步计划的定位

| 计划步骤 | 状态 |
|---|---|
| 一、规则注册表 | ✅ 完成（52 条） |
| 二、控制映射与测试矩阵 | ✅ 完成（44 控制 ↔ 44 用例，15 tested） |
| 三、落实 P0 控制 | ✅ 完成（CI + 分支保护 + 执行器；P0 控制 13 条中 8 条 tested） |
| 四、真实仓库试点 | 🟨 **进行中**（R0/R1 层 5 条运行时用例有结论，含失败案例；身份/审计存储类未动） |
| 五、按试点结果修订 | ⬜ 未开始（注意：现有 v1.1.1 是审计驱动修订；试点驱动的修订应为 v1.1.2/v1.2） |

## 10 · 批准后跟进：VD-01 执行器独立信任域部署（2026-10-29 16:20–16:45）

§8 批准的下一批试点第①项已开工并完成首轮：

- **控制面仓库** `slow-is-fast/aasegs-gov-plane`：executor 六组件 + 10 条负向用例 + 控制面 CI（run 40841631946 绿）+ 分支保护（required check + CODEOWNERS 审批 + 禁 force push/删除）。
- **pin 绑定**：数据面 `governance/executor_pin.json` 绑定控制面不可变 commit `4cf9bbe9…`（含 tree SHA 与内容哈希）。
- **T-VD-01**：正向 PASS；负向 2/2 被拒（篡改 commit_sha、篡改 content_hash 均失败关闭）；已接入数据面 CI。
- **登记**：控制 44→45（VD-01，P0，tested），GOV-14 gap 消除（gap 规则 6→5），测试断言同步（45/25）。
- **诚实边界**：账号级隔离（独立 org/账号）未部署，Agent 凭证分域待落地——VD-01 为 tested（逻辑验证），**verified 仍为 0**。

详见 `evidence/vd01_20261029T163000Z.md`。

### §10.1 T-VD-01b 凭证域分离（16:35 补录）

- **机制**：数据面 CI 运行时凭证（github.token）只授数据面；`scripts/verify_credential_domain.py` 对控制面做无害写尝试，CI 模式断言 403 拒绝，意外成功则清理并失败关闭。
- **本地演示**：Owner 全量凭证跨域写**成功**（drill label 即建即删，控制面核查无残留）——人横跨两域属预期，登记使用约束"该凭证不得交给数据面 Agent"。
- **结论**：数据面运行时凭证分域已由 CI 连续证明；verified 剩余门槛：①独立 org/账号；②Agent 日常运行切换到 fine-grained PAT（只授数据面）。

### §10.2 WF-05/WF-06 契约要素校验（16:50 补录）

- **执行器源码归属控制面**：`executor/contract.py`（控制面提交 `21099cb…`），数据面同步并 bump pin（`previous` 记录旧值 + `bump_reason`）；控制面 CI run 40844523493 绿，负向用例 10 → 12。
- **T-WF-05**（WFL-001 任务契约 11 要素）：缺项/占位值/非法风险等级/批准证明不全/**作者自批** 共 5 项注入全部 REJECT，正向对照 ACCEPT。
- **T-WF-06**（WFL-002 交付报告 11 要素）：缺 SHA/伪造 SHA/非法结案/类型错误 4 项注入全部 REJECT，正向对照（空列表合法）ACCEPT。
- **过程错误**：初版控制号 WF-03/WF-04 与既有 WF-03 撞号，被 `duplicate id` 断言拦下，改为 WF-05/WF-06。
- gap 规则 5 → **3**（剩 GOV-08 原则性、AGT-005、SUP-005，均有 uplift 决策）。控制总数 45 → **47**，tested 16 → **18**。

### §10.3 ATT-01 / CLM-01（17:10 补录）：gap 收敛至 1 条

- **ATT-01**（SUP-005，P0）：控制面 `executor/attestation.py`（提交 `2148e61…`，pin 已 bump）。7 项注入全部 REJECT：Agent 冒充人类主体、非人类 principal_type、主体不在白名单、带内自证通道、旁证不可核查、缺字段、策略不符；正向对照 ACCEPT。诚实边界：无 IdP 签名时只能证明"材料齐全且主体不似 Agent"，不能证明审批人本人操作。
- **CLM-01**（AGT-005，P1）：数据面 `scripts/check_claims.py`，扫描 17 份文档检出无证据支撑的绝对化声明；负向被抓、正向（实测数据 / 免责声明）放行。lint 调参两次修正误报（存档 HTML、免责句）。
- **账本**：控制 47 → **49**，tested 18 → **20**，P0 15；**gap 规则 3 → 1，仅剩 GOV-08 原则性条款（按设计不设运行时控制）**。

### §10.4 凭证域与主体独立性演练（17:20 补录，用户提供 fine-grained PAT）

- **T-VD-01b / T-ID-02 实证**：agent 凭证在数据面可写（建/删分支成功，正向对照），对控制面写被 **403 拒**。ID-02 推进为 tested。
- **重要方法学发现**：GitHub 仓库 API 的 `permissions` 对象对 fine-grained token **不可信**（两仓都返回 push/admin=true），判定凭证域必须做**真实写尝试**，不能读 permissions 字段。
- **T-QA-03 结论（负面但关键）**：第二 PAT **不构成独立主体**——PR #5 用 agent token 创建，Owner 凭证与 agent token 审批均被 `Can not approve your own pull request` 拒绝。平台按**主体**而非**凭证**判定审批独立性。因此 QA-03 / RVW-01 维持 not_enforced，需第二人类账号或 App 身份才能覆盖。
- 清理：PR #5 已关闭未合入，分支已删，open PR 数 0。token 仅存在于会话，未写入任何文件/提交；**建议用后立即轮换**。

---

## 11 · 单人开发者 + 多 Agent 场景适配（2026-10-29 收官）

Owner 明确场景约束：**只有一名人类开发者，但有多个 Agent**。据此对两项未达成项做正式处置——跳过不等于消失，按《审计问题清单》§2 登记为 `ACCEPTED_RISK`（例外登记见 `governance/exceptions_2026-10-29.md`）。

| 例外 | 涉及 | 不可达原因 | 补偿控制 | 到期 / 撤销条件 |
|---|---|---|---|---|
| **EXC-01** | QA-03 / RVW-01 第二人类审批主体 | 第二 PAT ≠ 第二主体（PR #5 实证，平台按主体判定） | 评审与写入**分凭证**（评审用只读 token）+ `verify_reviewer_credential.py --expect-deny` 机器化校验 + 评审证据绑定 SHA + 平台服务器端拒绝自批 + 人类执行 merge | 2027-01-31；引入第二人类主体或组织级 App 身份即撤销 |
| **EXC-02** | verified 授予（独立 org/账号） | 单账号、无独立主机 | 控制面独立仓库 + SHA pin + 运行时凭证分域 + Agent 凭证限域 + 执行器源码只读引用（pin bump 流程已实跑） | 2027-04-30；具备独立账号/主机并完成部署验收即撤销 |

**新增工具**：`scripts/verify_reviewer_credential.py`——校验评审凭证是否只读；已用当前**可写** agent token 反向验证：正确判定"不合格"并自动清理探测分支。`RVW-02` 暂列为**候选控制**，不登记进目录（尚无 tested 证据），待只读 PAT 创建后实测再登记——避免用未验证条目虚增覆盖数。

**多 Agent 操作约定**：一 Agent 一 token、限域单仓 + 短期轮换、只读 Agent 与写入 Agent 分凭证、token 不落盘。

## 12 · 最终结论（2026-10-29）

- **规范**：AASEGS v1.1.1 已由 Owner 批准**转正为正式生效版本**。
- **账本**：控制 **49 条**、**tested 21**、P0 15、**gap 1 条**（GOV-08 原则性条款，按设计不设运行时控制）、**verified 0**（诚实标注，不提前宣称）。
- **闭环**：52 条规则全部可追踪；49 条控制一一对应独立负向用例；控制面与数据面双面 CI 连续验证（pin + 凭证域 + 目录 lint + 27 项测试）。
- **已归档失败案例**：Round 1 注入成功（无分支保护）、workflow 步骤名冒号导致 YAML 解析失败、CLM-01 lint 自指误报、控制号 WF-03 撞号、第二 PAT 不构成独立主体。
- **未关闭**：22 项审计问题全部 OPEN（owner 已指派）；关闭须逐项满足验收条件并独立复核。
- **下一步（Owner 可选）**：创建只读评审 PAT 以登记 RVW-02；具备条件时推进独立账号部署以解锁 verified。

### §10.5 RVF-01 证据新鲜度与持续复验（18:15 补录）

- **机制**：22 条 tested 控制全部补 `evidence_at`；lint 新增断言"tested 必须有时间戳"；`scripts/verify_evidence_freshness.py` 按 TTL（P0 30 / P1 90 / P2 180 天）判定，`--enforce` 过期即失败关闭并**接入 CI**，`--degrade` 可将过期控制置 `degraded=true, tested=false`。
- **测试 5/5**：过期被拒、无时间戳被拒、新鲜不误杀、降级写回生效、仓库回归 fresh 22 / stale 0。
- **诚实边界**：本机制判定"证据是否过期"，不等于"控制仍有效"——它强制复验发生，不是复验本身。
- **时间表**：P0 证据 2026-11-28 起 CI 转红，须复验后更新 `evidence_at` 复绿。控制 tested 21 → **22**。

### §10.6 CHG-01 策略变更影响评估（19:05 补录）

- **实现**：控制面 `executor/change.py`（提交 `0cf3cba…`，pin 已 bump）。活动 Run 注册表 + 受影响集合计算 + 逐 Run 处置决定（continue/pause/reauthorize/terminate），**缺省即失败关闭**；**重大安全热修复禁止 continue**（GOV-16 核心）；reauthorize 需与新策略一致的人类审批且不得自批。
- **T-CHG-01**：8 项注入全部 REJECT（缺处置/漏处置/非法值/severe+continue/重授权无证明/策略不符/Agent 审批）+ 正向对照 PUBLISHED（受影响集合计算正确，已是新策略的 Run 不计入）。
- **诚实边界**：只强制"变更影响分析 + 处置"流程闭环，不替代权限平面的真实撤销/重授权。
- **遗留**：CHG-01 标 P1 而其规则 GOV-16 为 P0（TTL 90 天 vs 应 30 天，未计入 P0 统计）；同类风险等级不一致共 17 处，待补传播约束。控制 tested 22 → **23**。

### §10.7 风险等级传播修正（19:10 补录）

- **规则**：控制风险等级**不得宽松于**其所服务规则的最高等级（从严允许、从宽禁止）。等级不是标签——它驱动 RVF-01 的 TTL、GOV-18 的准入判定与优先级排序。
- **修正 4 处（只升不降）**：APR-01、CHG-01、RVW-01、CNC-01 由 P1 → **P0**（各自服务的最高规则等级均为 P0）。未调整：REG-01/CKP-01/BASE-01/GATE-01（标 P0 但仅服务 P1 规则，属合法从严）。
- **P0 控制 15 → 19**。
- **防漂移**：`validate_controls.py` 新增传播断言（负向对照：APR-01 标回 P1 被拒；正向恢复 P0 通过）。
- **诚实代价（已确认由 Owner 接受）**：APR-01、RVW-01 升 P0 后仍 `not_enforced` → 形成"P0 控制未强制"，按 GOV-18 **阻塞对应风险等级准入**；CNC-01（tested）TTL 由 90 天变 30 天，2026-11-28 前须复验。这是把此前"标低等级换来的宽松"还原为真实约束，不是回归。
- 注：§12 最终结论中的"P0 15"应读作 **19**。

### §10.8 APR-01 人工审批闸门（19:20 补录）

- **实现**：控制面 `executor/approval.py`（提交 `0e1aea5…`，pin 已 bump）。审批绑定 task_id/risk/scope/policy_hash/commit_sha/expires_at，任一漂移即失效；过期、吊销失效；R3 须人类审批，AI Reviewer PASS 不单独放行。
- **T-APR-01**：10 项注入全部 REJECT（未知 ID / 过期 / commit 漂移 / 范围扩张 / 风险升级 / 策略漂移 / 任务漂移 / 吊销 / 非人类签发 / R3+AI PASS）+ 正向对照 APPROVED。
- **诚实边界**：只验证"审批记录与当前请求一致"，不证明审批人本人意愿（身份服务职责）。
- **准入影响**：§10.7 中因 APR-01 升 P0 而产生的"P0 未强制"阻塞**已解除**。P0 仍未强制剩余 11 条：AUTH-01/02、ISO-01、CKP-01、BASE-01、RVW-01、EVD-01/02、INC-01、GATE-01、CRED-01（其中 RVW-01 受 EXC-01 约束）。控制 tested 23 → **24**。

### §10.9 EVD-01/02 防篡改审计流（19:30 补录）

- **改造**：控制面 `executor/audit.py`（提交 `1eb4d3b…`，pin 已 bump）升级为哈希链——事件带 seq/prev_hash/hash；`verify()` 检出篡改/删行/重排/截断；`read(strict=True)` 与 `ensure_available()` 在缺失/损坏/链失败时抛 `AuditUnavailable`（失败关闭）。
- **T-EVD-01**：篡改内容、删行、重排三类注入全部检出，正向对照通过。
- **T-EVD-02**：缺失 + 损坏两类场景均抛异常，正向对照通过。
- **诚实边界**：哈希链使篡改**可检测**而非**不可篡改**（写入权限仍在持有者手里）；真正防篡改需独立审计存储与权限分离（AUD-014 / GOV-14）。
- **影响**：控制 tested 24 → **26**；P0 未强制 11 → **9**（AUTH-01/02、ISO-01、CKP-01、BASE-01、RVW-01、INC-01、GATE-01、CRED-01）。原有 15 条执行器用例向后兼容保持绿。

### §10.10 ISO-01 跨项目数据隔离（21:05 补录）

- **实现**：控制面 `executor/scope.py`（提交 `2e60be6…`，pin 已 bump）。Run 绑定 project_id/repository_id/tenant_id；跨项目、跨租户、跨仓库、通配范围、未绑定 Run 一律默认拒绝并写 `boundary_violation`；未分类数据按最高敏感级别处理。
- **T-ISO-01**：6 项注入全部 REJECT + 正向对照 ALLOWED；审计流正确记录违规与"未分类按最高敏感"。
- **诚实边界**：进程内边界判定 ≠ 租户隔离（还需存储层权限与网络策略，AUD-016 完整范围）。
- **影响**：控制 tested 26 → **27**；P0 未强制 9 → **8**（AUTH-01/02、CKP-01、BASE-01、RVW-01、INC-01、GATE-01、CRED-01）。

### §10.11 CKP-01 / BASE-01（2026-10-30 09:15 补录）

- **CKP-01**：控制面 `executor/checkpoint.py` 扩展 `pre_restore_check()`（提交 `e58d856…`，pin 已 bump）。恢复前四项校验（授权有效 / 策略一致 / 基线一致 / 副作用无 UNKNOWN），任一不符暂停重评并写审计；**不可补偿操作 + 条件不符 → MANUAL_REMEDIATION_REQUIRED**。T-CKP-01：5 项注入全暂停（含人工处置 1 项）+ 暂停期间不得续写 + 正向对照 RESUME。
- **BASE-01 状态同步**：其用例 T-QA-04 已于 Round 3（PR #4 / CI run 40832571407）实跑（三 SHA 绿-红-绿，旧检查不可复用），此前目录状态未跟上——属账本漂移，已据既有证据置 tested（evidence_at=2026-10-29）。
- **影响**：控制 tested 27 → **29**；P0 未强制 8 → **6**（AUTH-01/02、RVW-01、INC-01、GATE-01、CRED-01）。用例 18 → 19。
