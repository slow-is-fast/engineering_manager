# 证据：远端能力协商落地 + 两处"空绑定"补检（2026-10-31 01:05）

## 1. 做了什么

把 `AUD-009-03`（目标系统不支持幂等 / 查询不可用）与 `AUD-010-03`（远端状态
漂移与补偿失败）从 `unimplemented` 落到 `test`。验收矩阵 `unimplemented`
**6 → 4**。

控制面 `slow-is-fast/aasegs-gov-plane`：
- `271a672` 新增 `executor/remote.py` + T-REM-01..19
- `73c7732` 补 T-REM-20 / T-REM-21

数据面同步 vendor 副本与用例镜像，pin bump 到 `73c7732`
（tree `328591ecd4bf`，executor/ 内容哈希 `cae97b37bf6e`）。

## 2. AUD-009-03：能力不足不得默认重放

决策表（失败关闭）：

| 幂等 | 查询 | 决策 |
|---|---|---|
| `key` | * | `REPLAY_WITH_KEY`（且必须带 key） |
| `none` | `available` | `RECONCILE_FIRST` |
| `none` | `unavailable` | `MANUAL_REMEDIATION_REQUIRED` |
| 未登记 | — | `MANUAL_REMEDIATION_REQUIRED` |

**未登记按最保守**：`capability()` 对没见过的系统返回 `none/unavailable` +
`registered=False`。"没听说过"不等于"能配合"——与 retrypolicy 里"未知操作按
破坏性处理"同一条原则。

写的过程中发现两处语义漏洞，一并补掉：

1. **`RECONCILE_FIRST` 原本只是个返回值。** 调用方完全可以无视它直接
   `replay()`，AUD-009-03 等于什么都没拦。现在 `replay()` 要求拿出
   `reconcile` 的 `MATCH` 结论，拿不出就抛 `RemoteRejected`。调用方自己拼
   一个 `{"result": "MATCH"}` 也骗不过去——**先看能力，不看结论**（T-REM-09）。
2. **`reconcile` 原本只在"查不了且没给 actual"时判 `UNVERIFIABLE`。** 现在
   `actual` 拿不到、或远端查不了，都判无法核对。查不了却硬塞一个 `actual`
   进来，来源不可信，不得采信为 `MATCH`（T-REM-12）。

## 3. AUD-010-03：漂移与补偿失败

- 漂移 → `DRIFT_DETECTED` + `next: MANUAL`，禁止基于旧快照继续恢复
- 补偿 `failed` / `partial` → `COMPENSATION_FAILED` + `next: MANUAL`。
  **partial 是最危险的返回值**：看起来补偿过了，实际遗留一半副作用，
  当成功继续推进等于把不一致悄悄固化。
- 补偿无 `plan_ref` → 拒绝；未知补偿结果 → 拒绝（不默认放过）

## 4. 记账时发现的 ref 覆盖不全

`AUD-010-03` 覆盖"漂移"**和**"补偿失败"两件事，`AUD-009-03` 覆盖整张决策表，
而验收矩阵每条断言的 `ref` 只能指一条用例。原先可用的用例（T-REM-04 / 11 / 14）
各自只测一个侧面，指过去会丢掉另一半。补：

- **T-REM-20**：漂移 → 补偿 partial → 仍是人工，走完链条仍不得重放，且
  `drift_detected` / `compensation_failed` 两条审计都要留痕（`reconciled`
  不得出现）。
- **T-REM-21**：决策表逐格走一遍（含未登记兜底），对 `MANUAL` 的格子断言
  `replay` 真的抛错、不只是返回个标签。**只测最坏那一格的话，"把
  none+available 改成直接放行"这种变异逃得掉——而它恰好是最容易出事的格子。**

## 5. 两处"空绑定"（本轮真正的收获）

### 5.1 T-VD-01：本地 vendor 副本此前无人校验

数据面的用例跑的是**本地 vendor 的 `executor/`**，不是控制面那个 commit。
而 `verify_executor_pin.py` 只下载 tarball 校验 pin——**两者之间没有任何
检查把它绑起来**。后果：有人本地改宽 `executor/gate.py` 里的一条规则，
数据面自己的用例照样全绿，pin 照样显示"我们用的是 X"。

这正是本规范一直在防的"文档声明替代机器判定"，只是这次发生在我们自己身上。

补检后做**受控演练**（不靠推理）：

| 注入 | 结果 |
|---|---|
| 改 `remote.py` 把 `MANUAL` 兜底换成放行重放 | 红：`内容不一致: ['executor/remote.py']` |
| 往 `executor/` 多塞一个文件 | 红：`本地多出的文件: ['executor/__evil.py']` |

**坑（实测）**：Windows `core.autocrlf=true` 下工作区文件带 CRLF，而 tarball
里是 LF——不做换行规范化会产生**假失败**。实测 25 个文件里 2 个
（`closure.py` / `gate.py`）因此不一致，规范化后逐字节相同。这与 T-QA-04
那次"浅克隆导致假绿"是同一类陷阱的镜像：一个是该红没红，一个是没红却红。

