# 独立 Reviewer 指定（reviewer_designation）

- 状态：已指定（Owner 拍板，2026-11-01）
- 关联审计问题：AUD-001 / AUD-002 / AUD-014 / AUD-020（独立评审）
- 关联规则：AGT-001、GOV-17（作者不得自批）；EXC 例外流程
- 背景：本包采用「单人 + 多 Agent」开发模式，当前仅有 Owner（Andy）一人开发。

## 1. 指定内容

| 项 | 指定 |
|---|---|
| Reviewer 角色 | `review-agent`（独立 Agent，非 authoring agent） |
| 指定评审模型（默认推荐） | **Claude Opus/Sonnet（reasoning 模式）**；Owner 须确认 WorkBuddy 中实际可用模型 |
| 作者模型（对照） | `hy3` / Hunyuan 家族 |
| 独立性判据 | 评审模型家族 **≠** 作者模型家族（不同训练 → 不同盲区，构成实质独立） |

> ⚠️ 模型为占位推荐：Owner 须在 WorkBuddy 中确认实际可用模型并填入本节；
> **唯一硬约束**是评审模型与作者模型不同家族。若作者改用其他家族模型写作，
> 评审模型须相应切换，始终保持「不同家族」这一独立性前提。

## 2. 评审范围与流程

- **触发**：每次代码/文档变更经 `git diff` 送检（含本治理包的脚本与文档变更）。
- **评审 Agent 职责**：读 diff + 相关上下文，输出 `must-fix` / `should-fix` 清单
  （逻辑 / 边界 / 安全 / 并发 / 门禁影响）；**不得 auto-approve**。
- **最终拍板**：Owner（Andy）对评审结论做最终确认；签署经
  `record_signoff` / `apply_signoffs --by <Owner>` 记录，评审 Agent 署名于签署流程。
- **自批防护**：`contract.py` / `apply_signoffs.py` 已含「作者不能自批」守卫
  （AGT-001 / GOV-17）；评审 Agent 与 authoring Agent 为不同实例，从机制上规避自批。

## 3. 范围与例外边界（诚实声明）

- 本指定以 **AI review-agent 替代人类独立评审**，适用于本包当前 solo 开发阶段。
- **不替代人类问责**：若本包进入对外正式合规审计（SOC2 / ISO 27001 等）且审计
  判据要求「人的职责分离」，则本 AI reviewer **不**满足该判据。此时须：
  1. 走例外登记（EXC），在 `exception_register.json` 记录「AI reviewer 替代」
     及到期 / 升级条件；或
  2. 待有第二位人类开发者后，将 Reviewer 升级为独立人类并修订本文件。
- 本文件**不关闭任何断言、不翻转 `verified`**；真实环境验证仍受 EXC-02 门控。

## 4. 与审计问题的关系

- 本指定**提供** AUD-001 / AUD-002 / AUD-014 / AUD-020 所需的「独立 Reviewer 身份」
  控制（从缺失 → 已指定 + 已记录）。
- 上述审计问题是否**最终关闭**，取决于各自 acceptance 判据（通常还要求评审流程
  实际运行并对变更署名）。指定是前提，不是闭环；后续每次变更走 §2 流程即逐步满足。
- Owner 可拉取 `audit_policy.json` / `acceptance_matrix.json` 中对应条目的判据逐条核对。

## 5. 变更记录

- 2026-11-01：Owner（Andy）指定 `review-agent`（默认 Claude 推理模型，家族独立于
  hy3/Hunyuan）为本包独立 Reviewer；文档化于本文件 `governance/reviewer_designation.md`。
  此指定使阻塞点 #1 的「Reviewer 身份」从空白推进到「已指定 + 已记录」。
