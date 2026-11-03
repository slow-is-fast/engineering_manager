# AASEGS 治理包 · Owner 行动清单（Agent 侧收口后的交接）

> **⚠️ 2026-11-03 Owner 决定：人工签署链已冻结（本文件下方各节的行动建议暂停执行）**
>
> - **继续跑**：19 项机器门禁（本地 `--all` / CI）原样保留。它们抓的全是真问题
>   （幽灵用例、字段错位、指纹换行、分类错、证据未登记），且 Owner 成本为零——
>   这是"防倒退"，不是负担。
> - **停止生产**：剩余 8 条"仅需文档与判断"断言的复核材料、选项③正式评审。
>   原因：材料链的规格（生成脚本 + 指纹 + 变异检验）是为"给独立主体复核"服务的，
>   而单人环境里那个独立主体不存在——**没有读者的高规格就是纯成本**。
> - **冻结期间**：`verified` 停在 1/22。这不是退化，是承认现状：剩下的验证
>   需要的资源（第二人类主体 / 真环境）本来就不在（EXC-01/02/03 已登记）。
> - **解冻条件**（任一出现即解冻）：① 真有第二个人要看这套东西；② 治理包要
>   对外交付 / 展示。解冻时从 `governance/review_handoff.md` + 同源报告
>   `evidence/agent_review_20261102.md` 起步，材料规格按当时的读者重新定。
>
> 本冻结决定本身不产生门禁（不再加戏）；下面第 1～7 节保留作为"解冻后的路线图"，
> 其中的数字是写作时点的，读的时候以实际为准。

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

### Tier 2 — 需真实环境资源（9 条，成本较高）
与 `owner_worklist.md` 第二节对齐（此前这里只列了 4 条，是过期版本）：

| 行动 | 对应断言 | 所需资源 |
|------|----------|----------|
| 隔离环境集成测试 + 资源端拒绝证据 | AUD-004-05 | 隔离环境（容器/VM） |
| Claude Code / Codex 实际配置验证记录 | AUD-005-03 | Claude Code / Codex 真机配置 |
| 记忆状态机与检索/缓存集成测试 | AUD-006-05 | 记忆后端（检索/缓存） |
| 真实代表性副作用端到端 + 远端结果证据 | AUD-009-04 | 真实副作用系统 + 远端结果证据 |
| 恢复演练 + 检查点与决策可追溯关联 | AUD-010-04 | 可制造故障并恢复的环境 |
| 隔离环境演练记录 | AUD-011-04 | 隔离环境 |
| 真实试点仓库配置独立检查（分支保护 + SHA 绑定） | AUD-012-03 | 真实试点仓库 |
| 审批与仓库门禁集成测试 | AUD-018-03 | 真实仓库（分支保护 + 审批门禁） |
| 受控真实仓库证据包 + 独立 Reviewer/Owner 签署 | AUD-021-03 | 受控真实仓库 + 独立签署人 |

### 解锁 EXC-02（让 Tier 2 的"verified"级证据成立）
| 行动 | 效果 |
|------|------|
| 获取独立账号/主机（或组织级 App 身份） | EXC-02 撤销条件满足 → 受其 waive 的 30 条控制的 `verified` 可授予 |

> **注意 EXC-02 的边界**：它的 `waives.requirement` 只有 `["verified"]`，`waives.controls` 是
> 那 30 条控制。**它不 waive 上面这 9 条 `manual` 断言**——那些是"需要真环境的一次性人工验证"，
> 不是"某条控制的 verified 档位"。所以 EXC-02 对 Tier 2 只是**背景约束**，不是豁免凭证；
> 这 9 条目前没有终止条件，见 §7。

## 4. 复核人操作速查（Owner 把角色派下去后用）

