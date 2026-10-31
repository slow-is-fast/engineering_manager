# 独立复核签署模板（sign-off scaffold 使用指南）

本文件是给人看的。机器侧落证用 `scripts/record_signoff.py`，落证存储为
`governance/signoffs.jsonl`（append-only）。本脚手架服务于 EXC-01：把
"谁 / 何时 / 基于什么证据 / 以什么独立角色 / 给什么结论"结构化记录，
让 manual 断言的关闭有可追溯的独立复核证据。

## 前置：声明执行主体身份（防自签）

工具会拒绝"签署人 == 执行主体"。运行前设置环境变量指向跑测试 / Agent 的
那一方身份，例如：

```bash
export GOV_ACTING_IDENTITY=slow-is-fast   # 或本次 Agent 的具体标识
```

这样当你（人类复核者）用自己的身份签署时，不会被误判为自签；但若有人试图
用同一个执行主体身份签署，工具直接拒绝。

## 签署命令（复制改成你的信息）

```bash
GOV_ACTING_IDENTITY=slow-is-fast python scripts/record_signoff.py \
  --assertion-id AUD-015-04 \
  --reviewer <你的 GitHub 账号或实名> \
  --role security-owner \
  --verdict approved \
  --evidence evidence/response_handbook.md,evidence/drill_2026xx.md \
  --basis "已审阅响应手册与四类隔离演练记录（凭证泄露/越权写入/审计中断/数据暴露），每类场景均有对应 T-INC 用例覆盖，结论可信。"
```

## 字段说明

| 字段 | 含义 | 约束 |
|------|------|------|
| `--assertion-id` | 对应 `acceptance_matrix.json` 里的 manual 断言 ID | 必填 |
| `--reviewer` | 签署人真实身份 | 必填；不得等于 `GOV_ACTING_IDENTITY` |
| `--role` | 独立角色 | 仅 `independent-reviewer` / `owner` / `security-owner` |
| `--verdict` | 结论 | `approved` / `rejected` / `needs-work` |
| `--evidence` | 证据路径，逗号分隔 | 至少一条；会算哈希留痕 |
| `--basis` | 人类可读说明 | 至少 10 字，说明看了什么、为何给此结论 |

## 重要边界（诚实）

- 本工具**只记录**，不关闭任何断言。签署后，`acceptance_matrix.json` 里对应
  断言的状态更新、以及最终的 CLOSED/ACCEPTED_RISK 声明，仍须由 Owner 按治理
  流程单独处理——签署是证据，不是关闭动作本身。
- 未签署前，断言继续标记为 `manual`，不被冒称已满足。
- 任何"用执行主体身份签署以通过"的尝试都会被工具拒绝（技术不可行）。
