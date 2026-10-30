# 控制↔规则双向闭合、四条未实现断言落地与 REC-02 定级（2026-10-30T18:30+08:00）

**CI 追溯**：本地全量复跑读数见 §五。CI run 编号由随后一次提交补记——本仓惯例是不把未核实的 run 号写进证据。

**代码**：控制面 `61fed88…`（`ledger` / `breaker` / `change` / `toolgate` 扩展 + 新增 `retrypolicy.py`），数据面同步并 bump `executor_pin.json`（`61fed8806d9f` / tree `e3f64d5469f1` / content `7f3f0b4b2b5d`，T-VD-01 已对照 GitHub 校验通过）。

---

## 一、双向闭合：14 条"凭空存在"的控制

上一轮收盘时记录了一个缺口：覆盖检查只做**规则 → 是否有控制**，没做**控制 → 是否被某条规则要求**。结果 14 条控制不被任何规则引用，却都以 `tested` 状态出现在目录里。这类控制的特征是"看起来治理很完整，实际上没有任何规范条款要求它"——和控制缺失一样危险，因为审阅者会把它当作已覆盖的保证。

### 1.1 补规则引用（6 条，7 处）

| 控制 | 挂到规则 | 规则条款 | 吻合点 |
|---|---|---|---|
| `CTX-02` | `AASEGS-AGT-007`（P1） | 晋升为跨任务共享记忆必须进行来源校验与授权审核 | 控制证据是"签名晋升记录"，失败动作是"拒绝共享晋升" |
| `CTX-03` | `AASEGS-AGT-008`（P1） | 共享记忆存储必须可撤销、可检索版本历史 | 控制证据是"墓碑与检索日志"，失败动作是"过滤并挂起" |
| `WF-01` | `AASEGS-WFL-004`（P1） | 任务所有权变更必须 CAS/version 校验 | "交接接受事件"就是所有权变更的落点 |
| `WF-02` | `AASEGS-WFL-004`（P1） | 同上 | "租约 + base SHA"就是 CAS 的实现手段 |
| `WF-03` | `AASEGS-WFL-006`（P0） | 生产数据库破坏性变更不得被默认自动重试 | "唯一操作回执"是重复投递不得二次执行的前提 |
| `REC-04` | `AASEGS-WFL-007`（P1） | 必须区分 STOPPED/COMPENSATING/COMPENSATED/MANUAL_REMEDIATION_REQUIRED | "补偿计划审批"正是进入 COMPENSATING 的门 |

### 1.2 登记处置（8 条）

允许控制存在，但必须写清"为什么没有条款要求它"。两类处置：

| 控制 | 类型 | 依据 | 理由 |
|---|---|---|---|
| `REG-02` | `audit_driven` | AUD-002 | 六态状态服务：审计要求可区分六态，规范正文只有散文，无独立编号 MUST |
| `ISO-01` | `audit_driven` | AUD-016 | 跨项目隔离边界：审计修补要求，规范散落在 §4，未单独编号 |
| `SMT-01` | `audit_driven` | AUD-007 | 状态转换矩阵：审计要求机器可读，§5 只描述状态含义 |
| `BRK-01` | `audit_driven` | AUD-011 | 熔断器：§7 提到熔断但没给可判定阈值语义 |
| `RVF-01` | `audit_driven` | AUD-022 | 证据新鲜度：规范只写"持续复验"，未规定 TTL 与失败关闭 |
| `REC-01` | `defense_in_depth` | 派生自 `WFL-005` | 检查点完整性（签名 + base SHA）是 CKP-01 的底座，**不回答**"敏感数据不得写入快照" |
| `REC-03` | `defense_in_depth` | 派生自 `WFL-006` | 熔断是"破坏性变更不得默认重试"的实现手段，规范无独立熔断 MUST |
| `AUD-03` | `defense_in_depth` | 派生自 `SEC-008` | append-only 审计存储是 EVD-01/02（P0，已 tested）的底座，P0 义务由 EVD 承担 |

处置登记不是免责声明，是**事实披露**：把一条控制标成 `defense_in_depth`，等于承认"规范没有强制要求它"。

### 1.3 校验器从"单向"改成"双向"

`scripts/validate_controls.py` 新增四条断言（任一不满足即失败关闭）：

1. 每条控制必须有 `risk_level`（此前**不服务任何规则**的控制可以空着等级，因为旧断言只检查"服务规则的控制"）；
2. 不被任何规则引用的控制必须在 `control_coverage.json` 登记；
3. 登记项必须是 `audit_driven`（带 `issue`）或 `defense_in_depth`（带 `derived_from`，且规则必须真实存在）；
4. **反向过期检查**：一旦某条控制重新被规则引用，它的处置登记必须删掉——否则会出现"规则已覆盖 + 登记还在"的双重记账。

配套两条负向用例：`T_REG_03`（摘掉某控制唯一引用 → 必须报孤儿）、`T_REG_04`（摘掉 `risk_level` → 必须报缺等级）。

