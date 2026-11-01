# 正式评审交接包（选项 ③）

> **这份文件是给下一位评审者的输入，不是评审结论。**
> 它由本会话的 Agent 编写；同一个 Agent 已经做过一轮 **draft 评审**（未落账）。
> 按 `skills/adversarial-review/SKILL.md` 前置③（评审主体 ≠ 作者），
> 正式评审必须在**新会话、不同家族**的 review-agent 里重做一遍——
> 本文件只负责把"你需要知道什么才能开始"讲清楚，不替你下判断。

---

## 0. 它不是什么

- 不是"作者已自证清白"的说明。§5 专门列出**作者最可能错的地方**。
- 不是 verdict。verdict 只能由评审者经 `record_signoff.py` 落账（role=`independent-reviewer`）。
- 不是断言关闭凭证。`verdict=approved` ≠ 断言 closed（铁律①）；关闭另走
  `record_signoff` → `apply_signoffs`，且需 Owner 确认。

## 1. 为什么必须换人

| 约束 | 出处 | 现状 |
|---|---|---|
| 评审主体 ≠ 作者 | 铁律④ / SKILL 前置③ | 本会话 Agent 既是提交作者，又是 draft 评审者，**不满足** |
| 单人仓库无第二人类审批主体 | `EXC-01`（2027-01-31 到期） | 第二 PAT 不构成独立审批主体，已实证 |
| 机器门禁全绿 | SKILL 前置② | 见 §3：本地**不可能**字面满足，须按 §3 的口径判定 |

换家族的实际意义：draft 评审与本会话共享上下文，同源盲区不会被自己发现。
上一轮已经证明这一点——首跑抓到的是**作者自己 12 个提交、潜伏 1 天**的 `T-VD-01` 红。

## 2. 评审范围

起点 `fe72107^`，终点为交接时的 `HEAD`（本文件提交时是 `a0879b6`）。

```bash
git log --oneline --reverse fe72107^..HEAD
```

| 提交 | 内容 | 为什么在范围里 |
|---|---|---|
| `fe72107` | 修 draft findings F3–F6 | draft 评审的原始对象 |
| `372969d` | 补 2 个 workflow 步骤 | `--verify` 抓到"注册了但从未在 CI 跑"，是本轮最重要的真实缺陷 |
| `e80d91a` | T-QA-04b 接线校验 | 由上一条事故直接催生的门禁 |
| `32746b7` | `check_args` 显式声明 + fail-closed | 接线的第三条腿 |
| `0c3c83d` | T-EXP-01 例外到期 | `expires` 字段此前无人比较 |
| `7a575b9` | T-OWN-01 清单 + 防漂移 | Owner 侧 22 条断言的执行入口 |
| `83c8b0e` | 清单命令链 e2e | e2e 当场抓到投影 bug（见 §8） |
| `8e11594` | 校验 `signature` 字段 | 此前该字段从不被校验，手写 JSONL 可绕过 |
| `c642d74` `308b4c1` `26a9658` | `--all` 跑完全部再汇总 / 措辞 / `reviewed_at` 未来时间告警 | 三处"算出来却没人看"的同族缺陷 |
| `8e3532a` `1a1d9fc` `dd2b6c2` `74dd673` `275d19d` `090835b` `9a7902b` `f0fde31` `a0879b6` | 看板刷新 | 只改 `GOVERNANCE_STATUS.html`，可略读但请核对数字是否与事实一致 |

**不在范围**：`executor/` 下的产品代码本轮未改（只 bump 了 vendor pin）；
`evidence/` 未新增证据文件——本轮新增的都是自动化门禁，"证据"即 CI 运行记录本身。
如果你的判断是"改门禁也该附 evidence"，这就是一条 finding，请照报。

## 3. 前置②怎么满足（这里有个坑，先说清楚）

`SKILL.md` 要求"机器门禁全绿（`gov_run --all`）"。**在这台机器上这句话字面不成立**，
原因不是回归，而是设计：

```bash
python scripts/gov_run.py --all     # → exit 1，汇总行 17/18
```

