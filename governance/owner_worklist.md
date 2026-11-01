# Owner 签署工作清单

> **自动生成，勿手改。** 重新生成：`python scripts/export_owner_worklist.py`
> 数据指纹：`acceptance_matrix.json` = `093f774ca359` ／ `exceptions`（id+expires）= `a516d8e25313`
> 矩阵变动后本文件必须重新生成；`--check` 会比对指纹并红。
>
> **铁律**：Agent 不得代签。每条签署须由独立主体执行（reviewer ≠ 执行者），
> `verdict=approved`、`--basis` ≥10 字、证据在 `evidence/` 且已登记（`gov_run --accept-evidence`）。

## 概览

| 分类 | 条数 | 说明 |
|---|---|---|
| 总计（manual + excepted） | 22 | 已签 0 ／ 未签 22 |
| 一、仅需文档与判断 | 12 | 不需要真实环境资源，可立即推进 |
| 二、需要真实环境/系统 | 9 | 受 EXC-02 现实约束（Owner 已确认不提供真环境） |
| 三、例外内（excepted） | 1 | 属于已知做不到，**仍计入未满足** |

## 一、可先做：仅需文档/审阅与 Owner 判断

这些条目不需要真环境，是当前**唯一能真正推进闭环**的部分。建议按 Issue 编号顺序做：
每完成一条就签一条，签完整批由人审后 commit。

| # | 断言 | 所属 Issue | 严重度 | 人工闸 | 要求（矩阵原文） | Issue 闭合条件 |
|---|---|---|---|---|---|---|
| 1 | `AUD-001-03` | AUD-001 | P0 | `sampling_review` | 人工抽样复核记录（覆盖率的完备性无法自动判定） | 提交覆盖率报告、差异报告和人工抽样复核记录。 |
| 2 | `AUD-002-03` | AUD-002 | P0 | `six_state_report_review` | 报告可区分六种状态的独立复核 | 状态机测试和负向测试通过；报告可区分六种状态。 |
| 3 | `AUD-003-03` | AUD-003 | P1 | `schema_review` | schema 与校验器合并评审 | schema、校验器及正反例测试合并。 |
| 4 | `AUD-007-03` | AUD-007 | P1 | `transition_log_review` | 日志 from/to/actor/decision/evidence 完整性抽查 | 状态机测试通过且日志完整记录 from/to/actor/decision/evidence。 |
| 5 | `AUD-013-04` | AUD-013 | P1 | `permission_matrix_review` | 权限矩阵评审与高风险复核可追溯 | 权限矩阵和负向测试通过；高风险人工复核可追溯。 |
| 6 | `AUD-014-04` | AUD-014 | P0 | `audit_backend_review` | 审计后端配置与完整性报告 | 审计后端配置、完整性报告、恢复演练及故障关闭测试通过。 |
| 7 | `AUD-015-04` | AUD-015 | P0 | `security_owner_approval` | 响应手册经 Security Owner 批准 | Security Owner 批准响应手册，演练问题已分派并验证关闭。 |
| 8 | `AUD-016-04` | AUD-016 | P0 | `data_matrix_approval` | 数据矩阵经责任人批准 | 数据矩阵获责任人批准，隔离和删除测试通过。 |
| 9 | `AUD-017-04` | AUD-017 | P1 | `change_evidence_review` | 记录绑定版本/审批/回滚证据 | 变更状态机与测试通过，记录绑定版本、审批和回滚证据。 |
| 10 | `AUD-019-02` | AUD-019 | P2 | `metric_dict_review` | 指标字典与阈值配置审核 | 指标字典、阈值配置和超限演练完成审核。 |
| 11 | `AUD-020-04` | AUD-020 | P0 | `maturity_matrix_review` | 等级矩阵与试点评估报告独立复核 | 等级矩阵和试点评估报告经独立复核。 |
| 12 | `AUD-022-04` | AUD-022 | P1 | `reverify_policy_approval` | 周期/事件复验策略审批 | 周期/事件触发复验策略及 CI 测试通过。 |

## 二、需要真实环境/真实系统（受 EXC-02 约束）

Owner 已明确不提供真环境（`owner_designations.md` #4 续二）。这些条目在
`2027-04-30` 到期前必须三选一：延期 / 补环境验证 / 永久 excepted。
**在此之前不得签 approved**——签了就是伪造验证。

