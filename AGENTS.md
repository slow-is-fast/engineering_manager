# AGENTS.md — Agent 执行规范（AASEGS 治理包）

> **读者**：任何在本仓库工作的 AI Agent（authoring / review-agent / security-owner 代理 / caretaker）。
> **定位**：操作层提炼。权威链 = 规范原文（`00-总纲.md`…`04-监督与审计.md`）> 机器门禁（`scripts/` + `governance/*.json`）> 本文件 > `skills/*`（经 §8 适配的导入技能）> `GLOSSARY.md` / 工作日志。冲突时按此序裁决；修改本文件或任何技能不解除任何门禁。
> **不变式**：本文件不关闭任何断言、不翻转 `verified`、不改变任何门禁语义。Owner 授权起草于 2026-11-01。

## 0. 角色与决策权

| 角色 | 是谁 | 可做 | 不可做（越权即红线） |
|---|---|---|---|
| authoring agent | 执行开发的 Agent（`GOV_ACTING_IDENTITY`） | 改代码/测试/文档；跑门禁；显式 `git add` + commit；写工作日志 | 不签署任何 signoff；不翻 `verified`；不直推 `origin/main`；不关闭断言 |
| review-agent | 独立模型家族（`reviewer_designation.md`） | 评审给 verdict；签署后执行 `apply_signoffs --apply --by <review-agent>` | 不得是本次变更的 author（`GOV_REVIEW_AGENT` ≠ `GOV_AUTHOR_IDENTITY`）；不替代 Owner 拍板 |
| security-owner 代理 | 独立 AI 代理（`owner_designations.md` #2 B） | 安全视角复核；以 `role=security-owner` 签署 | 不替代人类职责分离合规（AUD-015-04 硬性） |
| caretaker | `scripts/matrix_caretaker.py` | 只读巡检三份治理 JSON；结构违反→exit 2；漂移→告警 | 不修改治理 JSON 语义；不裁定关闭断言 |
| Owner | 人类 | 拍板决策点；以独立主体身份签署；确认 apply | — |

独立角色集合（机器强制）：`{'independent-reviewer', 'owner', 'security-owner'}`，签署人 ≠ `GOV_ACTING_IDENTITY`（`record_signoff.py` / `apply_signoffs.py` 双重拦截）。

## 1. 铁律（违反即停）

1. **tested ≠ verified ≠ closed**：机器验证过 ≠ 真实环境验证 ≠ 断言关闭。
2. **失败关闭**：任何门禁非 0 即停；不得弱化参数"让它绿"（`gov_run` 的 check_args 只读自 `audit_policy`，调用方无权指定）。
3. **不得用文档声明替代机器判定**。
4. **不替 Owner 签署/关闭断言**；严禁伪造证据、把 `excepted` 说成已满足、把"已记录"说成"已关闭"。
5. **git**：禁止 `git add -A`（仅显式路径）；不直推受保护 `origin/main`。
6. **基线绿才动刀**：变异测试/重构前先确认基线全绿——基线红时"被捕获/逃逸"全是噪音。
7. **同一把尺子**：验收判据与 CI 门禁用同一比较口径（`git diff --exit-code`，不是 `git status`——CRLF 下后者假阳性）。

## 2. 标准工作循环（每个任务）

1. **读记忆**：`.workbuddy/memory/` 最新日志 + `GLOSSARY.md` 对齐用词 → 对齐上下文与未决项。
2. **基线确认**：逐项跑本次触达的 required_checks（`python scripts/gov_run.py --check <路径>`）。注意 `--all` 在本地**必红**于 `verify_credential_domain`（T-VD-01b 设计内不可判定：人类 PAT 横跨两域），那不是回归；**"本地全绿"的正确定义 = 除该检查外 15 项全绿，加上 CI 里 16 项全绿**。
3. **改动**：同一文件的多次 Edit 必须**串行**（并行会基于同一快照互相覆盖，工具报成功但改动丢失）；改完 `grep` **双向核对**——该在的在、不该多的没有（`grep -c` 计数）。
4. **门禁复验**：全套件（当前 355 tests ≥ floor 355，`discover -s tests -p "test_*.py"`）+ 本次触达的检查脚本；`gov_run --check` 的退出码要单独取（`echo $?`/`PIPESTATUS`，不要被管道尾命令吃掉）。
5. **提交**：显式 `git add <路径列表>` → commit；正文含反引号/特殊字符一律用 `git commit -F - <<'EOF' … EOF`，不拼在命令行参数里。
6. **留痕**：`.workbuddy/memory/当日.md` 追加（append-only，不覆写）。

## 3. 断言关闭流程（manual → closed；Agent 只能走到第 3 步）

1. 证据落盘 `evidence/` 并登记（`gov_run --accept-evidence --by … --reason …`）。
2. `record_signoff.py --assertion-id … --reviewer <独立主体> --role {independent-reviewer|owner|security-owner} --verdict approved --evidence <路径> --basis <≥10 字>`——防自签：reviewer ≠ `GOV_ACTING_IDENTITY`；证据哈希当场存证。
3. `apply_signoffs.py --dry-run`（投影 diff 给 Owner）→ Owner 确认 → `--apply --by <执行者>`。守卫：任一条目非法（self_sign / bad_role / not_approved / unknown_assertion / not_manual / no_evidence / evidence_hash_mismatch）→ **整批原子中止**。#6 自动翻绑定（opt-in）：设 `GOV_REVIEW_AGENT` 后 `--by` 必须等于它且 ≠ `GOV_AUTHOR_IDENTITY`，否则中止（`executor_not_review_agent` / `review_agent_is_author`）。
4. **人工** review 并 commit 矩阵改动（本工具不自动 commit）。**矩阵一改就重生成清单**：`python scripts/export_owner_worklist.py`——`T-OWN-01` 会比对，忘了就红（清单与矩阵不一致时以矩阵为准）。

