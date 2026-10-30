# drill → automated：三场演练变成三个常态化校验器（2026-10-30T21:00+08:00）

**CI 追溯（已更正 2026-10-30 21:50）**：数据面 run `41007061157`（109 tests OK；`PASS(T-QA-01)`、`PASS(T-QA-02)`、`PASS(CLM-01)`；成熟度等级 G1 / 阻断 10；§四 断言 90 条满足 63）。

> ⚠️ **本文件原先把 `PASS(T-QA-04): baseline reviewed together with governance @051eb29f2f8f` 当作通过证据，那条结论是错的。**
> 同日冷读复核实测发现：`actions/checkout` 默认 `depth=1`，浅克隆下 `git log -1 -- <path>` 恒返回 HEAD，于是 `B == G`，T-QA-04 **无条件打印 PASS**——它当时在 CI 里从未真正工作过。
> 修复与实证见 `evidence/cold_review_20261030T215000Z.md`：已加 `fetch-depth: 0`、脚本对浅仓库失败关闭，并用一次受控演练确认它在 CI 上**真的会红**（run `41065699717` 失败于 `baseline drifted`）。

---

## 一、为什么做

上一轮全量复核把 44 条 `tested` 分成两类：**41 条 `automated`**（每次改动都会再跑）和 **3 条 `drill`**（只有一次性演练记录）。这 3 条是 `QA-01`、`QA-02`、`BASE-01`，证据分别是 PR #3、#2、#4。

`drill` 不是错误，但它有个要命的性质：**演练证明了门禁在当时有效，不能证明此后每一次改动都被检查过**。PR #3 那天 CI 确实拦住了篡改；第二天有人把 action 从 `@v4` 换成别的，没人会再拦。

本轮把三场演练各自变成一个常态化校验器。**drill 计数归零。**

## 二、三个校验器

| 控制 | 校验器 | 强制语义 | 对应的原始演练 |
|---|---|---|---|
| **QA-01**（P1） | `scripts/verify_ci_app_binding.py` | `.github/workflows/*.yml` 里每个 `uses:` 必须 pin 到 40 位 commit SHA；浮动 tag（`@v4`/`@main`）一律拒绝。本地 action（`./`）不在此限——它跟代码一起受版本控制 | PR #3「篡改 CI」 |
| **QA-02**（P0） | `scripts/verify_test_floor.py` | 验收用例数（`tests/*.py` 的 `def test_*` + `negative_static.py` 的 `T_XXX_`）不得低于基线 `min_test_count`（当前 **110**，实际 116） | PR #2「删除验收测试」 |
| **BASE-01**（P0） | `scripts/verify_quality_baseline.py` | 基线七要素齐备 + **漂移检测** | PR #4「SHA 绑定三 SHA 绿-红-绿」 |

### 2.1 顺手把本仓的 CI 也 pin 了

QA-01 不是纸上要求：本仓 workflow 原本用 `actions/checkout@v4`、`actions/setup-python@v5`——**两个浮动 tag**。已改为 SHA pin（`11d5960…` / `a26af69…`，版本号保留在注释里仅供人读）。

理由不是形式主义：浮动 tag 指向的内容可以被上游静默替换。今天审核过的 CI，明天可能执行完全不同的代码，**而流水线外观毫无变化**。

### 2.2 漂移检测为什么用提交先后、不用 SHA 比对

`BASE-01` 的语义是"SHA、配置或策略变化后旧检查与旧审核不得复用"。最直觉的实现是要求基线里的 `applies_to_sha` 等于当前 HEAD——但那意味着**每改一行代码都要重批一次基线**。这种规则没法执行，结果一定是被人绕过，比没有更糟。

改成：

- 取基线文件最后一次被修改的提交 `B`；
- 取治理范围（`governance/`、`rule-registry.json`、`control-catalog.yaml`、`scripts/`、`tests/`、`.github/`）最后一次被修改的提交 `G`；
- `B == G` → 同批审查，通过；`B` 严格早于 `G` → **治理变了基线没动，失败**；`B` 比 `G` 新 → 通过。

保留了"旧审核不得复用"的语义，但只在该审的时候审。

## 三、受保护质量基线

新增 `governance/quality_baseline.json`，七项要素：必需检查 / 可信 CI 来源 / 执行器与配置版本 / 测试阈值 / 适用 SHA / 例外 / 变更审批规则，外加审查人与审查时间。

基线里的数字是**下限不是目标值**。把下限设成刚好等于当前值，意味着任何删除都会被拦住，但新增测试不需要审批——这是有意的：**防退化，不防进步**。

## 四、负向用例与变异检验

新增 `tests/test_baseline_negative.py`，三条控制各一条独立负向用例，**每条都配正向对照**（证明拒绝不是"永远拒绝"）：

- `test_t_qa_01_unpinned_action_rejected` / `test_t_qa_01_pinned_action_passes`
- `test_t_qa_02_test_count_drop_rejected` / `test_t_qa_02_missing_baseline_fails_closed`
- `test_t_qa_04_baseline_drift_rejected`（建临时 git 仓：同批提交通过 → 只改治理文件提交 → 必须失败）/ `test_t_qa_04_incomplete_baseline_rejected`

**变异检验 5 条全红**：

| 变异 | 结果 |
|---|---|
| T-QA-01 接受任何 `uses`（浮动 tag 放行） | **CAUGHT** |
| T-QA-01 放宽 SHA 长度（任意 `@xxx` 都算 pin） | **CAUGHT** |
| T-QA-02 删掉下限比较（只统计不判定） | **CAUGHT** |
| T-QA-04 漂移不判定 | **CAUGHT** |
| T-QA-04 空列表当缺失（把"没有例外"判成未声明） | **CAUGHT** |

最后一条值得单独说：写第一版时我用 falsy 判断，`exceptions: []` 被当成"未声明"——**"没有例外"是好事，不是没写**。这跟 EvidencePack 那次踩的是同一个坑：区分"没写"和"没有"。

## 五、诚实边界

- **T-QA-02 只数数量**，不判断被删的那条是不是恰好该删。数量下限是防退化的粗粒度闸门，不替代对具体用例的评审——"该不该删"仍是人做的事。
- **T-QA-01 不校验 pin 的那个 SHA 内容是否安全**，只校验"是不是不可变引用"。pin 到一个恶意 SHA 它拦不住。
- **T-QA-04 只检查提交先后**，不审查变更内容是否合理。"这次下调阈值有没有正当理由"要人读 `change_approval` 里的记录来判断。
- **基线的 `min_test_count=110` 是此刻的下限**，随着用例增加应当上调；但上调不是自动的，需要人审——否则又变成"跟着代码悄悄改"。
- 三条控制的 `tested` 仍是**逻辑验证**，`verified` 仍为 0（EXC-02）。
- **drill 归零不等于"所有控制都有强证据"**——它只说明现在没有控制再靠"当年演练过一次"支撑。
