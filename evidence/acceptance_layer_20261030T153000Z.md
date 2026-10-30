# 闭合流程第二层：§四 验收断言矩阵（2026-10-30T15:30+08:00）

**CI 追溯**：数据面 run `40995681783`（79 tests OK；T-VD-01 PASS：pin=23579c99fad1 tree=27611bf5a872 content=20278d9128a7；T-RVF-01 fresh 38/0/0/0；T-CLOSE 步骤输出 `80 条 | 满足 46 | 未满足 34（人工待办 21）| 断言全通过 0/22`，`--acceptance` 明细已进日志）；控制面 run `40995599379`（64 用例 OK，含 2 个验收层用例）。

**背景**：闭合评估原先只判"应答控制是否 tested"，`closure.py` 的文档字符串自己写着"不读 §四 验收标准原文，不能替代逐条验收"。这条局限意味着 18 项 `READY_FOR_REVIEW` 头上悬着一段真空——**"可评审"里到底有多少内容，没人答得上来**。本轮把 §四 原文拆成可判定断言，填上这一层。

## 一、新增事实源

`governance/acceptance_matrix.json`：22 个问题、**80 条断言**，每条来自 §四「验收标准」与「关闭条件」原文。

| 断言类型 | 含义 | 机器如何判定 |
|---|---|---|
| `test` | 映射到具体用例方法 | 在 `tests/*.py` 中查找 `def <ref>(`；**不存在即不满足**（幽灵用例无法冒充） |
| `script` | 跑仓库内既有校验器 | 子进程执行，退出码 0 才算满足；含递归守卫（禁止调用闭合评估自身） |
| `evidence` | 证据文件 | 必须存在**且包含指定字符串**（防占位文件顶替） |
| `manual` | 须人工/独立环境执行 | 没有 `signoff`（by+ref+date）一律 `manual_pending` |
| `unimplemented` | 当前无任何机器覆盖 | **显式记账为不满足**，既不假装通过，也不假装"人工已验证" |

## 二、判定语义（失败关闭）

- 问题未出现在矩阵 → `acceptance_unmapped`，**不得**据此宣称验收完成；
- 未知断言类型（如 `vibes_check`）→ `unknown_assertion_kind`，不默认放过；
- 矩阵文件缺失 → `acceptance_matrix_missing`，同样阻断关闭；
- **新增违规 `closure_without_acceptance`**：声明 `CLOSED`/`ACCEPTED_RISK` 但仍有未满足断言或未签署的人工项 → 与 `unbacked_closure` 同属记账不实，`--enforce` 非零退出。

### 关键设计：验收层不改变"可进入评审"的结论

`machine_ready`（控制级证据）与 `acceptance.machine_complete`（§四 断言）是**两个不同维度**，分别输出。用例 `T-CLOSE/acceptance_blocks_unbacked_close` 显式断言：即使验收断言全未实现，`machine_ready` 仍为真、`suggested` 仍为 `READY_FOR_REVIEW`——分层是为了看清缺口，不是为了把两个概念混成一个。

## 三、首次运行结果（诚实读数）

```
问题 22 项 | 控制级证据齐备 18 | 可进入评审 18 | 已声明关闭 0 | 违规 0
§四 验收断言：80 条 | 满足 46 | 未满足 34（其中人工待办 21）| 断言全通过的问题 0/22
```

| 分类 | 数量 | 说明 |
|---|---:|---|
| 已满足 | 46 | 有对应用例 / 校验脚本通过 / 证据文件命中 |
| 人工待办 | 21 | 隔离环境演练、独立复核、Security Owner 批准、真实仓库证据包等 |
| 显式未实现 | 13 | 如 SMT-01 状态机跳转、MTR-01 指标、四类隔离演练 |
| **断言全通过的问题** | **0 / 22** | 这是最重要的一行：**没有任何一个问题真正满足了 §四 全部验收标准** |

这条结论与"0 项 CLOSED"一致，但它给出了**为什么**——不是流程没走，而是每条都差在具体的地方，且这些地方被逐条点名，不再是一句笼统的"待复核"。

## 四、用例覆盖（T-CLOSE 第二层，新增 2 个）

| 用例 | 断言 |
|---|---|
| `test_t_closure_acceptance_blocks_unbacked_close` | 未实现断言 + 声明 CLOSED → 违规且 `blocking` 精确到断言 ID；矩阵缺失 → `acceptance_matrix_missing`；问题未分解 → `acceptance_unmapped`；同时验证 `machine_ready` 不受验收层影响 |
| `test_t_closure_acceptance_manual_signoff_and_unknown_kind` | 人工项无签署 → pending 且阻断关闭；登记 `signoff` 后 → 无违规；未知类型 → `unknown_assertion_kind`；指向不存在用例 → `missing_test_ref` |

夹具同时构造了 `tests/test_fixture.py`，使 `test` 类断言的"存在性检查"真的走了一遍查找逻辑，而不是恒真。

## 五、CLI 输出（CI 可直接读）

```
§四 验收断言：80 条 | 满足 46 | 未满足 34（其中人工待办 21）| 断言全通过的问题 0/22
```

`--acceptance` 逐条列出 `[OK]/[MISS]` 与未满足原因；`--no-scripts` 只评估 test/evidence/manual（本地快速模式，输出会标注"脚本未执行"，不冒充全量结果）。

## 诚实边界

- `kind=test` 只证明"该用例存在且随 CI 套件执行过"，**不证明它覆盖了条款的全部边界情形**——分解的粒度与映射的准确性仍需独立复核；
- `manual` 的 `signoff` 是自述式记录，机器只能检查字段齐全，**无法校验签署人的独立性**（EXC-01 不可达时这是硬限制）；
- 本矩阵是人工分解的产物，**分解本身的完备性**同样是一个需要评审的对象，不能自证；
- `script` 类断言复用既有校验器，其判据强度不超过被复用脚本本身的强度（检测层 ≠ 强制层）。
