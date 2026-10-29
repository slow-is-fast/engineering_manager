# AASEGS 试点阶段报告（2026-10-29）

**仓库**：slow-is-fast/engineering_manager（public）
**规范基线**：AASEGS v1.1.0 → v1.1.1（已于本报告批准日转正为正式生效，见 §8）
**报告性质**：PKG-01（试点证据包）首次履行。对照其八项要求逐项填写。
**读者**：Human Owner / Governance Owner——本报告是状态推进与版本转正的评审输入。

---

## 1 · 环境与版本

| 项 | 值 |
|---|---|
| 仓库 | public，分支保护已生效（required check strict + CODEOWNERS 1 审批 + 禁 force push/删除） |
| CI | `.github/workflows/governance.yml`（`governance / static-gate`），历次运行全绿 |
| 目录版本 | control-catalog **v1.1.1**（44 条控制）、rule-registry **v1.1.1**（52 条规则） |
| 审计基线 | AASEGS v1.1.0 审计问题清单 22 项 |
| 演练工具 | `scripts/validate_controls.py`、`tests/`（16 测试）、`tests/negative_static.py`、`executor/`（六组件） |

## 2 · 风险范围

按 00-总纲 F 的试点准入：本次全部活动限定 **R0/R1**（文档、脚本、演练注入），未执行任何 R2/R3 生产风险操作。演练注入全部发生在独立分支，已删除，main 无违规内容合入（每轮演练后均校验）。

## 3 · 控制状态快照

**44 条控制：tested 15 / not_enforced 29。**

| 类别 | 条目 | 状态 |
|---|---|---|
| 平台类（REG/QA 系） | REG-01、REG-02、AUD-01、QA-01、QA-02、QA-04 | tested 6 |
| 执行器类（WF/CNC/CTX/REC/EFF/BRK 系） | WF-01、WF-02、CNC-01、CTX-02、CTX-03、REC-01、REC-03、EFF-01、BRK-01 | tested 9 |
| 其余（身份、审计存储、事件响应、指标等） | 29 条 | not_enforced |

六态分布：tested 15、documented 29、verified **0**、configured 1（BASE-01 部分配置）。

**tested 与 verified 的边界**：tested = 控制逻辑在负向用例中按预期拒绝注入；verified 需要独立信任域部署（GOV-14 gap 适用）。执行器与被治理代码同仓库，其 9 条 tested 属"逻辑验证"。

## 4 · 测试结果汇总

| 轮次 | 对象 | 结果 | 关键结论 |
|---|---|---|---|
| 静态负向 | T-REG-01/02、T-AUD-01 | ✅ 4/4（含阴性对照） | 未注册条款被检出、伪造 verified 被拒 |
| Round 1 | T-QA-01/02（无分支保护） | ❌ **注入成功** | 检测层对"删测试/篡改 CI"原理性失明；防线只剩人 |
| Round 2 | T-QA-01/02（分支保护生效） | ✅ 注入被拒 | "PR 作者不能自批"是关键机制；CODEOWNERS 改写无效 |
| Round 3 | T-QA-04（SHA 绑定） | ✅ | 三 SHA 三结果（绿→红→绿），旧结果不可复用，门禁精确 |
| 执行器 | 10 条负向用例 | ✅ 10/10 | 六组件全部按预期拒绝注入；抓到空 manifest 误判 bug |

## 5 · 证据索引

| 类型 | 位置 |
|---|---|
| 静态负向证据 | `evidence/static_negative_*.json` |
| Round 1（失败案例） | `evidence/runtime_drill_20261029T144000Z.md`、PR #1（已关） |
| Round 2 | `evidence/runtime_drill2_20261029T150500Z.md`、PR #2 / PR #3 |
| Round 3 | `evidence/runtime_drill3_20261029T151500Z.md`、PR #4、CI run 40832319336 / 40832439900 / 40832571407 |
| 执行器 | `evidence/executor_20261029T154500Z.md`、CI run 40837846884 |
| 差异核对与修补 | `AASEGS_v1.1_会话与本地文件差异核对报告.md`（第八节修补记录） |

