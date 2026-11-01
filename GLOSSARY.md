# GLOSSARY.md — 共享词汇表（ubiquitous language）

> **用途**：人机对话、文档、提交信息、评审意见中的术语必须与本表一致；新术语**先入表再使用**（实践改写自 mattpocock/skills 的 GLOSSARY，未复制原文）。
> **权威链**：本表位于 AGENTS.md 之下、工作日志之上；与规范原文/门禁冲突时以后者为准。

## 1. 证据与状态（铁律①的词汇基础）

| 术语 | 定义 |
|---|---|
| 断言 assertion | `acceptance_matrix.json` 中可判定的最小验收单元（当前 22 issues / 90 条） |
| kind=test | 映射到仓库真实用例；用例不存在即不满足 |
| kind=script | 执行仓库校验脚本，退出 0 才算满足 |
| kind=evidence | 证据文件必须存在且含指定字符串 |
| kind=manual | 机器无法判定，须独立签署；未签署即 pending |
| kind=excepted | 受已登记例外约束；**仍计入未满足**，仍阻断关闭声明 |
| tested | 控制有真实用例/脚本覆盖并通过 |
| verified | 在 verified 级信任域（独立账号/主机）实际验证；**当前 0，受 EXC-02 门控** |
| closed | 断言经合法签署获得 `signoff` 字段；只能由 签署→apply 流程产生 |
| **铁律①** | tested ≠ verified ≠ closed：三个不同证据等级，任何混用都是虚假声称 |

## 2. 例外

| 术语 | 定义 |
|---|---|
| EXC-01 | 第二人类主体 / 独立 Reviewer 不可达（单人开发者），到期 2027-01-31 |
| EXC-02 | 独立账号与主机不可达，到期 2027-04-30；Owner 已确认不提供真环境（owner_designations #4 续二） |
| 例外语义 | "把洞标记出来"，不是"把洞填平"：excepted 仍阻断 machine_complete 与关闭声明 |

## 3. 门禁与检查

| 术语 | 定义 |
|---|---|
| required_checks | `quality_baseline.json` 中 15 项必需检查；`gov_run` 执行并记账 |
| T-QA-02 | 测试下限：acceptance cases ≥ floor 303 |
| T-QA-04 | 基线完整性：治理范围须与基线同批提交（漂移即红）+ 单调性（下调须 `change_approvals`） |
| T-REF-01 | 治理 JSON 结构化字段引用可解析 |
| T-REF-02（严格模式） | 代码引用的规则/控制编号必须为注册表规范拼写；无前缀归一化，拼写分歧即悬空 |
| GATE-01 | 准入判定：成熟度 G1/G2；风险 R0–R3，R2/R3 需 G2 |
| fail-closed 失败关闭 | 任一门禁不符即非零退出；不得弱化参数让其变绿 |
| 悬空引用 | 引用的编号在注册表/目录中不存在（fail-closed 拦截） |
| 规范命名形式 | `GOV-*`（无 AASEGS 前缀）、`AASEGS-AGT-*`、`AASEGS-SUP-*`（有前缀）；以注册表为准 |

## 4. 签署与闭环

| 术语 | 定义 |
|---|---|
| signoff | 独立复核签署记录，append-only 于 `governance/signoffs.jsonl`（当前 0 条） |
| 独立角色 | independent-reviewer / owner / security-owner（`record_signoff` 强制集合） |
| 防自签 | 签署人 ≠ `GOV_ACTING_IDENTITY`（默认 `slow-is-fast`）；apply 侧双重拦截 |
| dry-run / apply | 先投影 diff 给 Owner，确认后 `--apply --by <执行者>` 改写矩阵；任一条目非法 → **整批原子中止** |
| 翻转 flip | manual → closed 的动作；#6 自动翻绑定：设 `GOV_REVIEW_AGENT` 后 `--by` 必须=它且 ≠ `GOV_AUTHOR_IDENTITY` |
| verdict | approved / needs-work / rejected；**approved ≠ 关闭** |

## 5. 角色

| 术语 | 定义 |
|---|---|
| authoring agent | 执行开发的 Agent（`GOV_ACTING_IDENTITY`） |
| review-agent | 独立模型家族的评审 Agent（`reviewer_designation.md`） |
| security-owner 代理 | 独立 AI 代理（owner_designations #2 B）；不替代人类职责分离合规 |
| caretaker | `scripts/matrix_caretaker.py`：只读巡检；不裁定、不写治理 JSON |
| Owner | 人类；拍板决策点、以独立主体签署、确认 apply |

## 6. 治理数据文件

| 文件 | 定义 |
|---|---|
| rule-registry.json | 59 条规则（GOV×19 + AASEGS×40），仓库根 |
| control-catalog.yaml | 控制目录（内容实为 JSON，仅扩展名 .yaml），仓库根 |
| acceptance_matrix.json | 22 issues / 90 断言 |
| control_coverage.json | 8 条 disposition（audit_driven / defense_in_depth），每条须有 owner |
| evidence_ledger.json | 证据台账（46 项）；改动/消失触发 `gov_run --verify` 红 |
| quality_baseline.json | 受保护下限基线：15 required_checks、floor 303、EXC-01/02 |
| change_approvals | 基线下调（阈值/必需检查/例外扩大）的强制审批记录 |

## 7. caretaker 专属

| 术语 | 定义 |
|---|---|
| 结构不变量 | 断言 id 唯一且 kind 合法；disposition 有 owner 且类型合规；evidence 有 sha256 |
| 指纹 fingerprint | 三份矩阵结构的哈希；用于跨运行漂移比对 |
| 漂移 drift | 与上次快照指纹不一致；默认告警 exit 0，`--strict` / `CARETAKER_STRICT=1` → exit 3 |
| 退出码 | 0 健康 / 2 结构违反（硬失败）/ 3 strict 模式漂移 |

## 8. 工作流

| 术语 | 定义 |
|---|---|
| 基线绿才动刀 | 变异/重构前 `gov_run --all` 必须全绿 |
| 变异检验 | 对守卫注入变异验证检查器真能抓；基线红时"被捕获/逃逸"全是噪音 |
| 同一把尺子 | CI 与验收用 `git diff --exit-code` 口径（CRLF 下 `git status` 假阳性） |
| 双向核对 | 改后 grep：该在的在、不该多的没有（`grep -c` 计数） |
| append-only 日志 | `.workbuddy/memory/当日.md` 只追加不覆写 |
