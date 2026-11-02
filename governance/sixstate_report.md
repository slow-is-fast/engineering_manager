# 六态报告：三个层上的状态区分能力

> **自动生成，勿手改。** 重新生成：`python scripts/export_sixstate_report.py`
> 数据指纹：`40b938f6cc2a`（`--check` 比对；材料变了就红）
>
> **这是产物，不是复核记录。** 它不判"够不够"，只报"是什么"。
> `AUD-002-03` 的复核结论由人写，写在 `evidence/` 里，不是这里。
>
> **过期会被拦住**：`tests/test_sixstate_report.py` 的 `test_report_is_in_sync`
> 会在数据变化后报红，不需要额外的 `required_checks` 接线。
> （对照 `coverage_pack_aud001.md`：那份的 `--check` 至今没有任何门禁在调用。）

## 一、这份报告要回答什么

`AUD-002`（P0）的验收标准与闭合条件原文：

> 验收标准：缺少执行器、测试或有效证据时不能进入 verified；配置漂移或证据过期触发降级。
> 闭合条件：状态机测试和负向测试通过；**报告可区分六种状态**。

六种状态指 `documented / configured / tested / verified / degraded / excepted`，定义在 `scripts/validate_controls.py:12` 的 `STATES` 元组。

**但六态不是"整个系统"的词汇表，它只属于其中两层。** 第三节把三层并排放。

## 二、三层各用什么词（这是"报告能否区分六态"的第一个岔路）

| 层 | 文件 | 字段 | 取值 | 校验强度 | 是否参与门禁 |
|---|---|---|---|---|---|
| 规则 | `rule-registry.json` | `status` | 六态 | 只校验键集与布尔类型（`validate_controls.py:108`） | **否**（`rule_status_participation: schema_only`） |
| 控制 | `control-catalog.yaml` | `state` | 六态 | 键集 + 布尔 + 「`verified` 必须前三态皆真」（`validate_controls.py:36`） | **是** |
| 断言 | `governance/acceptance_matrix.json` | `kind` | `script` / `test` / `manual` / `excepted` / `evidence` | 由 `check_audit_closure.py` 判 | **是** |

读法：**第三层根本不用六态。** 断言层用 `kind` 表达"这条怎么验"，用 `signoff` 表达"谁验过"。所以"报告可区分六种状态"这句话如果指全系统，它天然缺一层；它只能指规则层与控制层。

## 三、控制层（权威层）：55 个控制的真实取值

| 状态 | 为 true 的控制数 | 占比 |
|---|---|---|
| `documented` | 55 / 55 | 100% |
| `configured` | 34 / 55 | 61% |
| `tested` | 50 / 55 | 90% |
| `verified` | 0 / 55 | 0% |
| `degraded` | 0 / 55 | 0% |
| `excepted` | 0 / 55 | 0% |

**组合分布**（"只有这几个为 true"）：

| 组合 | 控制数 |
|---|---|
| `documented` + `configured` + `tested` | 34 |
| `documented` + `tested` | 16 |
| `documented` | 5 |

从未取值为真的状态：`verified` / `degraded` / `excepted`。

**这一行是本报告最重要的事实。** 六个字段都在、都被校验，但真正有值的只有3 个。剩下的不是"暂时为 0"，是**从来没有过非 0**——见第五节。

## 四、规则层：59 条条款的真实取值

| 状态 | 为 true 的规则数 |
|---|---|
| `documented` | 59 / 59 |
| `configured` | 6 / 59 |
| `tested` | 6 / 59 |
| `verified` | 0 / 59 |
| `degraded` | 0 / 59 |
| `excepted` | 0 / 59 |

**组合分布**：

| 组合 | 规则数 |
|---|---|
| `documented` | 53 |
| `documented` + `configured` + `tested` | 6 |

> 规则层的 `status` 是 **schema_only**：`validate_controls.py` 只校验键集与布尔类型，从不强制任一为真，也不把它用于任何门禁判定。`rule-registry.json` 顶层的 `rule_status_note` 自己就是这么写的。
>
> 所以这一层的数字**不能当"规则落地了没有"读**。要读规则级执行状态，必须走 `enforcement.controls` 指向的控制条目——那是第三节。

## 五、"能写、能存、没人读"：三个需要单独看的状态

这一节对每个状态扫一遍源码（`scripts/` 与 `executor/`，排除导出脚本本身），按"定义 / 写入 / 读取"归类。低估计原则：分不清读写的一律算读取。

### `verified`

