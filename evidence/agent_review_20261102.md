# 同源对抗评审（agent-review，非选项③）

> **效力声明**：本报告由与作者同模型家族的 Agent 产出，上下文独立但模型同源。
> 它**不构成** `skills/adversarial-review` 前置③要求的「新会话、不同家族」正式评审，
> 不得作为 `role=independent-reviewer` 的签署依据。它能覆盖的是机械性问题
> （数字过期、文档与代码不一致、命令跑不通、断言不成立）；模型家族的共同盲区
> 它看不见——如果本报告全绿，那恰恰是同源评审无效的证据，不是好消息。

**评审时点状态**：HEAD = `1465b4a`（docs(status): 看板刷新到 3f14712…），
`git status` 干净。评审对象仓库 `D:\code\engineering_manager`。
本评审未修改任何仓库内受版本控制的文件；对原仓库的写动作仅限
`gov_run --all` / `matrix_caretaker` 按设计产生的 gitignored 运行产物
（`evidence/audit/trail.jsonl`、`.caretaker_state.json`——后者在验证中被移走后
由 `--all` 运行重新生成）。F4/F5 的破坏性实验全部在 `/tmp` 下的克隆里完成。

---

## 一、结论摘要

1. **交接包多处数字已过期**（范围 21→33 提交、356→387 用例、363→394 下限、17/18 与 18 步→19 项检查），且 §2「evidence/ 未新增证据文件」已与事实不符——照 §3 判定口径字面执行会误判，但底层结论（本地唯一红 = T-VD-01b、CI 全绿）未翻转。
2. F1–F7 全部按交接包给的方法独立复验通过；§5 六处中**第 2 条（check_args 可被静默降级为生成模式）确实仍然敞着**，已构造出具体回归路径；第 6 条（`--all` 口径）经查代码**已有对策，作者多虑了**。
3. §8 四条自曝失误在仓库中均无残留。

---

## 二、F1–F7 逐条验证（命令 → 输出 → 判断）

### F1（vendor 与 pin 一致性）— PASS

```
$ python scripts/verify_executor_pin.py
PASS(T-VD-01): executor pin verified: slow-is-fast/aasegs-gov-plane@28ef6b1e3651 tree=bf330225876f content=b337b3bfa70e
PASS(T-VD-01): 本地 vendor 副本一致（29 个文件，换行已规范化为 LF）   # exit 0
```

`governance/executor_pin.json` 的 `content_hash_sha256` = `b337b3bfa70ef2b02680bb…`，
与脚本对本地 `executor/` 重算的 `content=b337b3bfa70e…` 一致。判断：**已闭环**。

### F2（基线红导致评审终止，流程性）— 已消解（以可验证的最大程度）

T-VD-01 的 pin bump 发生在 `5113c85`（`git log -- governance/executor_pin.json` 首条
命中：`5113c85 fix(governance): bump executor pin to upstream 7c8a086 after PR#1 comment-alignment sync`），
早于 `fe72107^`。在克隆中 `git checkout fe72107^` 后跑 `verify_executor_pin.py` →
PASS（pin 指向 7c8a086，29 文件一致，exit 0）。即评审范围起点处基线已绿。
「当时首跑抓到红」的历史过程无法逐字节复现（需要当时的工作区），此判断止步于此。

### F3（--state 可覆写治理文件）— PASS

```
$ md5sum governance/quality_baseline.json      # 先备份到 /tmp
244087bf22787cacaac81715dcea5d80
$ python scripts/matrix_caretaker.py --state governance/quality_baseline.json
OK(caretaker): 三份矩阵结构不变量通过
FAIL(caretaker): --state 不允许指向受保护目录内: governance\quality_baseline.json
# exit 2；再次 md5sum 同值；git status 干净
```

判断：**已修**。拒绝发生在写之前（`matrix_caretaker.py:64-77` `_ensure_state_path_safe`），文件未被触碰。

### F4（CI 漂移失聪 / git 回退）— PASS（附一处验证方法陷阱，见 §六-L1）

先在原仓库用 `--no-state` 跑：只输出结构不变量 OK，**没有任何漂移检查**——
因为 `matrix_caretaker.py:230-231` 在 `--no-state` 分支直接 `sys.exit(0)`，
漂移逻辑在其后。改为正确测法（克隆到 /tmp/em_rev，删 state、把
`governance/acceptance_matrix.json` 回退到 `fe72107^` 版本、**不带 --no-state**）：

