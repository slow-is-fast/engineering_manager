# AASEGS 治理包 · Owner 行动清单（Agent 侧收口后的交接）

> 本文件是前三份交付的综合与收口，给 Owner（Andy）一份可照做的分层行动表。
> 前置交付：
> - `governance/manual_signoff_checklist.md`（21 条 manual 断言，断言中心，照表填）
> - `governance/g2_blocker_closure_plan.md`（10 个 P0 问题，问题中心，要什么资源）
> - `scripts/record_signoff.py` + `governance/signoffs.jsonl`（落证脚手架，当前 0 条目）
> - `evidence/signoff_template.md`（人用签署指南）

## 1. Agent 侧已完成（无需 Owner 再投入）

| 项 | 状态 | 证据 |
|---|------|------|
| 放行路径变异体检 | 13 项必需检查全收口，累计 **80 变异 0 逃逸** | `evidence/fail_open_*.md` 系列 + CI success |
| 测试下限 / CLM-01 / 基线漂移 | 281≥269、52 docs 无绝对词、T-QA-04 绿 | 每次提交前复跑 |
| EXC-01 签署脚手架 | `record_signoff.py` 防自签硬约束 + 5 守卫 + 变异 0 逃逸 | `evidence/signoff_scaffold_20261031T224100Z.md` |
| 21 条 manual 签署清单 | 断言中心矩阵（角色/证据/ basis / Checklist） | `manual_signoff_checklist.md` |
| G2 阻断关闭证据矩阵 | 问题中心矩阵（10 P0 = 各 1 manual） | `g2_blocker_closure_plan.md` |
| 两处自身误述已更正 | 到期日无不一致；`unimplemented` 实为 0 | 上两轮提交 |

## 2. 当前诚实状态

- `governance/signoffs.jsonl`：**0 条目**——没有任何真实签署落到存储，Agent 未代签任何一项。
- 21 条 manual 断言：在 `acceptance_matrix.json` 中仍标记 `manual`（未关闭、未 verified）。
- 成熟度 GATE-01：仍 **G1**，G2 阻断仍为 **10**（= 上表 10 个 P0 问题各自的 manual 断言）。
- EXC-01 到期 **2027-01-31**；EXC-02 到期 **2027-04-30**。两份文件现已一致。

## 3. 分层行动清单（按"成本/可否立即"排序）

### Tier 1 — 纯人力签署，不依赖稀缺真实环境（建议最先做）
| 行动 | 对应断言 | 所需角色 | 资源需求 |
|------|----------|----------|----------|
| 指派独立 Reviewer 做覆盖率抽样复核 | AUD-001-03 | independent-reviewer | 抽样记录（可由现有脚本产出覆盖率/差异报告） |
| 指派独立 Reviewer 读六种状态报告 | AUD-002-03 | independent-reviewer | 报告样本已存在 |
| 指派独立 Reviewer 复核试点评估报告 | AUD-020-04 | independent-reviewer | 试点评估报告已存在 |
| 数据矩阵责任人批准 | AUD-016-04 | owner | 责任人身份 |
| Security Owner 角色建制 + 批准响应手册 | AUD-015-04 | security-owner | **需先存在 Security Owner 角色**（组织建制缺口） |
| 审计后端配置与完整性报告复核 | AUD-014-04 | independent-reviewer | 需审计后端**已实际部署运行**（验证其在线） |

> Tier 1 共 6 个 P0 问题（AUD-001/002/014/015/016/020）。AUD-015 的卡点是"角色尚未建制"——
> 这不是签署动作，是组织角色配置，应先解决。

### Tier 2 — 需真实环境资源（受 EXC-02 约束，成本较高）
| 行动 | 对应断言 | 所需资源 |
|------|----------|----------|
| 隔离环境集成测试 + 资源端拒绝回执 | AUD-004-05 | 真实隔离环境 + 外部资源端真实拒绝回执 |
| 真实代表性副作用端到端 + 远端回执 | AUD-009-04 | 真实远端系统 + 端到端执行 + 远端结果回执 |
| 真实恢复演练 | AUD-010-04 | 真实恢复演练执行（可本地但须真实跑） |
| 真实试点仓库独立检查 | AUD-012-03 | 受控真实试点仓库 + 独立检查人 |

### 解锁 EXC-02（让 Tier 2 的"verified"级证据成立）
| 行动 | 效果 |
|------|------|
| 获取独立账号/主机（或组织级 App 身份） | EXC-02 撤销条件满足 → verified 可授予 → Tier 2 断言不再仅 manual_pending |

## 4. 复核人操作速查（Owner 把角色派下去后用）

```bash
# 0) 防自签前置：声明执行主体身份（Agent 侧），复核人必须不同
export GOV_ACTING_IDENTITY=slow-is-fast

# 1) 复核人准备证据文件（放 evidence/manual/，内容按 manual_signoff_checklist.md 对应小节填）
#    例如 AUD-001-03：evidence/manual/AUD-001-03.md 写抽样方法/比例/结论
#    注意：evidence/ 下新增文件须登记：`python scripts/gov_run.py --accept-evidence --by <你> --reason "新增 AUD-001-03 复核证据"`

# 2) 落证（工具会拒绝自签/非法角色/缺证据/短说明）
python scripts/record_signoff.py \
  --assertion-id AUD-001-03 \
  --reviewer "<复核人实名>" \
  --role independent-reviewer \
  --verdict approved \
  --evidence evidence/manual/AUD-001-03.md \
  --basis "抽样覆盖 X 条控制，比例 Y%，未发现遗漏，覆盖率/差异报告与矩阵一致"
```

- 工具硬约束：签署人 `== GOV_ACTING_IDENTITY` → 拒；`role` 不在三集合 → 拒；缺证据 → 拒；`basis<10` 字 → 拒。
- 每条断言的"证据该写什么 / Checklist"见 `manual_signoff_checklist.md` §2；"要什么资源"见 `g2_blocker_closure_plan.md` §2。

## 5. 需要 Owner 提供 / 拍板的事项（阻塞点）

1. **独立 Reviewer 身份**：Tier 1 的 AUD-001/002/014/020 需要一位 ≠ `GOV_ACTING_IDENTITY` 的真实人类/独立账号。谁？
2. **Security Owner 角色建制**：AUD-015-04 硬性要求该角色批准；当前组织可能未配置。
3. **数据矩阵责任人（owner）**：AUD-016-04 由谁以责任人身份批准？
4. **真实环境资源**：Tier 2 的 AUD-004/009/010/012 需隔离环境/真实远端/真实试点仓库——何时提供？
5. **独立账号/主机（EXC-02）**：是否计划引入？不引入则 Tier 2 的 verified 级证据始终不可达。
6. **签署后断言状态更新流程**：真实签署落入 `signoffs.jsonl` 后，由谁、按什么流程把 `acceptance_matrix.json` 里对应断言从 `manual` 改为 `closed`？（脚手架只落证，不自动改断言状态——需 Owner 流程。）

## 6. 诚实边界
- 本清单**不关闭任何问题/断言**，只把"Agent 已完成"与"Owner 该做什么"分开列清。
- 在 `signoffs.jsonl` 出现对应 `assertion_id` 的 `approved` 签署、且 Owner 按流程更新断言状态之前，GATE-01 仍为 G1、10 个 P0 仍阻断、21 条 manual 仍 `manual`。
- 以上所有结论均可由 `acceptance_matrix.json` / `exception_register.json` / `maturity_matrix.json` 复核，未做机器判定替代。