### 5.2 T-QA-04：基线里的 pin 版本此前无人比对

`quality_baseline.json` 的 `executor_pin_version` 只是个**必填字段**，没有
人检查它与 `governance/executor_pin.json` 是否一致。本轮开工时实测：基线
记着 `61fed88`，pin 已经是 `73c7732`——两处都声称"我们用的执行器版本"，
各说各话也没人管。补交叉比对，`commit_sha` 与 `tree_sha` 两个字段都比对。

## 6. 连锁发现：T-QA-04 的脏检查被换行误伤

改完 5.2 后本机 T-QA-04 恒红：`git status --porcelain` 在 `autocrlf=true`
下把仅换行不同的文件报成已修改（实测：工作区 CRLF、blob LF，规范化后逐字节
相同，`status` 报 ` M` 而 `git diff --exit-code` 判无差异）。

**判据必须用与门禁同一把尺子。** 改用 `git diff --quiet --exit-code`（与 CI
同一套 clean/smudge 口径）+ `git ls-files --others` 兜住未跟踪文件（diff
看不到它们，但不能放过）。这与 2026-10-09 那次 "`git status` 与 `git diff`
不一致" 是同一个坑，这次出现在治理脚本内部。

## 7. 变异检验

先确认基线绿，再注入；还原一律内存备份 + `try/finally` 写回。

| 批次 | 变异数 | 捕获 | 逃逸 |
|---|---|---|---|
| `executor/remote.py` 全量 | 14 | 14 | 0 |
| T-REM-20 / T-REM-21 定向 | 5 | 5 | 0 |
| T-QA-04 交叉一致性 | 4 | 4 | 0（**第一轮 1 条逃逸**） |
| T-QA-04 未跟踪分支 | 1 | 1 | 0 |

**第一轮逃逸**：把 `tree_sha` 从比对字段里删掉，没有任何用例发现——commit
对得上就能蒙混过关。补 `T-QA-04 pin_tree_mismatch` 后归零。

另修了一个自己的方法论 bug：变异脚本最初用正则抓"哪些用例失败"，但
`unittest -v` 会为**每一条**用例打印一行（含通过的），导致恒定显示"19 条
失败"——归因永远是全集，等于没做归因。改为只匹配 `... FAIL/ERROR` 结尾的
行与底部 `FAIL: xxx` 汇总行。

## 8. 读数

| 指标 | 本轮前 | 本轮后 |
|---|---|---|
| 验收矩阵 `unimplemented` | 6 | **4** |
| 控制面用例 | 88 | **109** |
| 数据面用例（T-QA-02 口径） | 139 | **164** |
| 单元测试（`discover` 实跑） | 132 | **157** |
| 用例下限 `min_test_count` | 139 | **164**（删除余量仍为 0） |
| GATE-01 阻断 / 等级 | 10 / G1 | **10 / G1**（门槛未放宽） |
| 断言满足 | 63 | **65** |

口径说明：`discover` 只统计 `tests/test_*.py`，比 T-QA-02 少 7——后者还
计入 `tests/negative_static.py` 的 `T_XXX_`（132 + 7 = 139，157 + 7 = 164）。
另外 `grep -c "def test_"` 会多算约 10 条：docstring 用例里故意写了
`def test_pad_one` 这类字符串，正则分不清——这也是当初改用 AST 计数的原因。

CI 实测（非仅本地）：控制面 `run 41092055097` 109 条绿；数据面
`run 41095042684` 157 条绿，含新的 vendor 副本校验步骤。

## 9. 诚实边界

- **`remote.py` 做的是决策，不真的调用远端。** 远端能力来自调用方声明，
  声明错了策略拦不住。`T-REM-18` 显式断言"能力谎报拦不住"并写成用例
  （而不是写在注释里），防止后来者误以为 AUD-009-03 覆盖了声明错误场景。
  真正的防线是能力登记须带独立来源证据，不在本模块职责内。
- **vendor 副本校验是内容哈希，不是来源证明。** 它证明"本地代码 == pin 的
  那个 commit"，不证明那个 commit 本身是对的——后者靠 PR 审批与 CI。
- **T-QA-04 的脏检查改用 diff 后，不再能发现"仅换行变化"的未提交改动**——
  这是有意的取舍：换行不构成治理变更，为此报红只会把人逼到关掉检查。
- `AUD-009-04` / `AUD-010-04` 仍是 `manual_pending`：真实代表性副作用端到端
  与恢复演练，需要真实远端与独立复核，受 EXC-01 / EXC-02 限制（2027-04-30 到期）。
- 剩余 `unimplemented` 4 条：`AUD-013-03` / `014-03` / `015-03` / `016-03`。
