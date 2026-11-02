# `AUD-002-03` 复核材料：六种状态到底能不能被区分

> **这是复核材料，不是复核记录。** 它不下判断、不选 verdict、不写 `signoffs.jsonl`。
> 三个勾必须由人打；人对着它写下的结论，才是 `AUD-002-03` 的证据。
>
> 配套产物：`governance/sixstate_report.md`（自动生成，指纹比对，勿手改）。
> 本文件只讲"该怎么看"，具体数字一律指向那份报告，不在这里重复——
> 两处各写一份数字，迟早会有一处是旧的。

## 一、这条断言要什么

| 项 | 内容 |
|---|---|
| 断言 | `AUD-002-03`（P0） |
| 人工闸 | `six_state_report_review` |
| 原文 | 报告可区分六种状态的独立复核 |
| 所属 Issue | `AUD-002`：缺少执行器、测试或有效证据时不能进入 verified；配置漂移或证据过期触发降级 |
| Issue 闭合条件 | 状态机测试和负向测试通过；**报告可区分六种状态** |

`AUD-002-01` / `AUD-002-02` 已经是 OK（两条 test 断言）。**只差这一条，AUD-002 就能闭合。**

## 二、为什么现在才做：原来"No such 报告"

2026-11-02 实测三份候选报告（`GOVERNANCE_STATUS.html`、`owner_worklist.md`、
`coverage_pack_aud001.md`），`documented` / `configured` / `degraded` 三个词
**一次都没出现过**（见 `sixstate_report.md` §六的表）。它们讲的是 Issue 与断言，
不是控制层的六态。

也就是说：在这份报告出现之前，"报告可区分六种状态"这句话**字面不成立**。
让 Owner 对着那三份签"可以区分"，等于让他签一份不存在的东西。

所以本次先补产物（`sixstate_report.md`），再谈复核。**这是把缺失的东西补上，
不是把标准降低**——两者的区别值得在结论里说一句。

## 三、四个必须先知道的事实

| # | 事实 | 出处 |
|---|---|---|
| 1 | 六态定义在 `scripts/validate_controls.py:12`；**规则层 `status` 是 schema_only（不参与门禁），控制层 `state` 才是权威** | `sixstate_report.md` §二、§四 |
| 2 | 控制层 `verified` / `degraded` / `excepted` **三个状态从未取值为真**（不是"暂时为 0"，是从未有过非 0） | §三 |
| 3 | `degraded` **有唯一写入点、零读取点**。降级实际生效靠的是 `--degrade` 顺手把 `tested` 置 false，而 `tested` 有人读 | §五 |
| 4 | `excepted` 在控制层零使用、零读取；**例外的真实登记在断言层**（`kind=excepted` + `EXC-01/02/03`）。同一件事被表达了两遍，没有对齐 | §五 |

第 3 条尤其值得停一下：**降级生效了，但不是因为 `degraded` 这个字段。**
哪个字段真的有用，看谁读它，不看它在 schema 里出现过。这条恰好被旁边那个字段
替它把活干了，所以症状一直被掩盖。

## 四、三个待打勾的判断（工具答不了）

### ① 你认可 `governance/sixstate_report.md` 就是这条要的"报告"吗？

- **认可** → 六态区分能力现在有一份可复算的产物，继续看 ②。
- **不认可** → 请说清你要什么形态（一页表？按 Issue 组织？进看板？）。
  那这份报告只是草稿，`AUD-002-03` 不能签。

### ② `degraded` 零读取，算不算"AUD-002 验收标准里『证据过期触发降级』没被机器落实"？

- **不算** → 002-03 问的是"报告能不能区分六态"，报告现在能，并且把这件事写明了；
  缺口另立一条跟踪。**我倾向这个**，但这是判断不是事实。
- **算** → 那 002-03 应当评 `needs-work` 而不是 `approved`。
  一个能把结论翻过来的勾，值得你想清楚再打。

### ③ 你接受"六态只在规则层与控制层有意义、断言层用 `kind`"这个口径吗？

- **接受** → 报告里"六态不是全系统词汇表"那句就是结论的一部分。
- **不接受** → 需要先统一两层词汇（把 `excepted` 收成一处）。那是设计改动，
  不是复核能解决的，002-03 应挂起。

## 五、已知瑕疵（作者自曝）

1. **"未发现读取点"是低估计结论。** 正则扫不到"把 `state` 整个传给另一个函数"
   这种间接消费。所以它是"我没找到"，不是"不存在"。
2. **跨层归类有一条是按文件名判的**，不是语义分析：`closure.py` 里的 `excepted`
   一律算断言层（依据是那里的 `s` 来自 `self._assertion_state(a)`）。
   这个判据成立，但它是"读了一次源码后写死的规则"，不是每次都能自动推出来的。
3. **报告不判"六态模型设计得对不对"**，只报现状：哪些状态有值、谁在读写。
   模型该不该长这样，超出这条断言的范围。
4. **本材料不替你做结论。** 上面三个勾，勾完之后的处置路径都写了，但那只是
   "勾这个会走向哪里"，不是"我建议你勾这个"——②那个勾更是故意把反对答案放在
   前面，因为它有后果。

## 六、签了之后会发生什么

`AUD-002` 当前 `2/3 满足（人工待办 1）`。这条签成 `approved` 后 →
`3/3`，P0 Issue 达到 `machine_complete`。

**注意**：`machine_complete` 不等于"这件事做完了"。它表示"该验的都验了"，
而第 3 条事实（`degraded` 零读取）仍然是真缺口——它会在别的地方被跟踪，或者不被跟踪。
签字不会让它消失，只是让它不再挡着 002。

## 七、落账命令

```bash
# 0) 先确认执行主体不是签署人（防自签，record_signoff 会拒）
export GOV_ACTING_IDENTITY=agent-runner

# 1) 登记材料与结论（evidence/ 下的文件必须先存在）
python scripts/gov_run.py --accept-evidence \
  --path evidence/aud002_sixstate_review_<日期>.md \
  --by slow-is-fast --reason "AUD-002-03 六态区分能力复核"

# 2) 签署（--basis ≥10 字，写清看了什么、结论是什么、哪些不成立）
python scripts/record_signoff.py \
  --assertion-id AUD-002-03 \
  --reviewer slow-is-fast --role independent-reviewer \
  --verdict approved \
  --evidence evidence/aud002_sixstate_review_<日期>.md \
  --basis "<抽了哪几节、结论是什么、哪一条事实你认为不成立>"

# 3) 投影进矩阵（dry-run 先看）
python scripts/apply_signoffs.py --dry-run
python scripts/apply_signoffs.py --apply --by agent-runner

# 4) 矩阵变了 → 清单必须重生成（T-OWN-01 会红）
python scripts/export_owner_worklist.py
```

第 2 步的 `--basis` 是这条断言唯一的"人看过"的痕迹。写成"已复核"三个字，
等于这次复核没发生。
