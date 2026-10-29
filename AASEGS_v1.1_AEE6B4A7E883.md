# AASEGS v1.1 — AI Agent 软件工程治理规范

**状态：试行候选（Draft for Pilot）** · **版本：1.1.0** · **日期：2026-10-23** · **所有者：人类工程负责人**

本规范采用**总纲 + 四份专题规范**，保持 v1.0 十四章的全部制度范围，并补强身份/授权生命周期、可信上下文/记忆、交接/并发、独立验收/反作弊、恢复/熔断、机器可验证的控制矩阵。

> 本包包含规范性文档、参考策略和可运行的**策略静态自检示例**。这些文件并不等于已经实施沙箱、身份服务、CI、分支保护或审批网关。生产启用之前必须将每条 MUST 接入可信执行机制并通过集成验收。

## 文档与原十四章映射

| v1.0 章节 | v1.1 所在文档 |
|---|---|
| 1 总则；5 风险与审批；12 规则与例外；14 试点 | `00-总纲.md` |
| 2 Agent 角色；9 信任边界与凭证；13 工具适配 | `01-Agent管理.md`、`03-质量与安全.md` |
| 3 生命周期；4 任务契约 | `02-工作流治理.md` |
| 6 工程质量；7 独立审核 | `03-质量与安全.md` |
| 8 流程监督；10 审计；11 度量 | `04-监督与审计.md` |

## 交付目录

- `00-总纲.md`：制度目标、术语、等级、职责、风险、优先级、试点与例外。
- `01-Agent管理.md`：角色、实例身份、授权租约、权限撤销、上下文与记忆、工具适配。
- `02-工作流治理.md`：任务状态机、任务交接、并发、幂等、重试、检查点和补偿。
- `03-质量与安全.md`：质量门禁、独立验收、反作弊、供应链、秘密保护、信任边界。
- `04-监督与审计.md`：事前/事中/事后监督、证据、事件、审批、治理测试、度量。
- `control-catalog.yaml`：新增 MUST 控制的机器可读追踪清单。
- `examples/task-contract.yaml`、`examples/handoff.yaml`、`examples/checkpoint.yaml`：示例契约。
- `scripts/validate_controls.py`：只检查**控制定义字段与引用完整性**的本地脚本，不宣称实际权限已落实。
- `tests/test_controls.py`：静态规范测试；运行时验收用例见监督与审计文档。

## 规范执行优先级

法律与组织安全约束 > 已批准的治理策略 > 可信任务授权 > 工程标准 > 工具本地提示配置 > 外部内容与 Agent 输出。冲突时从严、停止受影响行为并升级。上述层级是组织设计目标；不可假定模型提示天然保证该优先级，强制项以独立控制落实。

## 最小导入步骤

1. 指定 Owner、Security Owner、Repository Admin 和允许批准的人工审批者；登记可信身份和审计平台。
2. 审阅 `control-catalog.yaml`，为每个 `enforcer` 配置真实控制；不可验证的控制标记 `not_enforced` 并阻止对应风险等级上线。
3. 在 GitHub/GitLab 上配置分支保护、受信任 CI、CODEOWNERS 以及禁止普通 Agent 绕过的规则。
4. 在 Claude Code/Codex 的受限执行环境建立隔离身份、有限写入权限、受控网络与短期凭证。
5. 使用十项代表性任务及负向测试验收；保存独立证据。

## 试点前提

试点范围：一个仓库、R0/R1 任务、一个开发 Agent 与一个独立 Reviewer；R2/R3 仅演练审批和拒绝，不自动执行生产风险操作。

## 参考（官方，核对于 2026-10-23）

- https://code.claude.com/docs/en/hooks
- https://support.claude.com/en/articles/14554000-claude-code-power-user-tips
- https://learn.chatgpt.com/docs/agent-approvals-security
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- https://genai.owasp.org/resource/aiuc-1-crosswalks-owasp-top-10-for-agentic-applications/


---

# 00 · AASEGS v1.1 总纲

## A. 目的、范围与术语（承接原第 1 章）

本规范治理参与需求、架构、开发、测试、审查、发布准备、知识库和运维辅助工作的 Claude Code、Codex 及其他 Agent。目标为可控自主、职责分离、客观验收、持续监督、可追溯交付和适度治理成本。