- 定义：1 处（`scripts/validate_controls.py:12`）
- 写入：1 处
  - `executor/drill.py:123`：`entry["verified"] = True`
- 读取：2 处
  - `scripts/validate_controls.py:35`：`if st['verified']:`
  - `executor/gate.py:376`：`("all_p0_controls_verified", "verified")):`

  **`verified` 是被真读的，但恒不成立。** `executor/gate.py:376` 的准入条件 `all_p0_controls_verified` 会逐个检查 P0 控制的 `verified`；而控制层 `verified` 为 true 的数量是 0。也就是说这个准入条件目前**永远不满足**——它是"未达标"，不是"没检查"。

### `degraded`

- 定义：1 处（`scripts/validate_controls.py:12`）
- 写入：1 处
  - `scripts/verify_evidence_freshness.py:77`：`c['state']['degraded'] = True`
- 读取：0 处
  - （**未发现读取点**）

  **降级到底有没有生效？** 有，但不是因为这个字段：`verify_evidence_freshness.py --degrade` 除了置 `degraded=true`，还顺手把 `tested` 置 false（`verify_evidence_freshness.py:78`），而 `tested` 是有消费者的（`executor/gate.py:368` 的准入判定）。所以降级的效果是**通过 `tested` 实现的**，`degraded` 只是留了个记号。

  **哪个字段真的有用，看谁读它，不看它在 schema 里出现过。** 这正是"算出来却没人看的值等于没有"的又一例——只不过这次它旁边那个字段恰好替它把活干了，所以症状被掩盖了。

### `excepted`

- 定义：1 处（`scripts/validate_controls.py:12`）
- 写入：0 处
  - （无）
- 读取：0 处
  - （**未发现读取点**）
- 另 7 处出现这个词，但**消费的是另一层**，不计入读取：
  - `scripts/matrix_caretaker.py:43`：`ALLOWED_KINDS = {'test', 'script', 'evidence', 'manual', 'unimplemente`
  - `executor/closure.py:49`：`"excepted")`
  - `executor/closure.py:196`：`elif kind == "excepted":`

  **例外实际不在这一层。** 控制层 `state.excepted` 零使用；真实的例外登记在断言层：`acceptance_matrix.json` 里 `kind=excepted` 的断言，以及 `exception_register.json` 的 `EXC-01/02/03`。两套词汇表达同一件事，没有对齐——这也是"报告可区分六态"要面对的问题：**六态里有三个从未取值，其中 `excepted` 的语义已经在别处被实现了另一遍。**

## 六、候选报告对六态词表的覆盖（机器 grep）

| 报告 | `documented` | `configured` | `tested` | `verified` | `degraded` | `excepted` |
|---|---|---|---|---|---|---|
| `GOVERNANCE_STATUS.html` | 0 | 0 | 1 | 12 | 0 | 6 |
| `governance/owner_worklist.md` | 0 | 0 | 0 | 0 | 0 | 4 |
| `governance/coverage_pack_aud001.md` | 0 | 0 | 19 | 1 | 0 | 0 |

**这张表是 `AUD-002-03` 的直接输入。** 在这份报告出现之前，三份候选报告里`documented` / `configured` / `degraded` 全为 0——它们没有在用六态的词汇。所以"报告可区分六种状态"在 2026-11-02 之前**字面不成立**，本报告是把缺失的那一份补上，不是把标准降低。

## 七、这份报告不能证明什么

- **不证明六态模型是对的。** 它只说明现状：哪些状态有值、谁在读写。模型设计对不对是另一件事。
- **不证明降级机制完备。** 它指出降级靠 `tested=false` 生效，但"证据过期之后准入门槛是否真的拦住"要看 `RVF-01` 与 `GATE-01` 的用例，不是这份报告。
- **不证明规则层状态可信。** 第四节已经说明它是 schema_only；本报告在这里的作用恰恰是提醒别拿它当证据。
- **"未发现读取点"是低估计结论。** 正则扫不到字典整体传递（比如把 `state` 整个传给另一个函数）。所以它是"我没找到"，不是"不存在"。

## 八、复算方式

```bash
python scripts/export_sixstate_report.py           # 重新生成
python scripts/export_sixstate_report.py --check   # 只比对指纹
```

数字全部由 `rule-registry.json` / `control-catalog.yaml` / `governance/acceptance_matrix.json` 算出，没有一个是写死的。「谁读字段」由源码正则扫出，排除三个导出脚本（否则报告会自我指涉）。
