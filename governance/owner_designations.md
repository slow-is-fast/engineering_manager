# Owner 阻塞点决策记录（owner_designations）

- 状态：#2~#6 共 5 项决策已记录（Owner 拍板，2026-11-01；其中 #2 后经续批由 A 修订为 B，见变更记录）
- 背景：本包「单人 + 多 Agent」solo 开发；独立 Reviewer 已单独指定于
  `reviewer_designation.md`。本文件记录其余 5 个阻塞点的 Owner 决策与诚实边界。
- 本文件**不关闭任何断言、不翻转 `verified`**；仅将阻塞点从「空白」推进到
  「已指定 + 已记录」。
- 关联脚本：`scripts/matrix_caretaker.py`（#3 caretaker，只读巡检）、
  `scripts/apply_signoffs.py`（#6 自动翻，含 review-agent 绑定守卫）。

## #2 Security Owner 建制（AUD-015-04）—— 决策 B：独立 AI agent 作 Security-Owner 代理

- 指定：solo 阶段 Security Owner 职责由**独立 AI agent**（security-owner 代理，
  记作 `sec-agent`）担任，其模型家族**独立于作者模型**（`reviewer_designation.md`
  同款独立性判据：与作者 `hy3`/Hunyuan 不同家族）。
- 诚实声明：AI 代理 ≠ 真实独立人类；它**不替代**正式合规审计对「职责分离」的
  人类独立性要求（AUD-015-04 硬性）。本决策是 solo 阶段「有角色在看」的务实覆盖，
  对外正式合规时仍须升级为独立人类 Security Owner。代理的任何签署/裁定一律经由
  #6 签署流程，且受防自批守卫约束（AGT-001 / GOV-17）。
- 关联：AUD-015-04（硬性）。本决策提供「角色已指定 + 已记录」，但是否最终关闭
  仍看其 acceptance 判据；`verified` 仍受 EXC-02 门控。

## #3 数据矩阵责任人 owner（AUD-016-04）—— 决策 C：自动化 agent 作 caretaker

- 指定：数据/证据矩阵的 accountable owner 由**自动化 caretaker agent** 担任，非人类。
- 职责边界（须先定义，如下）：
  - **负责**：矩阵文件完整性巡检、缺失字段告警、变更留痕、定时快照。
  - **不负责**：裁定断言可否关闭、替代人类问责、修改治理 JSON 的语义。
  - **越权防护**：caretaker 仅读 / 报告；任何「关闭断言」动作必须经由 #6 的签署
    流程，不得自行翻状态。
- 落地：`scripts/matrix_caretaker.py`（只读巡检三份治理 JSON，结构不变量违反→
  退出 2 硬失败；与上次快照漂移→告警，默认退出 0、可 `--strict` 退出 3）。
  该脚本**不写入治理 JSON**，仅写自身状态文件 `.caretaker_state.json`（已 gitignore）。
- 诚实声明：AI caretaker 提供「有角色在看」的覆盖，但不替代人类对数据责任的
  问责；对外合规时须升级为独立人类 owner。

## #4 真实环境资源（AUD-004/009/010/012 · EXC-02）—— 决策 B：沿用 EXC-02 延期

- 决策：暂不提供真实环境资源，沿用已登记的**例外 EXC-02**（到期 2027-04-30），
  继续以模拟环境推进。
- 影响：AUD-004/009/010/012 在 EXC-02 有效期内视为「例外豁免」，非「已满足」；
  `verified` 维持 0，直到真实环境资源就位并验证。
- 无需新建 EXC（EXC-02 已存在于 `exception_register.json`，且日期与基线一致）；
  本文件仅记录「沿用」立场。

## #5 独立账号/主机（解锁 EXC-02 → verified）—— 决策 B：本地隔离近似

- 决策：以**本地隔离**（独立容器 / VM / 沙箱）作为「独立」的近似实现，
  用于 EXC-02 到期后 / 期间的 verified 验证。
- 诚实声明：本地隔离 ≠ 真实独立账号 / 主机（不同信任域）。它能在 solo 阶段提供
  「执行环境与开发环境分离」的近似证据，但**不**等同于独立人类账号 / 独立云租户；
  对外正式审计仍须真实独立设施。`verified` 的最终翻转需在该隔离环境实际跑通
  验证脚本。
- 与 #4 关系：本地隔离是 EXC-02 到期后「如何验证」的手段之一；当前 EXC-02 仍
  有效，故 `verified` 仍 0。

## #6 签署后断言状态更新流程（manual → closed）—— 决策 B：review-agent 自动翻

- 决策：signoff 经合法流程记录后，由 **review-agent**（即 `reviewer_designation.md`
  指定的独立评审 Agent）自动将对应断言翻为 closed。
- 防自批守卫（全部满足才允许自动翻）：
  1. 仅当存在**有效 signoff 记录**（`signoffs.jsonl` 中该断言有合法签署，
     且签署人 ≠ 作者）时才允许翻；
  2. 自动翻执行者 = review-agent（≠ authoring agent），且 review-agent 不得是
     本次变更的 author；
  3. 翻状态动作写入审计日志（谁、何时、基于哪条 signoff）；
  4. 任何「作者自批」信号（签署人 == 作者）一律拒绝（AGT-001 / GOV-17）。
- 落地：`scripts/apply_signoffs.py` 已包含 self-sign / role / evidence 守卫；
  本轮新增 **#6 review-agent 绑定**（opt-in，环境变量 `GOV_REVIEW_AGENT`）：
  设置后 `--by` 必须等于该 review-agent 且不等于 `GOV_AUTHOR_IDENTITY`，否则
  原子中止（reason：`executor_not_review_agent` / `review_agent_is_author`）；
  翻转写入的 `signoff` 字段新增 `review_agent` / `flipped_at` 审计项。
- 诚实声明：自动翻只是「执行已批准的结论」，不替代评审判断；评审判断仍由
  review-agent 在评审流程中做出、Owner 最终拍板。本决策定义流程，不关闭断言。

## 变更记录

- 2026-11-01：Owner 就 #2~#6 逐一拍板（A / C / B / B / B），记录于本文件。
  关联 AUD-015-04、AUD-016-04、AUD-004/009/010/012（EXC-02）、AGT-001、GOV-17。
  不关闭任何断言；`verified` 仍 0；EXC-02 维持到期 2027-04-30。
- 2026-11-01 续（#2→B）：Owner 将 #2 由「A：Owner 兼任」修订为
  「B：独立 AI agent 作 Security-Owner 代理（家族独立于作者模型）」，诚实边界
  更新为「AI 代理不替代人类职责分离合规要求」；并同步在 #3 / #6 注明对应落地脚本
  与守卫。不关闭任何断言；`verified` 仍 0；EXC-02 维持到期 2027-04-30。