第 5 项 `verify_credential_domain.py`（`T-VD-01b`）在本机**必红**：人类 PAT 同时
可写控制面与数据面，测不到"数据面运行时凭证不得写控制面"这件事。脚本的原话是
"不可判定即拒绝：请在 CI 中运行"。把它做成绿只有两种办法，两种都是造假。

因此判定口径是：

1. **本地**：`--all` 汇总行必须是 `17/18`，且唯一的 `FAILED` 必须是
   `scripts/verify_credential_domain.py`。出现第二个 `FAILED` 就是真问题。
2. **CI**：`governance` workflow 全绿（18 个 `--check` 步骤全 pass）。
   `gh run list --limit 5 --json headSha,conclusion` 交叉核对，**不要只信
   `gh run watch --exit-status` 的退出码**（本轮踩过：它报了 success，实际是 failure）。

若你认为"本地有一项红就不能算满足前置②"，**这个分歧本身就该写成 finding**，
不要沉默地降级继续，也不要替它发明例外。

环境变量（否则落账会被拒）：

```bash
export GOV_REVIEW_AGENT=<你的身份>        # 评审主体
export GOV_AUTHOR_IDENTITY=<作者>          # 与上面必须不同
export GOV_ACTING_IDENTITY=agent-runner    # 执行工具的那一方，也不是评审主体
```

## 4. draft findings 状态与**独立验证方法**

| # | 严重度 | 内容 | 作者声称 | 你可以这样验 |
|---|---|---|---|---|
| F1 | **H** | 本地 vendor 与 `executor_pin.json` 不一致（`T-VD-01` 潜伏红） | 已闭环：上游 PR#1 → `7c8a086` → 重算 content hash → bump pin | `python scripts/verify_executor_pin.py`；再核对 `governance/executor_pin.json` 的 `content_hash_sha256` 是否等于对本地 `executor/` 重新计算的哈希 |
| F2 | — | 正式评审因基线红终止（流程性） | 已消解 | 看 `fe72107^` 时点的 `gov_run --all` 是否红；这条不再需要复现 |
| F3 | M | caretaker `--state` 可指向 `governance/*.json` 并覆写 | 已修：`_ensure_state_path_safe` 拒绝 | `python scripts/matrix_caretaker.py --state governance/quality_baseline.json; echo $?` → 期望 2，且该文件未被改动（`git status` 干净） |
| F4 | M | 漂移检测在 CI 结构性失聪（state 被 gitignore → 每次 fresh clone 都是基线） | 已修：`_git_baseline_fallback` 用 `git show HEAD~1:<path>` | 删掉 state 文件后在**有历史的**仓库里跑 caretaker；看是否仍能报漂移。注意浅克隆下会降级为"无基线"，这算已知边界 |
| F5 | M | 指纹只含 `id`，`kind` 翻转不触发告警 | 已修：指纹含 `(id, kind)` / `(key, owner, type)` | 改一条断言的 `kind`（如 `manual`→`excepted`）后跑 `matrix_caretaker.py`，期望漂移告警 |
| F6 | L | 多条分支无用例 | 已补 9 条 | 读 `tests/test_matrix_caretaker.py`；重点看"损坏 state 降级""假 kind""`audit_driven` 缺 `issue`"是否真的断言了失败原因，而不只是断言非零退出 |
| F7 | L | `GOV_REVIEW_AGENT` 等 env 身份是**咨询性信任**，非密码学 | **不修**，记录为已知限制 | 见 §6。若你认为它该被升格成强制，请说明用什么机制落地 |

一键复验（作者跑过的，仅作参照——**不要以它的 PASS 行为准**）：

```bash
python -m unittest discover -s tests -p "test_*.py"      # 356 tests
python scripts/gov_run.py --all                           # 17/18，见 §3
python scripts/verify_test_floor.py                        # 363 >= 363
python scripts/export_owner_worklist.py --check            # 清单与矩阵指纹一致
```

## 5. 作者最可能错的地方（请重点攻击）

按"最可能出错"排序，这几条都是作者**自己知道但没解**的：

1. **`T-QA-04b` 读不懂条件分支。** `verify_required_checks_wired.py` 用正则扫
   workflow 文本里的 `gov_run.py --check <path>`，**不看 `if:`**。一个只在
   `pull_request` 上触发的步骤，静态上也算"接上了线"。这条检查证明的是
   "步骤文本存在"，不是"它在每次 push 到 main 时都会跑"。
