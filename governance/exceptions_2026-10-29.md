# 治理例外登记（ACCEPTED_RISK）· 2026-10-29

**批准人**：slow-is-fast（Owner）
**场景约束**：本仓库为**单人开发者 + 多个 Agent**。`ACCEPTED_RISK` 不等于修复完成——按《审计问题清单》§2，必须记录批准人、范围、补偿控制、到期时间和撤销条件。

---

## EXC-01 · 缺少第二人类审批主体（QA-03 / RVW-01）

**范围**：本仓库单人开发场景下的"独立人工验收/审批"。
**实证依据**：PR #5 演练——第二 PAT 不构成独立主体，Owner 凭证与 agent token 审批均被 `Can not approve your own pull request` 拒绝。平台按**主体**而非**凭证**判定独立性。

**补偿控制（多 Agent 适配）**：

1. **评审与写入分凭证**：评审 Agent 使用**只读凭证**（Fine-grained PAT，Repository permissions: Contents = **Read-only**、Pull requests = Read and write 用于留评论），写入 Agent 另用一把限域可写凭证。**两者不得共用同一把 token**。
2. **机器化校验**：`scripts/verify_reviewer_credential.py --expect-deny`——评审凭证若具备写权限即失败关闭（已用当前可写 agent token 反向验证：正确判定不合格并清理探测分支）。
3. **评审证据绑定**：评审结论须含评审者身份、会话 ID、被评审 diff 的 SHA（QA-04 / CKP-01 已提供绑定能力）。
4. **平台层兜底**：自批由 GitHub 服务器端拒绝（已实证，非本仓库检测层行为）。
5. **人类最终责任不变**：merge 动作始终由人类 Owner 执行（GOV-06）。

**状态**：`RVW-02（评审凭证只读）`为**候选控制**，未登记进 `control-catalog.yaml`——因为它尚无 tested 证据（缺少只读 PAT 的实测）。创建只读 PAT 后跑通即登记，届时 EXC-01 的补偿控制 1/2 由"声明"升级为"证据"。

**到期**：2027-01-31。
**撤销条件**（满足任一即撤销本例外）：引入第二人类主体；或组织级 App/Reviewer 身份启用；或 RVW-02 完成登记并通过连续 CI 校验。

---

## EXC-02 · verified 授予所需的独立账号/主机不可达

**范围**：控制 VD-01、规则 GOV-14 的 `verified` 状态授予；执行器类 9 条控制与 VD-01/ATT-01 的 verified 推进。
**现状**：控制面与数据面同属 GitHub 账号 `slow-is-fast`；无第二个账号或独立主机。

**补偿控制（已实施）**：

1. **控制面独立仓库** `slow-is-fast/aasegs-gov-plane` + 分支保护 + CODEOWNERS（已生效）。
2. **SHA pin**：数据面 `governance/executor_pin.json` 绑定控制面不可变 commit（SHA + tree + 内容哈希三重），T-VD-01 每次 CI 校验，篡改即失败关闭。
3. **运行时凭证分域**：数据面 CI 的 `github.token` 写控制面被 403 拒（T-VD-01b，连续 CI 证明）。
4. **Agent 凭证限域**：Agent 使用限域单仓的短期 fine-grained PAT（T-ID-02 已实测：数据面可写、控制面被拒）。
5. **执行器源码只读引用**：数据面不得直接改 `executor/`；变更须走控制面 PR + pin bump（首次 bump 已实跑）。

**诚实声明**：以上把"信任域分离"做到了**仓库级 + 凭证级**，但**不是账号级/主机级**。因此 VD-01、9 条执行器类控制、ATT-01 保持 `tested`，**verified 仍为 0**——不因补偿控制而提前宣称 verified。

**到期**：2027-04-30。
**撤销条件**：具备独立 org/账号，或执行器部署到独立主机/容器（具备独立凭证与只读挂载）后完成部署验收。

---

## 多 Agent 适配补充约定（非例外，属操作规范）

- 每个 Agent **一把独立 token**，禁止共享人类个人 token（AGT-002）；
- token **限域单仓 + 短期**（到期即轮换；本次演练用 token 已建议轮换）；
- **只读 Agent**（评审/审计）与**写入 Agent**（实现）严格分凭证；
- Agent 不得把 token 写入仓库、脚本或日志（本次演练全程以环境变量传入，未落盘）。