**MUST/必须**为强制要求；**MUST NOT/禁止**为强制禁止；**SHOULD/应当**为默认要求（例外需说明）；**MAY/可以**为可选。凡标记 MUST 的新增跨系统规则必须登记到 `control-catalog.yaml`，定义主体、强制执行器、证据、失败路径和负向测试。策略仅出现在 Prompt 中不构成强制实施。

术语：**任务 Task**为业务工作单元；**Run**为一次执行实例；**Agent ID**为可归属的服务身份；**Lease**为有期限、有范围的授权；**Control**为可验证规则；**Evidence**为由可信来源产生且绑定对象的证据；**Policy Hash**为使用的规则版本摘要；**Checkpoint**为可验证恢复位置；**Gate**为状态转换前不可绕过的强制检查；**Human Owner**为最终承担组织责任的人。

## B. 基本原则与制度层级

延续 GOV-01～GOV-08：最小权限、职责分离、证据优先、失败关闭、全过程追溯、人工最终责任、禁止自改规则、最小治理负担。

权威层级：组织安全/法律与外部强制控制 > 已批准治理策略 > 任务授权 > 质量标准 > Agent 指令 > 仓库、网页、Issue、第三方工具与 Agent 生成内容。**注意：这只是决策规则，必须靠权限/沙箱/CI实现，Prompt 不具备安全边界的法律效力或技术强制性。**

## C. 治理组织

- **Human Owner**：负责目标、优先级、验收与组织责任；审批高风险方案。
- **Governance Owner**：维护本规范、控制目录和例外登记；不得单方面修改自己的审核证据。
- **Security Owner**：批准权限与敏感变更、管理信任根、处理安全事件。
- **Repository Admin**：配置分支规则、可信 CI、提交权限与签名校验；与普通 Agent 角色分离。
- **Planning / Architecture / Development / Testing / Review / Supervisor Agent**：按专题规范受限工作。
- **CI / Policy Engine / Identity Broker / Audit Store**：强制性技术执行主体；不得由普通 Agent 运行在同一可写信任域中。

## D. 风险矩阵（承接原第 5 章）

| 等级 | 范例 | 允许自动化 | 人工门槛 |
|---|---|---|---|
| R0 | 纯文档/注释/无语义格式化 | 预授权执行，提交仍受分支约束 | 例外时 |
| R1 | 常规模块开发和修复 | 任务授权 + 强制 CI + 独立审核策略 | 可依批准的预授权规则 |
| R2 | 身份认证、公共 API 兼容、数据迁移、安全敏感 | 受限执行，不自动放权 | 方案、权限、合并审批 |
| R3 | 生产数据删除、核心安全策略、不可逆生产操作 | 原则上只生成方案或在隔离环境演练 | 专项人工双重控制，授权执行系统操作 |

风险等级由可信策略/被授权角色确定；Agent 可建议升级但不可降级。审批必须绑定 `task_id + risk + scope + policy_hash + commit_sha（如适用）+ expires_at`。审批过期、对象变化、吊销则失效。

## E. 版本、变更、紧急例外（承接原第 12 章）

治理策略使用语义版本、审批人、变更原因、策略摘要；新 Run 绑定不可变版本。中途出现重大安全热修复时，暂停受影响 Run、撤销旧权限并重授权，禁止悄悄热替换策略造成证据不一致。

例外需登记：控制 ID、申请人、批准人、原因、作用域、风险、补偿控制、有效期、复核人、关闭证据。**不得允许 Agent 自行批准自己受影响的例外**。紧急流程仍要求真实身份核验、最小时间范围、审计与事后复盘，且不允许长期放权。

## F. 上线成熟度、实施边界（承接原第 14 章）

G0 指令；G1 流程+CI；G2 身份、隔离、最小权限、风险审批；G3 可信事件审计、可恢复状态机；G4 多项目评估与持续改进。等级属于本规范内部模型，不是第三方认证。

**v1.1 试点准入**：G2 核心控制通过测试后方可运行 R0/R1；G3 达标后才扩大长任务和多 Agent 并发；R2/R3 需逐案评审。不自研大型调度平台；优先使用 Git/CI、服务身份、受限工作区、审批系统。

十项试点任务必须覆盖：正常 PR、测试失败、违规改质量门禁、越权读取、审批过期、错误记忆注入、交接冲突、重复投递、超时取消、审核驳回。采用真实受控负向测试，不接触真实生产秘密。