2. **`check_args` 的 fail-closed 只保证"声明了"，不保证"声明对了"。** 目前
   `T-OWN-01` 配的是 `[["--check"]]`——若哪天被改成 `[[]]`，它就跑成生成模式：
   每轮改写 `owner_worklist.md`、永远 exit 0、什么也没查。没有任何东西阻止
   这次回归。同类风险也在 `--check` 与 `--enforce` 的取舍上。
3. **`F4` 的 git 回退依赖 `HEAD~1`。** 同一提交里既改矩阵又改 state，或浅克隆
   （`--depth=1`），回退就失效并降级为"无基线=放行"。降级路径本身是刻意设计的
   （宁可少判也不误判），但它意味着**漂移检测在 CI 上并非无条件生效**。
4. **`signature` 是无密钥 sha256。** 拦的是手写、拼错、事后篡改；拦不住能重算的人。
   真正的独立性靠"reviewer ≠ 执行主体" + 矩阵改动经人工 review 后 commit。
5. **e2e 用 tmpdir 跑全链，不覆盖真实 `signoffs.jsonl` 的并发/追加语义。**
6. **`--all` 现在会跑完 18 项**（此前第 5 项就停）。副作用：本地一次 `--all`
   写 18 条 `gov.check.completed` 到审计流，且第 5 项失败后仍继续——请确认这不
   引入"失败也被算作已完成运行"的口径问题。

## 6. 已知限制（不要重复报为新 finding）

| 限制 | 原因 | 谁来管 |
|---|---|---|
| `EXC-01`：第二人类主体不可达 | 单人仓库，第二个 PAT 不是独立审批主体 | 2027-01-31 到期前必须三选一 |
| `EXC-02`：独立账号与主机不可达 | Owner 已明确不提供真环境 | 2027-04-30 到期前必须三选一 |
| `T-VD-01b` 本地必红 | 人类 PAT 横跨两域，测不到要测的东西 | CI 覆盖；本地按 §3 口径 |
| env 身份咨询性信任（F7） | 守卫防流程失序，不防本机 env 伪造 | 属 EXC-02 信任域 |
| `signature` 非密码学 | 无密钥、算法公开 | 见 §5 第 4 条 |

另：`governance/owner_worklist.md`、`GOVERNANCE_STATUS.html` 是**投影**，
不关闭任何断言、不产生任何签署。它们与矩阵不一致时，以 `acceptance_matrix.json` 为准——
如果发现看板数字与矩阵对不上，那是 finding。

## 7. 交付与落账

```bash
python scripts/record_signoff.py \
  --assertion-id <被评审的断言 id> \
  --reviewer <你的身份> \
  --role independent-reviewer \
  --verdict approved|needs-work|rejected \
  --evidence evidence/<你的评审报告> \
  --basis "<≥10 字：看了什么、为何给这个结论>"
```

- 报告文件先落 `evidence/`，再 `gov_run --accept-evidence --by … --reason …` 登记；
- `verdict` 由**评审主体**落账，作者不得代跑；
- 落账后 `apply_signoffs.py --apply --by <执行者>` 才把矩阵里的
  `verified` 投影出来，且仍需 Owner 确认。

## 8. 作者自曝的操作失误（信任校准用，不是评审发现）

写在这里，是因为它们都曾经**看起来像绿**：

1. `python … | tail; echo $?` 取到的是 `tail` 的退出码，曾据此声称门禁通过。
2. `gh run watch --exit-status` 报 success，实际该 run 是 failure；此后一律用
   `gh run list --json conclusion` 交叉核对。
3. 用 `$(python -c …)` 生成检查清单批量跑时，Windows 的 `\r\n` 让 17 个路径带上
   尾随 CR，全部被判"不在 required_checks 里"——**看起来像 17 条真红**。
4. `83c8b0e` 的 e2e 抓到真 bug：清单生成器读 `signoff.reviewer`，而
   `apply_signoffs` 实写 `by`；单测一直绿，是因为 fixture 自造了 `reviewer` 键
   ——**测试自洽、现实不符**。同类问题请在别处继续找。
