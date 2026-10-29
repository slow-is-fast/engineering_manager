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

## v1.1.1 实施完整性修订（2026-10-29）

v1.1 规范文本仍为 **1.1.0**；以下产物已升至 **1.1.1**：

- `AASEGS_v1.1.1_实施完整性修订版.md`：v1.1 原文（逐行保留）+ 12 章补充条款 + §13 负向测试用例补遗。
- `control-catalog.yaml`：44 条控制（原 20 条 + v1.1.1 新增 23 条 + 秘密凭证 CRED-01）。新增条目带 `risk_level`、`source_ref`、`addresses`（应答的审计问题）与六态 `state`。
- `rule-registry.json`：52 条强制规则注册表（v1.0 继承的 GOV-01～08 + 按域编号的存量条款），每条含来源位置、原文、风险、控制引用与状态。
- `AASEGS_v1.1_审计问题清单.json`：每项新增 `covered_by` 反向映射与 `coverage_summary`，`status` 仍为 `OPEN`。

**当前覆盖情况**：审计问题 22 项全部有控制定义应答；具备运行时证据 0 项；已关闭 0 项。规范文本已到 v1.1.1，治理证据仍为零，不得据此宣称运行时合规。

**校验**：

```bash
python scripts/validate_controls.py   # 字段、六态、风险等级、审计映射、用例唯一性、内联 MUST 注册
python tests/test_controls.py         # 6 个结构测试
python tests/negative_static.py       # T-REG-01/02、T-AUD-01 负向实跑
```

以上三项已接入 `.github/workflows/governance.yml`（check 名 `governance / static-gate`），对规范、注册表、控制目录的任何改动都会在 PR 上自动校验。分支保护与 CODEOWNERS 配置见 `governance/GATE_SETUP.md`。静态负向用例的运行证据存于 `evidence/`。

44 条控制与 44 个负向用例一一对应，无复用、无孤儿；52 条规则中 46 条有控制支撑，6 条已标注 gap。`state.verified` 为 true 时必须存在 `integration_evidence_uri`，否则校验失败。