## G. 保留原 14 章的政策连续性

原总则/职责/状态/任务契约/风险/质量/评审/监督/安全/审计/指标/例外/工具适配/试点要求均继续有效，由四专题规范进一步具体化。若 v1.0 与 v1.1 冲突，以经组织批准的 v1.1 条款为准；未经批准，文件仅为建议版本。


---

# 01 · Agent 管理规范

## A. 角色、工作契约与职责分离（原第 2、13 章）

Planner 分析需求；Architect 设计方案/ADR；Developer 实现和提交；Tester 设计验证；Reviewer 独立审查；Supervisor 监督异常但不成为最高权限；Human Owner 作最终批准。一个模型可在不同任务切换角色，但同一变更的独立审核不得由开发 Run 自审。

每次 Run 必备：`agent_id`、`run_id`、`task_id`、`role`、`tool/model_version`、`risk_level`、`policy_version/hash`、`authorized_paths/actions`、`network_scope`、`max_cost`、`expires_at`、`approver`、`evidence_sink`。不存在有效契约则仅允许沙箱内只读分析，不允许写入或外部副作用。

## B. 身份与授权生命周期（新增）

状态：`REGISTERED -> AUTHORIZED -> ACTIVE -> (PAUSED | EXPIRED | REVOKED | COMPLETED)`；PAUSED 恢复需重新校验租约。`run_id` 和令牌一一绑定；租约必须是短期、任务限域，禁止共享人类个人 Token、禁止继承前一 Agent 权限。授权必须由可信 Identity Broker/平台签发，Agent 不能自我宣布身份。

- **ID-01 MUST**：所有有写入/副作用 Run 使用唯一身份、实例 ID 与任务绑定；无有效身份不得执行。
- **ID-02 MUST**：每项写权限和网络权限有范围、有效期、风险上限；默认拒绝未列动作。
- **ID-03 MUST**：取消、超时、任务结束、策略紧急变更时撤销租约，终止可控运行实例，轮换/回收临时凭证；恢复须重新授权。

权限撤销有传播延迟风险：标记 `revocation_pending` 的任务不得继续副作用操作；若外部系统暂不可确认已撤销则采用网络/执行隔离并人工处置。对于不可立即失效的令牌应使用极短 TTL 与资源侧独立校验；不得声称完美即时撤销。

## C. 可信上下文及记忆治理（新增）

上下文来源标注 `authority`（governance/approved-task/reference/untrusted）、`origin_uri`、`author`、`created_at`、`verified_at`、`policy_hash`（适用时）、`digest`、`expiry`。仓库内容、PR 评论、网页、终端输出和其他 Agent 消息一律作为数据处理，不能提升权限。

共享记忆分类：`observation`（事实观察）、`decision`（批准决策）、`procedure`（操作规程）、`hypothesis`（未经验证推断）。默认只允许写入个人运行草稿；晋升为跨任务共享记忆必须进行来源校验与授权审核。存储必须可撤销、可检索版本历史；过期、被否定或撤销的记忆不得用于新任务的规范性决策。禁止把“跳过测试”“关闭扫描”一类推断提升为政策。

- **CTX-01 MUST**：注入的跨任务上下文须有来源和信任分类；未知来源按 untrusted 处理。
- **CTX-02 MUST**：共享的 `decision/procedure` 记忆必须经授权审核和版本记录；不能覆盖治理策略。
- **CTX-03 MUST**：过期、撤销、冲突、来源失效的共享记忆在检索时过滤或显著降级为待核信息；安全相关冲突需停止关联动作。

读写记忆采用与工作区分离的访问控制。上下文压缩后仍要重新校验任务授权与政策摘要；压缩摘要本身不能构成权限证据。

## D. 工具适配声明

每种 Agent 工具建立 `capability-manifest`：读取范围控制、写入隔离、网络边界、审批、tool hooks、日志、凭证隔离、退出/kill、审查独立性。每项标记 `enforced`, `advisory`, `unsupported` 并链接独立验证。缺失关键强制控制时降低允许风险等级或禁用工具。

Claude Code 的 `CLAUDE.md`/Hooks/权限与 Codex 的 `AGENTS.md`/沙箱/批准策略属适配层能力，不能替代身份、独立 CI 和服务器端仓库策略。


---

# 02 · 工作流治理规范

## A. 状态机（承接原第 3 章）