```
$ python scripts/matrix_caretaker.py
OK(caretaker): 三份矩阵结构不变量通过
DRIFT(caretaker): 检测到与上次快照的结构指纹变化（告警，不修改治理文件）：
  - 指纹: 414d46dae31d... -> bbbede4839a2...（基线来源: git:HEAD~1）
  上次计数: issues=22 assertions=90 evidence=47
# exit 0（非 strict，告警级，符合 docstring 约定）
```

判断：**已修**。git 回退真实生效；`--strict` 时退出 3 由单测覆盖
（`tests/test_matrix_caretaker.py:111` `test_drift_detected_strict_is_three`）。

### F5（kind 翻转不触发告警）— PASS

在 /tmp/em_rev 克隆中把一条断言 `kind: manual → excepted`，删 state 后跑：

```
DRIFT(caretaker): 检测到与上次快照的结构指纹变化（告警，不修改治理文件）：
  - 指纹: 414d46dae31d... -> 868e27af08cb...（基线来源: git:HEAD~1）
# exit 0
```

id 集合未变、仅 kind 翻转，指纹仍变。单测 `test_kind_change_is_drift`
（tests/test_matrix_caretaker.py:151）同样断言 DRIFT。判断：**已修**。

### F6（无用例的分支）— PASS

`grep -n "def test_" tests/test_matrix_caretaker.py` 列出 16 条，其中 F6 补测可辨认：
`test_invalid_kind_fails` / `test_audit_driven_disposition_missing_issue_fails` /
`test_defense_in_depth_disposition_missing_derived_from_fails`（110-148 行）。
读了断言体：它们不仅断言 `returncode == 2`，还断言**失败原因文本**
（`assertIn('非法 kind', r.stdout)`、`assertIn('缺 issue', …)`、`assertIn('缺 derived_from', …)`）。
`test_git_history_baseline_detects_drift`（188 行起）在真实 git 临时仓库里验证
`git:HEAD~1` 回退 + 二跑固化。判断：**已修，且断言质量合格**。

### F7（env 身份咨询性信任）— 不复报

§6 已登记为已知限制（EXC-02 信任域）。本评审不持不同意见，也不重复报。

---

## 三、§5 六处攻击结果

| # | 判定 | 判据 |
|---|---|---|
| 1. T-QA-04b 不看 `if:` | **敞着（潜伏）** | `verify_required_checks_wired.py` 全文无任何对 `if:` 的解析（grep 无命中）。当前缓解：`.github/workflows/governance.yml` 中 **0 个 `if:` 条件**（`grep -n "if:"` 无命中），且触发含 `push: branches:[main]` + `pull_request`——即"静态算接线、条件步骤漏网"的缺陷当前没有实例。但 nothing 阻止未来某步加上 `if:` 而校验照常绿。与作者自述一致：证明的是"步骤文本存在"。 |
| 2. `check_args` 声明对了没 | **仍然敞着（本次评审最能复现的一条）** | 见下方详细攻击。 |
| 3. F4 依赖 `HEAD~1` | **已收窄** | 真浅克隆（`git clone --depth=1 file:///…`，1 个提交）实测：`BASELINE(caretaker): 无可用基线…已写基线`，exit 0——降级为放行，与自述一致。但 **CI 侧已缓解**：`governance.yml:39-41` `actions/checkout` 显式 `fetch-depth: 0`。另外"同一提交既改矩阵又改 state"这个担忧实际不成立：state 文件被 gitignore（.gitignore 有 `.caretaker_state.json`），永远不会进提交；提交里改了矩阵，`HEAD~1` 对比就能抓到。 |
| 4. `signature` 非密码学 | 不复报 | §6 已登记（`signature` 非密码学，见 §5 第 4 条）。 |
| 5. e2e tmpdir、不覆盖并发 | **敞着（与自述一致）** | `tests/test_owner_chain_e2e.py` 头注释自述"全程在临时目录、用合成主体"，用 `tempfile` 构造；无任何并发/追加语义用例。风险按作者披露原样存在。 |
| 6. `--all` 失败也记 completed | **已失效（作者多虑）** | `gov_run.py:361-366`：验收统计"必需检查落地"时明确过滤 `verdict == 'ok'`（`landed = {… if e.get('event_type')=='gov.check.completed' … and e.get('verdict')=='ok'}`），失败项不会算作落地；审计事件本身带 `verdict='failed'` + `exit_code` 字段，可区分。未发现"失败被算作已完成"的口径问题。 |

### §5.2 详细攻击（check_args）

现状：`governance/audit_policy.json` 的 `check_args` 共 19 键，其中
`scripts/export_owner_worklist.py => [['--check']]`。fail-closed 的实际代码
（`gov_run.py:186-199`）只挡两种情况：

- 键缺失 → 拒绝（提示语甚至示范了 `[[]]` 是合法写法）；
- 值不是非空列表的列表 → 拒绝。

