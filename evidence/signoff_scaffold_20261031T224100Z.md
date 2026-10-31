# 签署证据脚手架（EXC-01 落地机制）

- 日期：2026-10-31
- 关联：整体复核报告 §7 待决策项「21 条 manual 断言（EXC-01）」
- 交付：`scripts/record_signoff.py` + `tests/test_signoff.py`（5 条）+ `governance/signoffs.jsonl`（空存储）+ `evidence/signoff_template.md`（人用指南）
- 变异体检结果：**防自签约束 1 处 fail-open 变异，0 逃逸**

## 背景

`governance/acceptance_matrix.json` 有 90 条验收断言：满足 63、人工 21、显式未实现 6。
21 条 manual 断言（如 `AUD-015-04 响应手册经 Security Owner 批准`、`AUD-021-03
受控真实仓库证据包 + 独立 Reviewer/Owner 签署`）本质分两类——独立复核/批准类
与真实环境/集成类——都靠 EXC-01 编码的"独立主体/资源不可达"门控，Agent 无法
替 Owner 关闭。它们不是"待办工作量"，是不能由单方判定满足的硬约束。

但"无法自动关闭"不等于"无法让真实复核可追溯"。此前缺一个把独立复核
结构化落证的机制，导致即便有第二人类主体复核，证据也散落、不可机器核验。
本脚手架补这个缺口。

## 做了什么

- `scripts/record_signoff.py`：把一条签署 append 到 `governance/signoffs.jsonl`，
  记录 assertion_id / reviewer / role / reviewed_at / evidence_refs（含哈希）/
  verdict / basis / signature。
- **硬约束（失败关闭）**：
  1. 签署人身份 == `GOV_ACTING_IDENTITY`（执行主体）→ 拒（防自签，EXC-01 核心）；
  2. role 不在 `{independent-reviewer, owner, security-owner}` → 拒；
  3. 缺 evidence_ref → 拒；
  4. basis 少于 10 字 → 拒。
- `tests/test_signoff.py`（5 条）：`test_valid_signoff_recorded` +
  `test_self_sign_rejected` / `test_invalid_role_rejected` /
  `test_missing_evidence_rejected` / `test_short_basis_rejected`。
- `governance/signoffs.jsonl`：空存储，等待真实独立复核写入。
- `evidence/signoff_template.md`：人用指南（含防自签前置、命令、字段、边界）。

## 变异体检（防自签约束）

对 `scripts/record_signoff.py` 注入 1 处 fail-open 变异：把自签拒绝比对
`if reviewer == acting:` 改为 `if False:`，运行 `tests.test_signoff`。
目标守卫 `test_self_sign_rejected`（reviewer 设为执行主体）在变异后**失败**
→ 变异被抓住（守卫抵抗住 fail-open）。`ESCAPED: []`。注入与还原用
内存备份 + `try/finally` 还原，`git diff` 干净后删除 harness。

## 诚实边界（关键）

- 本脚手架**不关闭任何一条 manual 断言**。它只让"真实独立复核"有可追溯、
  机器可核验的落证。21 条断言在 `acceptance_matrix.json` 中仍标记为 manual，
  直至有真实第二主体按此机制签署、并由 Owner 按治理流程更新断言状态。
- 我（Agent）**未替任何人签署**，也未在存储里写入任何条目（当前为空）。
- 自签在工具层被技术拒绝；任何"用执行主体身份签署以通过"的尝试都会失败。
- 显式未实现 6 条（需真实远端/隔离环境/真实保留周期）仍不在此脚手架范围内，
  它们需要真实环境资源，非机制缺失。
