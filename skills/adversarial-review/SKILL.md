---
name: adversarial-review
description: 对抗性评审循环——把 review-agent 从纸面指定变成可执行流程：多角度攻击 diff，verdict 经 record_signoff 落账。
invocation: user
source: 概念改写自 pstack /interrogate（未复制原文）；verdict 落账对接本项目 record_signoff / apply_signoffs
constitutional-check: 对照 AGENTS.md §1 已审查（2026-11-01）；铁律④由步骤 6 硬性落实，铁律①②⑥由前置与产出节落实。
---

# /adversarial-review —— 对抗性评审

## 何时用
- 任何将被"声称已验证 / 已关闭"的改动：manual 断言闭合前、P0 修补后、安全相关控制变更后；
- Owner 或 AGENTS.md §6 要求独立评审时。

## 前置（任一不满足即终止并报告，不得"降级继续"）
1. 被审 diff / 提交范围明确；
2. **机器门禁全绿**（`gov_run --all`）——红基线上不存在"评审通过"这回事（铁律②⑥）；
3. 评审主体 ≠ 作者：以 review-agent 身份评审，且 `GOV_REVIEW_AGENT` ≠ `GOV_AUTHOR_IDENTITY`、≠ `GOV_ACTING_IDENTITY`（铁律④）。

## 评审循环（每个角度一轮，产出 findings[severity, 位置, 理由, 反例]）
- **正确性**：这段逻辑在什么输入下会错？给出可构造的反例。
- **安全**：越权 / 注入 / 信息泄露 / 信任域混淆——对照 executor 既有威胁模型。
- **治理合规**：改动是否触碰 `governance/*.json`、`scripts/`、门禁参数？若触碰，是否与基线同批提交、是否需要 `change_approvals`？
- **测试覆盖**：哪个分支没有测试？删除哪行代码不会被现有用例发现？
- **证据审查**：本次改动声称的结论需要什么证据？证据文件是否真的存在且包含该内容（防占位文件顶替）？

## 产出与落账
1. findings 报告：按 severity 排序，每条附复现/反例路径；
2. verdict：approved | needs-work | rejected + basis（≥10 字，说明看了什么、为何给此结论）；
3. **verdict ≠ 关闭**（铁律①）：approved 仅代表评审通过；断言关闭必须走 `record_signoff` → `apply_signoffs`（Owner 确认）；
4. verdict 由评审主体经 `record_signoff.py` 落账（role=independent-reviewer）；**作者身份不得代跑签署**。

## 宪法约束
- 评审不得修改门禁参数"让结果好看"（铁律②）；
- findings 允许推翻自己先前的判断——评审职责是找真问题，不是批准。