**`[[]]` 本身完全合法**。而 `export_owner_worklist.py:266-285` 里 `--check` 是
可选开关：不带它就是生成模式（改写 `governance/owner_worklist.md`、exit 0）。
接线校验 D 段（`verify_required_checks_wired.py:108-127`）只核对：声明存在、
形状合法、`check_args` 与 `required_checks` 键集合相等——**从不看参数值**。
`grep -rn "export_owner_worklist" tests/*.py` 亦无任何用例钉住 `['--check']`
这个值（`tests/test_gov_run.py:456` 的 `setdefault(c, [[]])` 恰恰说明 `[[]]`
被测试基建当作普通合法值）。

结论：把 `[["--check"]]` 改成 `[[]]` 后，`--all` 照样全绿、每轮改写投影文件、
T-OWN-01 名存实亡，**没有任何机器门禁会红**。与作者自述完全一致，风险敞口未收窄。
（修法建议留给作者：在接线校验里对"生成/校验双模式"脚本钉住参数值，或让
`export_owner_worklist.py` 在检测到写入模式被门禁调用时拒绝。）

---

## 四、交接包自身数字核对

| 交接包写的 | 实际（命令与输出） | 影响 |
|---|---|---|
| §2：范围 21 个提交，终点 `6206abf` | `git log --oneline fe72107^..HEAD \| wc -l` → **33**；HEAD=`1465b4a` | **H**。"范围只增不减"声明覆盖了新增提交，但 §2 表格未列出这 12 个提交（`f4fff10`…`1465b4a`）的内容，评审者无从知道它们改了什么（实际包括 EXC-03 登记、第一条真实签署 `fe15276`、T-REF-03 门禁、六态报告等**有实质内容**的提交）。 |
| §3：本地 `--all` 汇总行必须是 `17/18` | `python scripts/gov_run.py --all` → exit 1，汇总行 **`检查未全部通过：1/19 项未通过`**（18 ok，唯一 FAILED = `scripts/verify_credential_domain.py`） | **H**。判定口径过期。§9 已自纠 required_checks 18→19，但 §3/§4 未同步——文件自相矛盾。照 §3 字面执行（"必须是 17/18"）会把本轮正常结果误判为异常。 |
| §3：CI 18 个 `--check` 步骤全 pass | `required_checks` len=**19**（quality_baseline.json）；workflow 中 `gov_run.py --check` 唯一目标 **19** 个；`gh run view 41395041366` 最新 run（HEAD=1465b4a）conclusion=**success**，19 个检查步骤全 success | 数字过期，结论方向未变（CI 确实全绿）。 |
| §4：`--all` → `17/18` | 同上，**1/19 未通过** | 同 §3 条目。 |
| §4：356 tests | `python -m unittest discover -s tests -p "test_*.py"` → **Ran 387 tests … OK** | 数字过期。全绿结论未变。 |
| §4：`verify_test_floor.py` → `363 >= 363` | **`PASS(T-QA-02): 394 acceptance cases >= floor 394`**（exit 0） | 数字过期（33 个用例的增幅对应 §9 之后的提交），结论未变。 |
| §2：「evidence/ 未新增证据文件」 | `git log fe72107^..HEAD -- evidence/` → **`fe15276`**，新增并跟踪 `evidence/aud001_sampling_review_20261102.md`（`git ls-files` 确认入库） | **H**。§2 的事实陈述已与仓库不符——这条提交同时是 signoffs.jsonl 的第一条真实签署（文件内确有 1 条：`AUD-001-03, reviewer=slow-is-fast, role=independent-reviewer, verdict=approved`），属评审范围内的重要事实，交接包却声明其为空。 |
| §6：看板与矩阵不一致算 finding | `GOVERNANCE_STATUS.html` 当前行：「最新提交 3f14712…19/19 必需检查落地；本地 --all 18/19」——与实际一致（1465b4a 本身是刷新看板的提交，看板反映其父提交属正常）；页内其余 `17/18`/`18/18`/`385`/`392` 均在历史事件行内 | 未发现现役数字与矩阵不一致。 |

**总体判断**：过期是「数字 + 一处事实陈述」层面的，结论未翻转（本地唯一红仍
是 T-VD-01b、CI 全绿、F1–F6 修复均真实成立）；但 §3 的判定口径和 §2 的 evidence
声明若被字面采信，会导致误判——这正是交接包作为「唯一入口」最不该错的两处。

---

## 五、§8 自曝失误残留检查