```bash
# 0) 防自签前置：执行主体写成 Agent，**不是**你自己
#    默认值就是 slow-is-fast（= Owner）。若你本人要当 reviewer，必须先把它改成别的名字，
#    否则 record_signoff 会以「禁止自签」拒绝——这不是 bug，是防代签的设计。
export GOV_ACTING_IDENTITY=agent-runner

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
4. **真实环境资源**：Tier 2 的 9 条（清单见 §3）需隔离环境/真实远端/真实试点仓库——何时提供？不提供的话，请直接给 §7 的路径 1 开绿灯。
5. **独立账号/主机（EXC-02）**：是否计划引入？不引入则 Tier 2 的 verified 级证据始终不可达。
6. **签署后断言状态更新流程**：真实签署落入 `signoffs.jsonl` 后，由谁、按什么流程把 `acceptance_matrix.json` 里对应断言从 `manual` 改为 `closed`？（脚手架只落证，不自动改断言状态——需 Owner 流程。）

## 6. 诚实边界
- 本清单**不关闭任何问题/断言**，只把"Agent 已完成"与"Owner 该做什么"分开列清。
- 在 `signoffs.jsonl` 出现对应 `assertion_id` 的 `approved` 签署、且 Owner 按流程更新断言状态之前，GATE-01 仍为 G1、10 个 P0 仍阻断、21 条 manual 仍 `manual`、1 条 excepted 仍计入未满足（合计 22 条待办，见 `owner_worklist.md`）。
- 以上所有结论均可由 `acceptance_matrix.json` / `exception_register.json` / `maturity_matrix.json` 复核，未做机器判定替代。

## 7. 9 条「需要真环境」断言的定性方案（三选一，需 Owner 拍板）

### 7.1 现状：它们没有终止条件

- 这 9 条都是 `kind=manual`，**不是** `excepted`；
- `EXC-02` 不 waive 它们——它的 `waives.requirement` 只有 `["verified"]`，管的是那 30 条控制的
  verified 档位，不是「需要真环境做一次人工验证」这件事；
- 于是它们会一直 `pending`：没人能签（无环境）、也没有任何机制提醒该处理（例外才有到期日）。

**换句话说，这 9 条现在处于「永远不会被处理、也不会被提醒」的状态。这才是要修的东西**，
不是「想办法把它们签掉」。

### 7.2 三条路径

| 路径 | 做法 | 记录形态 | 代价 | `verified` 会变 true 吗 |
|---|---|---|---|---|
| **1. 延期（推荐）** | 新增 `EXC-03` 覆盖 9 条，`expires=2027-04-30`（与 EXC-02 对齐）；矩阵 9 条 `kind: manual → excepted` + `exception_ref: EXC-03` | 例外登记 + 矩阵改档 + 基线 `change_approvals` | 写 3 个文件、1 次审批记录 | **不会**。仍计入未满足、仍阻止 `machine_complete` |
| 2. 补环境 | 逐条按 §3 Tier 2 的资源清单真跑一遍，产出证据 | 9 份 evidence + 9 次签署 | 需要隔离环境/远端系统/试点仓库/独立签署人 | **会**（唯一路径） |
| 3. 永久 excepted | 不设到期日地标为 excepted | —— | **机制上不可表达**：`T-EXP-01` 要求例外必须有 `expires`（"带到期日但无人比较的例外 ≡ 永久例外"，所以索性不允许没有到期日） | 不会 |

路径 3 的变通做法（把 `expires` 拉到 5 年后）只是把决定推后，本质仍是路径 1，且更不诚实。

### 7.3 为什么推荐路径 1

1. **它把"永久挂着"变成"有计划地挂着"**：有到期日（`T-EXP-01` 会在剩余 ≤90 天时告警）、
   有补偿控制（现状：CI 18/18 + 三重 pin + 凭证分域 + 每次运行落审计流）、有撤销条件（任一真环境到位）。
2. **它不假装完成**：`excepted` 的语义原文是"仍然计入未满足、仍然让该问题无法 machine_complete、
   仍然阻止声明已关闭——例外是'把洞标记出来'，不是'把洞填平'"。所以这条路不会制造假绿。
3. **它成本最低且可逆**：环境一旦到位，撤销例外、按路径 2 补验证即可。

### 7.4 你拍板后我做什么

1. 写 `EXC-03` 进 `exception_register.json`（含 `scope` / `waives` / `compensating_controls` /
   `revocation` / `evidence_uri`）；
2. 矩阵 9 条 `kind → excepted`、`exception_ref → EXC-03`；
3. 基线 `change_approvals` 追加一条（**原文记录你的批准理由**，因为 `T-QA-04` 的单调性检查
   要求"扩大例外必须带审批"）；
4. 重生成 `owner_worklist.md` 与 `coverage_pack_aud001.md`，跑 `--all` 应回到 `17/18`；
5. 提交 + 等 CI。

需要你给的只有一句话：**「EXC-03 批准，理由：……」**。理由我照抄进 `change_approvals`，
不代写——那是这份记录里唯一属于你的部分。

### 7.5 我不能做的

- 不能把这 9 条签成 `approved`：没有环境就是没有验证，签了是伪造验证；
- 不能把它们标成 `closed`：`closed` 的前提是 `verified`，而 `verified` 的前提是真实环境。

（第 3 类那 1 条 `AUD-013-03` 已由 `EXC-01` 覆盖且已 `excepted`，不在本节范围。）
