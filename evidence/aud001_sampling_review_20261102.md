# AUD-001-03 人工抽样复核记录（2026-11-02）

> **签署主体**：slow-is-fast（Owner，human）
> **录入方**：agent-runner（Agent，执行 `record_signoff`/`apply_signoffs` 的那方；与签署人不同名，
> 铁律④的分工是「判断归人、录入归 Agent」——本文件如实记录谁说了什么）
> **复核材料**：`governance/coverage_pack_aud001.md`（指纹 `06c321130573`，
> `python scripts/export_coverage_pack.py --check` 可验证材料未过期）

## 一、复核了什么

1. **覆盖率报告**（coverage_pack §1）：规则→控制 58/59；规则→用例（字符串）53/59 vs
   **可解析 45/59** 两个口径分开陈述；控制→用例可解析 50/55。
2. **差异报告**（§2）：规则无运行时控制 1 条（GOV-08）；孤儿控制 8 条；
   **悬空用例引用 10 处**（T-ID-02 / T-QA-03 / T-RVW-01 / T-QA-05 / T-AUD-02，
   涉 8 条规则，其中 AASEGS-AGT-001/002 为 P0；规则侧 `verification.tests` 此前无任何检查器覆盖）。
3. **抽样清单**（§3）：全部规则按 `sha256(rule_id)` 升序取前 10 条，逐条给出
   规则原文、控制证据、用例源码片段与三个待勾判断。

## 二、抽样 10 条与已知瑕疵（Owner 在答复前已看到本表的事实列）

| # | 规则 | 控制 | 用例 | 事实 |
|---|---|---|---|---|
| 1 | GOV-08（P1） | **无** | **无** | 唯一未声明运行时控制的规则 |
| 2 | AASEGS-SEC-002（P1） | RVW-01 | `T-RVW-01` | **悬空**（方法不存在） |
| 3 | AASEGS-AGT-003（P0） | ID-01 | `T-ID-01` | 用例真实（test_executor_negative.py:1535） |
| 4 | GOV-18（P1） | GATE-01 | `T-GATE-01` | — |
| 5 | AASEGS-SUP-006（P0） | INC-01 | `T-INC-01` | — |
| 6 | AASEGS-AGT-008（P1） | MEM-01＋CTX-03 | `T-MEM-01` | 两条控制共用一条用例 |
| 7 | AASEGS-AGT-005（P1） | CLM-01 | **无** | 只有控制、无用例 |
| 8 | AASEGS-SEC-001（P0） | QA-02 | `T-QA-02` | — |
| 9 | AASEGS-SEC-009（P0） | APR-01 | `T-APR-01` | — |
| 10 | GOV-06（P1） | APR-01 | `T-APR-01` | 与 #9 同控制同用例 |

## 三、Owner 结论（会话原话，未改动）

> 问：① 10 条的勾选结论；② EXC-03 批准与否。
> 答：**「1 没问题 2 算EXC-03通过了」**（2026-11-02）

即：Owner 在看到上表事实列（含 3 条明显瑕疵）后，确认抽样复核通过。
EXC-03 的批准单独落账（见 `quality_baseline.json` `change_approvals[0]`，type=exception_added）。

## 四、本记录明确接受并另行跟踪的瑕疵（不因 approved 而消失）

1. **10 处规则侧悬空 `verification.tests`**：均为 `tested=false` 规则的登记瑕疵
   （规则从未声称被测过），但字段里写着不存在的编号。整改是治理决定（删引用或补用例），
   **另立工作项跟踪，不在本签署范围内**。
2. **GOV-08 无运行时控制**：`validate_controls` 已知并放行（"59 rules, 1 without runtime control"），
   属已登记的覆盖缺口。
3. **8 条孤儿控制**：有 tested 状态但无规则引用，语义映射待 Owner 拍板。

## 五、边界

- 本记录 + 签署只针对 **AUD-001-03 一条断言**（人工抽样复核记录的存在性与质量），
  不关闭 AUD-001 的其他断言，不制造任何 verified，不改变例外状态。
- `apply_signoffs` 会重算 `signature`（sha256 完整性校验）；签署后任何人改本文件的
  哈希都会让校验红。