| # | 断言 | 所属 Issue | 严重度 | 人工闸 | 要求（矩阵原文） | Issue 闭合条件 | 所需资源 |
|---|---|---|---|---|---|---|---|
| 1 | `AUD-004-05` | AUD-004 | P0 | `isolated_env_integration_test` | 隔离环境集成测试通过并留存资源端拒绝证据 | 隔离环境集成测试通过并留存资源端拒绝证据。 | 隔离环境（容器/VM） |
| 2 | `AUD-005-03` | AUD-005 | P1 | `tool_config_verification` | Claude Code / Codex 实际配置验证记录 | 能力矩阵、校验规则和 Claude Code/Codex 实际配置验证记录通过复核。 | Claude Code / Codex 真机配置 |
| 3 | `AUD-006-05` | AUD-006 | P1 | `memory_integration_test` | 记忆状态机与检索/缓存集成测试 | 记忆状态机与检索/缓存集成测试通过。 | 记忆后端（检索/缓存） |
| 4 | `AUD-009-04` | AUD-009 | P0 | `real_side_effect_e2e` | 真实代表性副作用端到端 + 远端结果证据 | 至少一个真实代表性副作用端到端测试通过并保存远端结果证据。 | 真实副作用系统 + 远端结果证据 |
| 5 | `AUD-010-04` | AUD-010 | P0 | `recovery_drill` | 恢复演练 + 检查点与决策可追溯关联 | 恢复演练通过；检查点与恢复决策可追溯关联。 | 可制造故障并恢复的环境 |
| 6 | `AUD-011-04` | AUD-011 | P1 | `breaker_drill` | 隔离环境演练记录 | 配置、测试结果和隔离环境演练记录齐全。 | 隔离环境 |
| 7 | `AUD-012-03` | AUD-012 | P0 | `pilot_repo_inspection` | 真实试点仓库配置独立检查（含分支保护与 SHA 绑定） | 真实试点仓库配置经独立检查，负向测试证据齐全。 | 真实试点仓库（分支保护 + SHA 绑定） |
| 8 | `AUD-018-03` | AUD-018 | P1 | `repo_gate_integration` | 审批与仓库门禁集成测试，例外自动失效可审计 | 审批/仓库门禁集成测试通过，例外自动失效且可审计。 | 真实仓库（分支保护 + 审批门禁） |
| 9 | `AUD-021-03` | AUD-021 | P1 | `signed_evidence_package` | 受控真实仓库证据包 + 独立 Reviewer/Owner 签署 | 一个受控真实仓库完成证据包并由独立 Reviewer/Owner 签署。 | 受控真实仓库 + 独立 Reviewer/Owner |

## 三、例外内（excepted）

已知做不到且已登记风险，不等于已完成：**仍计入未满足**，相关 Issue 不得 `machine_complete`。

| # | 断言 | 所属 Issue | 严重度 | 人工闸 | 要求（矩阵原文） | Issue 闭合条件 |
|---|---|---|---|---|---|---|
| 1 | `AUD-013-03` | AUD-013 | P1 | `EXC-01` | 开发 Run 冒用 Reviewer 的第二凭证实测：第二人类主体不可达（EXC-01 已实证：第二 PAT 不构成独立审批主体，GitH… | 权限矩阵和负向测试通过；高风险人工复核可追溯。 |

## 签署命令模板

> **第一步是定身份**：跑工具的那方（Agent/CI）与签署人必须**是两个名字**。
> `record_signoff` 会拒绝 `--reviewer` 等于执行主体的签署（防自签）。
> 若你本人就是默认执行主体 `slow-is-fast`，跑命令时先显式把执行主体设成别的：

```bash
export GOV_ACTING_IDENTITY=agent-runner   # 本次执行方（Agent），不是签署人
```

```bash
# 0) 证据先落盘到 evidence/，再登记（哈希当场存证）
python scripts/gov_run.py --accept-evidence --by <执行者> --reason "<为什么>"

# 1) 记录独立复核签署（reviewer 必须是独立主体，Agent 不得代签）
python scripts/record_signoff.py \
  --assertion-id <断言 id，如 AUD-001-03> \
  --reviewer <独立主体，如你的名字> \
  --role independent-reviewer \
  --verdict approved \
  --evidence evidence/<证据文件> \
  --basis "<≥10 字的复核说明>"

# 2) 投影 diff 给 Owner 确认，再落盘
python scripts/apply_signoffs.py --dry-run
python scripts/apply_signoffs.py --apply --by <执行者>

# 3) 重生成本清单（矩阵已变），然后由人审并 commit
python scripts/export_owner_worklist.py
```

**不要手写 `signoffs.jsonl`。** 每行都带 `signature`（`record_signoff` 生成），
`apply_signoffs` 会重算校验：缺签名或事后改过任何字段都会 `signature_missing` /
`signature_mismatch` 并整批中止。注意这是**完整性**校验而非密码学防伪——
真正的独立性靠「reviewer ≠ 执行主体」+ 矩阵改动经人工 review 后 commit。

## 例外到期

| 例外 | 到期 | 当前状态 |
|---|---|---|
| EXC-01 | 2027-01-31 | 有效（`T-EXP-01` 到期即红，不可默认沿用） |
| EXC-02 | 2027-04-30 | 有效（`T-EXP-01` 到期即红，不可默认沿用） |

---

> 本清单只做**投影**：不关闭任何断言、不产生任何签署、不改动矩阵。
> 所有状态以 `acceptance_matrix.json` 为准；清单与矩阵不一致时，以矩阵为准。