### 1.4 本轮自查揪出的两处我自己挂错的引用

写证据时逐条比对"控制证据语义 vs 规则条款"，发现上一轮补引用时有两处不成立，已在本轮修正：

- **`CTX-02` / `CTX-03` 挂反了。** `CTX-02` 的证据是"签名晋升记录"、失败动作是"拒绝共享晋升"，对应的是 **promotion**，该挂 `AGT-007`；`CTX-03` 是"墓碑与检索日志"，对应 **tombstone**，该挂 `AGT-008`。上一轮按编号顺序配对，正好反了。现已互换。
- **`REC-01` 挂在 `WFL-005` 不成立。** `WFL-005` 要求"敏感数据不得直接写入普通快照"，而 `REC-01` 保证的是检查点**完整性**（签名 + base SHA），管的是"有没有被篡改"，不是"里面有没有敏感数据"。这是拿相邻的控制凑覆盖。已从 `WFL-005` 摘除（该条仍由 `CKP-01` 应答），改登记为 `defense_in_depth`，并在理由里写明它不回答什么。

这两处都不是工具能发现的——校验器只查"有没有引用"，查不出"引用对不对"。**结构闭合 ≠ 语义闭合**，这一点记在这里。

---

## 二、四条 `unimplemented` 断言落地

§四 验收矩阵里有 10 条断言长期以 `unimplemented` 记账（"要求写了，但没有对应实现"）。本轮挑单机可做的四条做掉。

| 断言 | 条款 | 缺陷是什么 | 实现 | 用例 |
|---|---|---|---|---|
| `AUD-008-04` | 未接收超时 → UNKNOWN，须核对 | 账本只会把操作停在 `SUBMITTED`，没人扫超时；停在 `SUBMITTED` 既不等于成功也不等于失败，调用方容易当成功继续走 | `ledger.declare_dispatched(key, deadline)` + `sweep_timeouts(now)`：到期未回执置 `UNKNOWN` 并返回超时清单，调用方**必须逐条核对** | `test_t_eff_02_receipt_timeout_requires_reconcile` |
| `AUD-011-03` | 事件乱序：旧事件被忽略且不重复计数 | 熔断器按到达顺序累加，一条重放的失败事件会把阈值提前打满，一条迟到的"普通事件"又能把刚打开的熔断器搅乱 | `breaker.apply_event(seq, …)`：`seq ≤ last_seq` 一律 `IGNORED`，落 `breaker.event_reordered`，不推动状态 | `test_t_brk_02_out_of_order_events_ignored` |
| `AUD-017-03` | 模型升级/回滚：证据须绑定目标版本 | 证据按模型名索引，上一个版本的评测结果可以直接给新版本背书——"模型换了，评估没换" | `change.ModelReleaseEvaluator`：证据键改为 `(model, version)` 二元组，跨版本复用取不到；`rollback` 必须带可核查 `plan_ref` | `test_t_chg_02_model_upgrade_and_rollback_bound_to_version` |
| `AUD-022-03` | 工具升级使旧证据失效并降级 | 工具升级后旧版本的能力矩阵仍然有效，等于升级完还能按旧版本放行 | `toolgate.upgrade(tool, new_version, capabilities)`：旧版本标 `superseded_by`，`max_admissible_risk` 对 superseded 版本返回 `None` | `test_t_tool_02_upgrade_supersedes_evidence` |

`unimplemented` 从 10 条降到 **6 条**（`AUD-009-03`、`AUD-010-03`、`AUD-013-03`、`AUD-014-03`、`AUD-015-03`、`AUD-016-03`）。剩下的都在"真实远端/隔离环境/真实保留周期"上，单机造不出来，继续按 `unimplemented` 记账比假装做完诚实。

---

## 三、REC-02 定级与覆盖口径

`REC-02`（`retry_controller`）此前状态是 `not_enforced`、无 `risk_level`、无规则引用——它不是"没实现"，是"没人认领"。它服务的是 `AASEGS-WFL-006`（**P0**，MUST NOT：生产数据库破坏性变更不得被默认自动重试），所以等级必须是 P0。

### 3.1 `retrypolicy.py` 的强制语义

失败关闭，且**默认值站在拒绝一侧**：

| 情形 | 判定 |
|---|---|
| 操作在 `DESTRUCTIVE_OPERATIONS`（drop/truncate/delete_rows/migrate_down/purge…） | 破坏性 |
| 操作在 `SAFE_OPERATIONS` 白名单（read_config/apply_index/reconcile/refresh_cache） | 非破坏性，限 3 次 |
| **操作不在两张表里（未知）** | **按破坏性处理**——没听说过 ≠ 安全 |
| 破坏性 + 无审批 | 拒（`destructive_not_auto_retryable`） |
| 破坏性 + 审批人名字像 Agent（`agent-`/`run-`/`bot-`/`copilot`…） | 拒（`reauthz_by_agent`） |
| 破坏性 + 审批无 `scope_ref` 或不可核查 | 拒（`reauthz_without_scope_ref`） |
| 破坏性 + 审批操作与本次操作不符 | 拒（`reauthz_scope_mismatch`） |
| 破坏性 + 无 `state_check` 或结果不是 `confirmed_no_effect` | 拒——**没核对过的"重试"就是盲目重放** |