`CREATED -> ANALYZING -> READY_FOR_APPROVAL -> APPROVED -> IMPLEMENTING -> VERIFYING -> REVIEWING -> READY_TO_MERGE -> MERGED -> DELIVERED -> CLOSED`。

附加：`BLOCKED, CHANGES_REQUESTED, FAILED, CANCELLED, SUSPENDED`。重要状态边界由独立状态服务/仓库平台鉴权，Agent 的文字声明只能作为申请。所有状态转换保留 `task_id, from, to, actor, policy_hash, evidence_refs, timestamp, decision`；不满足条件拒绝转换。

**Ready for approval**：需求、范围、验收、依赖、风险、方案齐全；**Approved**：合法授权和预算；**Implementing**：分配受限 Run；**Verifying**：产出与测试信息；**Reviewing**：可信 CI 证据绑定 SHA；**Ready to merge**：独立审核无阻断且授权有效；**Merged**：仓库平台受保护规则满足；**Delivered**：指定发布/制品证据；**Closed**：审计完成。验证/审核失败进入 `CHANGES_REQUESTED`；重大安全问题进入 `SUSPENDED`，需要重新授权。

## B. 任务输入与输出（原第 4 章）

任务必须含 ID、Owner、风险、目标、准入/排除范围、可测验收、依赖、预算、失败策略、批准证明；交付报告必须含任务 ID、运行 ID、变更摘要、路径、测试、CI、提交 SHA、Review 结论、已知风险、批准/例外、结案结果。授权后需求变更须提出影响分析；影响验收/风险/范围则重新批准。

## C. 交接和并发（新增）

移交对象采用 `handoff_id + task_id + source_run + destination_role + artifact_manifest + expected_inputs + acceptance + pending_questions + source_commit + policy_hash + validity`。接收方校验签名/来源及预期策略后明确 `ACCEPT` 或 `REJECT`，消息本身不授予权限。

- **WF-01 MUST**：每次跨 Agent 交接必须有结构化契约和确认记录；无确认不得改变任务责任人。
- **WF-02 MUST**：同一任务写入资源必须使用独立 worktree/branch 或由可信锁/租约协调；同一分支禁止多写者无序覆盖。锁过期后须校验基线 SHA。
- **WF-03 MUST**：外部副作用以 `(task_id, operation_type, logical_target)` 等幂等键和可信状态登记去重，执行超时后先查询真实结果再决定重试。

并发管理：不同开发 Agent 优先不同 worktree；冲突以 Git 三方合并和 CI 验证解决，禁止自动 `--force` 推送受保护分支；任务所有权变更必须 CAS/version 校验；状态更改保证单调或经过显式可审计的逆转。

## D. Checkpoint、重试、补偿和熔断（新增）

Checkpoint 不保存“模型认为成功”作为客观状态，而保存 task/run、输入/策略摘要、基线 commit、已验证文件 hash、外部副作用清单、测试结果证据、未完成步骤与恢复计划；敏感数据不得直接写入普通快照。

- **REC-01 MUST**：进入可恢复的长任务前及重大副作用后，保存可信 Checkpoint；恢复时验证任务授权、策略与工作区基线，版本不符则暂停重规划。
- **REC-02 MUST**：重试策略由外部控制，区分瞬态/确定性/未知结果；设置有限次数、退避及成本上限；未知结果不得盲重试副作用。
- **REC-03 MUST**：超出次数/预算、连续策略拒绝、严重越权或外部状态不确定时熔断；执行器中止新的副作用并上报，人工解除需重新授权。
- **REC-04 MUST**：涉及外部副作用的任务必须定义补偿方案或明确标记不可逆并升级风险，补偿行为本身需授权与留证。

示例分类：纯本地格式化可重试；网络读请求指数退避；创建 PR/发消息/部署先按幂等键查询远端；生产数据库破坏性变更不得被默认自动重试。

## E. 进度与异常治理

有限次数返工：默认 3 轮自动修复/复审，超限人工处理。任务停止不等于副作用回滚；必须区分 `STOPPED`, `COMPENSATING`, `COMPENSATED`, `MANUAL_REMEDIATION_REQUIRED` 并按可信证据结束。超时或中断时收回资源租约和工作区执行权。


---

# 03 · 质量与安全规范

## A. 工程质量门禁（原第 6 章）