每条 tested 控制的 `integration_evidence_uri` 均指向可核查的 PR 或 CI run。

## 6 · 失败与例外

如实登记，无粉饰：

1. **Round 1 注入成功**（T-QA-01/02）：根因 INFRA-01（免费私有仓库无分支保护）。已通过转公开解除，但该案例保留了完整记录——它是"检测层≠强制层"的实证。
2. **INFRA-01**：已解除（public + 分支保护）。教训：平台层强制是有真实成本的（付费或公开）。
3. **handoff 空 manifest 误判 bug**：`not value` vs `value is None`，由正向对照用例发现并修复。
4. **6 条规则无运行时控制**（GOV-08 原则性条款除外为 5 条）：GOV-14（信任域分离）、AGT-005、WFL-001/002、SUP-005，均有 gap 说明，待控制化决策。
5. **22 项审计问题 0 关闭**：tested ≠ closed；关闭需满足各自 closure_criteria 并经独立复核。
6. **未覆盖**：T-ID 系列（需身份服务）、T-QA-03（需第二凭证）、WFL-003 实测（Owner 凭证下 force push 不受限）、全部 R2/R3 演练。

## 7 · 复验要求

以下结论依赖当前配置，复验时必须重查：

- 分支保护配置未回退（`gh api repos/.../branches/main/protection`）
- `governance / static-gate` 仍为必需检查且 workflow 未被篡改
- 执行器测试在 CI 中持续通过
- 仓库保持 public（或升级 Pro 后等效配置）

## 8 · 批准结论（Owner 已于 2026-10-29 批准）

批准人：**slow-is-fast**（2026-10-29）

- [x] **确认试点范围与证据充分性**——批准。R0/R1 层 5 条运行时用例有结论（含 Round 1 失败案例），证据链 PR/CI 可核查。
- [x] **指派 22 项审计问题的 owner**——指派 **slow-is-fast**，全部 OPEN；分配记录见 `AASEGS_Audit_Issues_Full.md` §二·A。
- [x] **决策 5 条 gap 规则的控制化优先级**——批准按以下顺序推进：① GOV-14（新增 VD-01 信任域分离，verified 的前提）→ ② SUP-005（并入 identity attestation，随 WP-02）→ ③ WFL-001/002（执行器 handoff 准入检查承担，成本最低）→ ④ AGT-005（文档审查流程化，最低）。决策已写入 `rule-registry.json` 各规则的 `gap_uplift` 字段。
- [x] **v1.1.1 转正**——批准。从「实施完整性修订候选」转为**正式生效**，转正记录见规范头部。关闭门槛不变：未关闭 P0 仍阻止对应风险等级准入。
- [x] **批准下一批试点**——批准，范围与优先级：① 执行器独立信任域部署（解锁 GOV-14 gap 与 verified 授予）→ ② T-ID 系列 / T-QA-03（需身份服务与第二凭证）→ ③ WFL-001/002 准入检查扩展（基于现有 handoff 契约）。

## 9 · 对五步计划的定位

| 计划步骤 | 状态 |
|---|---|
| 一、规则注册表 | ✅ 完成（52 条） |
| 二、控制映射与测试矩阵 | ✅ 完成（44 控制 ↔ 44 用例，15 tested） |
| 三、落实 P0 控制 | ✅ 完成（CI + 分支保护 + 执行器；P0 控制 13 条中 8 条 tested） |
| 四、真实仓库试点 | 🟨 **进行中**（R0/R1 层 5 条运行时用例有结论，含失败案例；身份/审计存储类未动） |
| 五、按试点结果修订 | ⬜ 未开始（注意：现有 v1.1.1 是审计驱动修订；试点驱动的修订应为 v1.1.2/v1.2） |