每次决策（允许和拒绝）都落审计，含操作、尝试序号、破坏性判定与依据。

### 3.2 覆盖口径

`REC-02` 已挂到 `AASEGS-WFL-006` 的 `enforcement.controls`（与该规则原有的 `EFF-01`、`WF-03` 并列），置 `tested`、`risk_level=P0`。这样它既不是孤儿，也不靠处置登记"豁免"。

---

## 四、账本变化

| 指标 | 前 | 后 |
|---|---:|---:|
| 控制 tested | 42 | **44 / 49** |
| 控制 verified | 0 | 0 |
| `risk_level` 缺失的控制 | 0（上一轮补齐） | 0（新增断言守住） |
| 被规则引用不到的控制 | 14 | **8**，且 8 条全部有处置登记 |
| P0 控制未 tested | 2 | **2**（`QA-03`、`RVW-01`，均持 EXC-01） |
| §四 验收断言 | 90 | 90 |
| 断言满足 | 59 | **63** |
| 显式 `unimplemented` | 10 | **6** |
| 断言全通过的问题 | 0 / 22 | **1 / 22** |
| 控制面用例 | 83 | **88** |
| 数据面总测试 | 98 | **103** |
| GATE-01 阻断项 | 10 | **10**（等级 G1） |

**阻断项仍是 10、等级仍是 G1，这是正确结果。** 10 个阻断项全部是 P0 审计问题停在 `READY_FOR_REVIEW`——`READY_FOR_REVIEW` 在 `OPEN_STATES` 内仍计阻断。控制补齐、断言落地都没有让门槛松动一格。

---

## 五、本地复跑与变异检验

### 5.1 全量读数（2026-10-30T18:30+08:00，本地）

```
控制面  python -m unittest tests.test_executor_negative         → Ran 88 tests ... OK
数据面  python -m unittest discover -s tests -p "test_*.py"     → Ran 103 tests ... OK
数据面  python tests/negative_static.py                         → RESULT: ALL PASSED（6 项）
数据面  python scripts/validate_controls.py                     → PASS: 49 控制 / 27 P0 / 53 规则
数据面  python scripts/verify_executor_pin.py                   → PASS(T-VD-01): 61fed8806d9f tree=e3f64d5469f1 content=7f3f0b4b2b5d
数据面  python scripts/check_admission_gate.py                  → G1，G2 阻断 10（open_issue × 10）
数据面  python scripts/check_audit_closure.py                   → 22 可评审 / 0 违规 / 断言 90 条满足 63
```

### 5.2 变异检验：五条新语义逐个拆掉，看用例是否真的抓得住

| 变异 | 结果 |
|---|---|
| `retrypolicy.is_destructive`：未知操作改为 `return False`（失败开放） | **CAUGHT** `test_t_rec_02` 转红 |
| `breaker.apply_event`：去掉 `seq <= last` 守卫（乱序重复计数） | **CAUGHT** `test_t_brk_02` 转红 |
| `ledger.sweep_timeouts`：超时只报不改（不置 `UNKNOWN`） | **CAUGHT** `test_t_eff_02` 转红 |
| `change`：证据改回按 `model` 索引（跨版本复用） | **CAUGHT** `test_t_chg_02` 转红 |
| `toolgate.upgrade`：不标记 `superseded_by` | **CAUGHT** `test_t_tool_02` 转红 |

五条全红，逐条还原后基线复跑仍 `Ran 88 tests ... OK`，工作区干净。

---

## 六、诚实边界

- **`tested` 是逻辑验证，不是 `verified`。** 本轮新增的 5 条语义都在单进程内存/文件状态上验证，没有独立主机、独立账号的第二信任域证据；`verified` 仍为 **0**，R3 不可达，受 `EXC-02`（到期 2027-04-30）。
- **双向闭合只保证"有引用关系"，不保证"引用正确"。** §1.4 那两处挂反/挂偏，校验器一条都没报——它查的是引用存在性。语义对不对，只能靠人逐条比对，这也正是本轮要做这件事的原因。
- **`retrypolicy` 不判断操作是否真的落在生产库上。** 它只决定"能不能重试"，操作分类是调用方传进来的；分类错了，策略拦不住。
- **`ModelReleaseEvaluator` 只保证"证据键绑到了目标版本"**，不保证证据本身是真的、也不保证评测集没变。
- **`toolgate` 的 superseded 只影响本清单内的放行判定**，不撤销已经签发出去的租约。
- **6 条 `unimplemented` 断言仍会挡住对应问题的"验收通过"**，`AUD-009/010/013/014/015/016` 六项在 §四 层面仍未满足。
- **21 条 `manual_pending`** 需要隔离环境演练、真实仓库证据包、Security Owner 签署与独立复核，仍受 `EXC-01`。