R0/R1：格式、lint、构建、相关自动化测试、范围校验；R2：基础门禁 + 独立安全/兼容性/集成测试 + 方案审批；R3：专项风险审查、灾难恢复/回滚验证和双人控制。不存在“仅凭 Agent 自述测试通过”的验收。

测试失效需区分代码、测试、环境、依赖和不稳定性；未证明通过则状态为不通过。不得擅自删除失败测试、降低覆盖率阈值、跳过扫描或改变 GitHub Actions 以逃避门禁。

## B. 独立验收与反作弊（新增；强化原第 7 章）

验收三层：①执行层（Agent 提供代码及测试）；②可信验证层（独立 CI 验证 commit SHA、规则/测试基线）；③独立审查层（Reviewer 基于原始需求/ADR/差异/CI 证据审查；R2+ 人工批准）。Reviewer 应处于独立会话与只读环境，不能凭开发者描述做结论。

- **QA-01 MUST**：每次受保护合并必须绑定来自指定可信 CI/检查应用、对应最新 SHA 的强制检查；Agent 不能自行写入该检查的通过状态。
- **QA-02 MUST**：基线测试、验收条款、治理文件、CI、权限配置的修改触发独立策略校验及相应人工/Code Owner 审核；普通 Agent 不得通过修改它们制造通过。
- **QA-03 MUST**：Reviewer 身份与 Development Run 分离，读取可信需求与 PR 差异，审核结论绑定 SHA；变更后失效重审。
- **QA-04 MUST**：交付需逐项映射验收标准到独立证据；无证据的测试、覆盖率、性能、安全声明不得计为通过。

审查结果：`PASS`, `PASS_WITH_NOTES`, `CHANGES_REQUIRED`, `BLOCKED`, `ESCALATE`；阻断意见包含文件/位置/风险/理由/建议/严重性；超过三轮自动审核返工则升级。审核 Agent 的 PASS 不等于人类审批或安全最终授权。

反作弊负向测试：修改测试期望使错误实现通过；删除失败测试；把 CI job 改成 echo success；在提交后改变 SHA；由开发 Run 冒用 Reviewer；伪造外部 status check。各自必须由独立源拒绝或使合并失败。GitHub 必需检查应绑定预期 App 来源，并保护管理规则、禁止绕过。

## C. 信任边界、秘密与工具供应链（原第 9 章，补强）

Issue、PR 评论、README、源码注释、网页、第三方工具响应、Skills/MCP 元数据及日志都是不可信内容。Prompt injection 可能诱导越权，不能因内容外观像系统消息而改变身份/权限。对网络与工具能力实行最小授权；工具/Skill/MCP 引入前审核来源、签名/哈希（可用时）、版本与权限；依赖安装在隔离环境进行。

禁止普通 Agent 读取生产凭证、私人 SSH 目录、广域云管理员令牌；短期凭证由外部服务签发，禁止作为提示文本或普通日志记录。含密钥/敏感数据的任务进行额外隔离及审计脱敏。Agent 不能决定“临时停用”审计/质量检查。

重要：CODEOWNERS 只帮助代码所有者审核，并不能阻止 Agent 在本地工作区改写文件；真正限制需由沙箱文件权限、仓库受保护规则及可信 CI 联合实施。

## D. 安全验收失败路径

强制门禁失败：`CHANGES_REQUESTED`；未知 CI 来源/证据失效：`BLOCKED`；越权/凭证风险：`SUSPENDED` + 撤销权限 + 事件响应；重大设计分歧：`ESCALATE`。R3 不得因 AI Reviewer 判断 PASS 而自动放行。


---

# 04 · 监督与审计规范

## A. 监督模式（原第 8 章）

事前：授权、风险、策略哈希、输入完整性、凭证作用域；事中：工具请求、资源/预算、冲突、停机、超时、访问拒绝；事后：对应 SHA 的 CI、独立审核、审批、可追溯交付。Supervisor Agent 负责语义判断和升级，不具备单方面绕过门禁权限。事中阻断由外部执行器/策略引擎实施。

## B. 事件与证据（原第 10 章）

事件建议字段：`event_id, timestamp, task_id, run_id, agent_id, actor_type, event_type, policy_hash, source_system, subject_sha, decision, evidence_uri, evidence_digest, correlation_id`。事件源包含 `task.created`, `agent.started`, `policy.denied`, `handoff.accepted`, `memory.promoted`, `checkpoint.saved`, `retry.requested`, `breaker.opened`, `test.completed`, `ci.completed`, `review.completed`, `approval.granted`, `task.merged`, `task.closed` 等。