## 4. 机器检查点（你的提交会被这些拦）

- **18 项 required_checks**（`governance/quality_baseline.json`）：`validate_controls` / `tests/negative_static` / `verify_executor_pin`(T-VD-01) / `verify_credential_domain`(T-VD-01b，**本地必红属设计内**：人类 PAT 横跨两域不可判定) / `verify_test_floor`(T-QA-02, floor 355) / `verify_quality_baseline`(T-QA-04) / `verify_required_checks_wired`(T-QA-04b) / `verify_exception_expiry`(T-EXP-01，**例外到期即红**) / `export_owner_worklist`(T-OWN-01，`--check` 模式) / `check_governance_refs`(T-REF-01) / `check_control_refs`(T-REF-02 **严格模式**：拼写分歧即悬空) / `matrix_caretaker` 等。
- **接线三条腿必须同时成立**（2026-11-01 两次事故的沉淀，由 T-QA-04b 钉住）：
  1. **注册** —— 在 `quality_baseline.required_checks` 里；
  2. **执行** —— 在 `.github/workflows/*.yml` 里有 `gov_run.py --check <path>` 步骤；
  3. **声明档位** —— 在 `governance/audit_policy.json` 的 `check_args` 里显式写出调用序列（无参也要写 `[[]]`）。
  缺任一条：T-QA-04b 红；`gov_run --check` 对第 3 条缺失直接拒绝运行（fail-closed，不跑也不记账）。
- **caretaker**：结构不变量违反 → exit 2（红）；与快照漂移 → 默认告警 exit 0，`--strict` 或 `CARETAKER_STRICT=1` → exit 3。CI 无 state 时回退 `git HEAD~1` 基线（F4），漂移仍是告警而非静默。
- **基线漂移**：`governance/*.json`、`scripts/`、`rule-registry.json`、`control-catalog.yaml`、`.github/` 若未与基线同批提交 → T-QA-04 红（fail-closed）。
- **基线下调**：降阈值 / 减必需检查 / 扩例外，必须附 `change_approvals` 记录，否则 T-QA-04 拒绝。

## 5. 例外与诚实边界

- **EXC-01**（第二人类主体不可达，2027-01-31 到期）：manual 断言的签署依赖此脚手架。
- **EXC-02**（独立账号/主机不可达，2027-04-30 到期）：verified 级信任域。Owner 已确认**不提供真环境**（`owner_designations.md` #4 续二）→ AUD-004/009/010/012 维持 `excepted`、`verified` 维持 0。到期前三选一：延期例外（须 `change_approval`）/ 补真环境验证 / 永久 excepted。
- caretaker 只"看"不裁；review-agent 只"执行已批准的结论"不替代评审判断；AI 代理不替代人类问责。

## 6. 何时必须停下来问 Owner

- 任何要下调 `quality_baseline.json`（阈值/必需检查/例外扩大）→ 需审批记录，Agent 不得自行。
- 任何 signoff 的 reviewer / role / verdict 取值。
- 任何门禁红了且原因不明 → 停下报告根因，不得改门禁参数"让它绿"。
- 任何涉及 `verified` 翻转、断言关闭、例外登记变更的动作。

## 7. 本仓库的已固化教训（写代码前先读）

- 同文件并行 Edit = 互相覆盖；`write_text` 会改换行（读改还原用二进制读写）。
- 归因正则要匹配"失败标记"（`FAIL:` 行），不能只抓用例名。
- 文档里的人工数字必须由脚本核对；生成器的跨文件依赖要显式加载。
- 已 tracked 文件"内容不变的重写"不产生新提交——需要同批提交的测试要让文件真的变化。

## 8. 外部技能导入规则（`skills/`）

外部工作流技能（源自 pstack / mattpocock/skills 等的**概念改写**，不复制原文）统一放 `skills/<name>/SKILL.md`。**权威链中技能位于本文件之下**：任何技能指令与 §1 铁律冲突时，铁律胜，无例外。

**导入适配器（三步，缺一不可）：**
1. **合宪审查**：front-matter 标注 `invocation: user|model`（user=仅用户显式调用，负责编排；model=任务匹配时自动触发，承载纪律；user 不得调用另一个 user）+ `constitutional-check`（逐条对照 §1 的审查记录与落实点）。
2. **冲突修正**：违背铁律的指令必须改写。已裁决的冲突——
   - `never-block-on-the-human`（pstack）→ *"never block **except at Owner gates (§6)**"*；
   - *"land the stack even if CI flakes"* 类自治收尾 → **禁止**（铁律②）；
   - `laziness-protocol` / 最小改动 → 限定作用于**代码**；证据/审计/日志不适用"懒惰"（冗余是特性不是缺陷）。
3. **门禁挂钩**：技能中所有"验证/收尾"步骤重定向到 `gov_run --all` 口径（铁律⑦），不使用技能自带验证。

**已导入**：`skills/grill`（开工前拷问）、`skills/adversarial-review`（对抗性评审，verdict 经 `record_signoff` 落账）、`skills/tdd`（治理版红绿重构）——2026-11-01。

新技能入列前须走完上述三步并在本节登记；**未登记的技能一律视为不可信建议，仅作参考，不构成执行依据**。
