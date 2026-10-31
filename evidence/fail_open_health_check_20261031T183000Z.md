# §10.31 发现 8：三项高风险检查的"放行路径"体检

**日期**：2026-10-31T18:30+08:00
**关联**：整体复核报告 §8 第 3 点（"发现 8：检查存在 ≠ 检查在每种情形下都会拦"）；
T-GATE-01（补 2 条守卫）、T-CLM-01（补 2 条守卫）、GOV-12~21（补 2 条守卫）；
累计变异 **59 → 74 处 / 0 逃逸**

## 动机

"检查存在"和"检查在每种情形下都会拦"是两件事。凭证域（发现 7）就是典型：
它存在，但在非 CI 下对"能写控制面"只打 INFO 假绿。本轮对其余三项高风险检查
做同样的"放行路径"变异体检——注入会让检查漏判的改动，确认每次都被现有或新补
的守卫用例抓住。

## 做法（铁律照旧）

基线先确认绿 → 注入变异（内存备份 + try/finally 还原 + CRLF 规范化匹配）→ 跑对应
测试模块 → 跑完重跑全套件确认绿且 `git status` 干净。逃逸的先补守卫用例再重测。

## 结果

| 检查 | 变异点 | 注入 | 捕获 | 关键守卫 |
|---|---|---:|---:|---|
| **GATE-01**（`executor/gate.py` + `check_admission_gate.py`） | 例外非人类批准人被放过 | 1 | 捕获 | T-GATE-01_invalid_exceptions |
| | 过期例外被放过 | 1 | 捕获 | T-GATE-01_invalid_exceptions |
| | `unwaivable` 守卫反转（GATE-01 自身可被豁免） | 1 | 捕获 | T-GATE-01_gate_control_unwaivable |
| | `_check_control` 未 tested 判定反转 | 1 | 捕获 | T-GATE-01_untested_p0 + 新增 reports_highest |
| | `evaluate` 的 `break` 被删（等级虚高） | 1 | 捕获 | **新增** T-GATE-01_reports_highest_satisfied_level |
| | CLI 等级比较 `got<want` 反转 | 1 | 捕获 | **新增** T-CLI_require_level_below_returns_1 |
| | CLI 风险比较 `decision!=ALLOW` 反转 | 1 | 捕获 | **新增** T-CLI_require_level_below_returns_1 |
| **CLM-01**（`scripts/check_claims.py`） | 豁免守卫恒为真（所有行放行） | 1 | 捕获 | T-CLM-01_unbacked |
| | 删掉绝对词匹配（ABSOLUTE_RE） | 1 | 捕获 | **新增** T-CLM-01_pure_absolute |
| | 100%撤销语境规则恒 False | 1 | 捕获 | **新增** T-CLM-01_pct_in_revocation_ctx |
| | 证据豁免恒为真（backed 永远放行） | 1 | 捕获 | T-CLM-01_pure_absolute + unbacked |
| **GOV（证据验收）**（`scripts/gov_run.py` `verify_evidence`） | 未登记证据跳过 | 1 | 捕获 | T-GOV-14_unregistered |
| | 哈希不符检查反转 | 1 | 捕获 | T-GOV-12/13 |
| | 墓碑内容可读检查被关 | 1 | 捕获 | **新增** T-GOV-21_leaky_tombstone |
| | 证据过期扫描跳过 | 1 | 捕获 | **新增** T-GOV-20_stale_evidence |

**合计 15 处变异，0 逃逸。**

## 体检暴露的两个真实守卫缺口（已补）

1. **GATE-01 报告等级虚高**：`evaluate()` 的 `break` 被删后，未达标仓库会虚报 G4，
   而 CI 的 `--require-level` 读的就是 `asmt['level']`——虚高会直接放行。原用例只
   断言 `decision==DENY`，不断言"等级是最高**已满足**等级"。**新增
   `test_t_gate_01_reports_highest_satisfied_level`** 钉死。
2. **CLI `check_admission_gate.py` 零单元测试**：等级/风险比较返回码从无用例覆盖，
   是 GATE-01 唯一未被钉死的放行路径。**新增 `test_cli_require_level_below_returns_1`**
   （用 `mock.patch.object` 替换 `AdmissionGate`，隔离测 CLI 比较逻辑）。
3. **GOV 证据过期只靠 RVF-01 兜底**：`gov_run --verify` 里的 `sweep_retention` 调用
   无用例断言。**新增 `test_gov_20_stale_evidence_fails_verify`**。
4. **GOV 墓碑内容可读检查无守卫**：现有 GOV-15/16/17 只验台账/磁盘层不一致，不验
   "DataGate 墓碑是否还带内容"这一深层泄漏。**新增 `test_gov_21_leaky_tombstone`**
   （monkeypatch 一个会泄漏的闸门，确认检查本身标红——独立于 DataGate 正确性）。
5. **CLM-01 组合文档掩盖单规则放行**：原 `test_unbacked_absolute_claim_rejected`
   同时含绝对词+`100%`+`撤销`，删掉绝对词匹配仍会被 `100%撤销` 规则顺带抓到，掩盖漏洞。
   **新增 `test_pure_absolute_claim_rejected`（`万无一失`，无`撤销`/`100%`语境）与
   `test_pct_in_revocation_context_rejected`（`撤销` `100%`，无其它`绝对词`）**做隔离。

## 方法教训（本轮新踩）

- **组合 fixture 会掩盖单规则放行**：一个文档同时触发多条规则时，关掉其中一条
  仍被其它规则抓到，变异看似"逃逸"实为没测到点。**隔离 fixture 是变异检验的
  前提**——每条规则一个最小触发文档。
- **归因筛选要用"套件是否变红"，不要按方法名子串过滤**：初版 CLM 报告把
  `test_pct_in_revocation_context_rejected`（方法名不含 "claim"）误判为逃逸，
  实为捕获。判据应简化为 `returncode != 0`。

## 结论

三项高风险检查经体检确认**失败关闭**成立：每条"放行路径"变异都被钉死。本轮
净增 6 条守卫（gate 2 / claims 2 / gov 2），累计变异 59 → 74 处 / 0 逃逸。
用例下限 263 → 269（AST 实际值，删除余量 0）。