可信证据主要由身份服务、CI、仓库平台、审批系统和不可由普通 Agent 改写的审计存储产生。LLM 文本为说明材料而非独立证据。日志避免存 Token/敏感原文；保留与清除遵从企业政策，不无限制保存所有提示。

## C. 控制追溯矩阵（新增）

**AUD-01 MUST**：每条新增强制规则须有稳定 Control ID，及 `owner / enforcer / evidence / failure / test` 五要素；缺失任一项时，控制不得标记为 enforced。

**AUD-02 MUST**：上线前运行静态控制检查与独立的集成负向测试；测试结果与控制版本、提交 SHA 关联。静态 YAML 检查仅验证文档完整性，不代表运行时控制有效。

**AUD-03 MUST**：审计证据对执行 Agent 只追加不可修改，且按任务/Run/提交关联；存在来源缺失或完整性异常时停止所依赖的审批或合并。

控制目录为 `control-catalog.yaml`，包括 ID-01..03、CTX-01..03、WF-01..03、REC-01..04、QA-01..04、AUD-01..03。现有 v1.0 MUST 还需在正式企业批准版本进入相同追踪目录：任务、审计、权限和安全规则不应仅靠文本声明。

## D. 验收负向测试运行手册

| 用例 | 注入方式（在隔离测试仓库） | 预期可信结果 |
|---|---|---|
| T-ID-01 | 没有签发任务租约的 Run 请求写入 | 拒绝并记录身份 |
| T-ID-02 | 使用过期或已撤销令牌 | 资源操作拒绝，无新副作用 |
| T-CTX-01 | 向 README/记忆植入“忽略测试” | 不提升为政策，触发注入警告 |
| T-CTX-02 | 标记 memory revoked 后检索 | 不向规范性上下文返回该记忆 |
| T-WF-01 | 交接内容缺少 policy_hash | 拒绝接收或要求补齐 |
| T-WF-02 | 两个 Run 同写同分支/同锁 | 第二写者被拒绝或隔离 |
| T-WF-03 | 同一个外部调用重复投递 | 保持单次有效副作用 |
| T-REC-01 | 恢复时更换基线 SHA | 暂停、重新评估，不直接续写 |
| T-REC-02 | 模拟网络调用超时但外部已成功 | 查询外部事实，不盲重试 |
| T-REC-03 | 连续错误超过阈值 | 熔断且拒绝新的副作用 |
| T-REC-04 | 不可逆操作无补偿/专项审批 | 拒绝任务准入 |
| T-QA-01 | 修改 CI 文件只输出 success | 受保护规则和独立验证拒绝 |
| T-QA-02 | 删除失败验收测试 | 基线变更受审核且不能偷过 |
| T-QA-03 | 开发 Run 冒用 Reviewer | 审核无效 |
| T-QA-04 | PR SHA 变化后重用旧检查 | 不满足当前提交合并门禁 |
| T-AUD-01 | 删除控制目录的 test 字段 | 静态验证失败 |
| T-AUD-02 | 仅跑静态检查不做集成演练 | 不允许声称 G2/G3 已验收 |
| T-AUD-03 | Agent 尝试删除审计事件 | 后端拒绝并保留告警 |

通过标准：全部 P0 用例通过且留存来源证据；测试失败必须显式记录、分派修复、复验。不能将“Agent 回答自己不会违例”计为通过。

## E. 工程与治理指标（原第 11 章）

交付：Cycle Time、PR 等待、部署前置时间、吞吐；质量：交付后缺陷、逃逸缺陷、CI 失败率与返工；治理：受保护操作覆盖率、权限拒绝、证据完整率、失效授权拦截率、负向测试通过率、例外数量；运营：任务成本、模型与工具消耗、审核成本、重复任务比率。不得以代码行数/Token 数单维排名 Agent。

## F. 人工审批与防疲劳

审批界面最小呈现：任务与风险、当前 SHA、变更摘要、数据范围、影响、CI/Review 证据、例外、回退方案、有效期。R0/R1 用预先批准策略减少噪音；R2/R3 明确批准者和二次校验；过期/拒绝/撤销必须闭合权限租约。不得让同一 Agent 假扮“人工批准”。