| # | 自曝失误 | 残留检查结果 |
|---|---|---|
| 1 | `\| tail; echo $?` 取 tail 退出码 | `grep -rn "tail; echo\|\| tail.*echo \$?" scripts/ governance/ *.md docs/` → 唯一命中 `governance/review_handoff.md:165`（自述本身）。**无残留**。 |
| 2 | `gh run watch --exit-status` 假绿 | `grep -rn "gh run watch" scripts/ governance/ *.md docs/` → 仅 `review_handoff.md:74,166`（自述）。无脚本使用。**无残留**。本次评审亦按其教训用 `gh run list --json conclusion` + `gh run view --json jobs` 交叉核对。 |
| 3 | `$(python -c …)` 批量生成路径遇 `\r\n` 全假红 | 检查项调用已全部收敛进 `audit_policy.json` 的 `check_args`，`gov_run.py` 用 `subprocess.run([sys.executable, path, *extra])` 列表传参，无命令替换路径。**无残留**。 |
| 4 | 清单生成器读 `signoff.reviewer` 而 apply 实写 `by` | `record_signoff.py:76` 写 `'reviewer'`；`apply_signoffs.py:110,146` 读 `entry.get('reviewer')`——两端字段名一致。`export_owner_worklist.py:175` 兼容读 `s.get('by') or s.get('reviewer')`。真实 signoffs.jsonl（1 条）字段为 `reviewer`。**无残留**。 |

---

## 六、其他发现（按 H/M/L 分级）

- **[H] 交接包过期数字 + 与事实不符的 §2 声明**（详见 §四 表格）。交接包自称
  「给下一位评审者的输入」，其 §3 判定口径（17/18 / 18 步）与 §2 事实声明
  （evidence/ 无新增）都已失效。§9 证明作者有能力在文末追加更正，但没把
  §3/§4 的一键复验块一并更新，文件现在是自相矛盾的。
- **[M] 范围新增的 12 个提交无逐条说明**。§2 表格止于 `6206abf`，而
  `f4fff10`→`1465b4a` 里包含第一条真实签署、EXC-03 例外登记、新门禁
  T-REF-03、六态报告等实质变更；「范围只增不减」一句不足以让评审者覆盖它们。
- **[L1] `--no-state` 会静默跳过漂移检测**（`matrix_caretaker.py:230-231`
  在基线逻辑之前 `sys.exit(0)`）。这不是 bug（开关语义如此），但 F4 的验证
  方法若被评审者"顺手"加上 `--no-state`，会得到无告警的假阴性——我在复验时
  第一步就踩了这个坑。建议在脚本 docstring 或交接包里写明。
- **[L2] `check_audit_closure.py` 是本地 `--all` 的时长大头**（161.2s / 总时长
  约 3 分钟）。无发现，仅记录现象，供未来调 `timeout-minutes` 参考。

**通过项存档（均跑了命令）**：F1/F3/F4/F5/F6 PASS（§二）；单测 387 全绿；
`verify_test_floor` 394>=394 exit 0；`export_owner_worklist.py --check`
`PASS(worklist): 清单与矩阵一致（matrix=d3914933e271, … 22 条）` exit 0；
`check_rule_tests.py` `PASS(T-REF-03): 规则侧用例引用全部可解析…` exit 0；
CI run 41395041366（HEAD 1465b4a）conclusion=success、19 步全 success。

---

## 七、未验证的怀疑（明确标注：没证据）

1. 六态报告「待签 21 条里只有 8 条真能读」的分类正确性——未逐条核对六态报告与矩阵。
2. 上游 `slow-is-fast/aasegs-gov-plane` 的 PR#1 与 `28ef6b1` 内容是否真如 pin 注
   所述——未拉取上游仓库比对。
3. CI 上 T-VD-01b 步骤显示 success，但我只能看到 conclusion，无法确认它在 CI
   环境里确实构造了"数据面凭证尝试写控制面被拒"的场景（step 内部语义未验）。
4. `audit_policy.json` 的 `honest_limits`、`retention` 等字段的实质正确性未审。

## 八、我做不到什么

- **不能下 verdict**：按约束未运行 `record_signoff.py` / `apply_signoffs.py`，
  未写 `signoffs.jsonl`，未改动 `governance/` 下任何文件。
- **不能充当独立评审主体**：同模型家族（见效力声明），不满足前置③。
- **无法复现历史时间点**：F2 的"当时基线红"只能以提交序列与起点处 PASS 间接
  佐证，无法重建当时工作区。
- **无法验证人因/物理信任域**：EXC-01/EXC-02、第二 PAT、独立账号均超出本机可验范围。
- **无法访问上游仓库状态**：F1 只能验证"本地与 pin 声明一致"，不能验证上游提交本身。
