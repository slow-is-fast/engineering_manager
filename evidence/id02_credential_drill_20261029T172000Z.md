# 凭证域与主体独立性演练（2026-10-29T17:20+08:00）

**对象**：用户提供的 fine-grained PAT（下称 agent token），仅用于本次演练，未写入任何文件/提交/日志。
**用例**：T-VD-01b（凭证域）、T-ID-02（最小权限租约）、T-QA-03（Reviewer 独立性）

## 1 · 探测结果

| 项 | 结果 |
|---|---|
| 身份 | `slow-is-fast`（User） |
| 仓库 API 返回的 permissions | 两个仓库都显示 `push/admin: true`——**该字段对 fine-grained token 不可信**，必须以实测为准 |
| 数据面写（创建/删除分支） | ✅ 成功（正向对照：凭证在其域内可用） |
| 控制面写（创建 label） | ❌ **403 `Resource not accessible by personal access token`** |

**结论 1（T-VD-01b / T-ID-02）**：agent 凭证的**凭证域分离已实证**——数据面可写、控制面被拒。这是 ID-02「最小权限/任务限域租约」的首条运行时证据。

**注意事项**：GitHub 仓库 API 的 `permissions` 对象会返回用户级权限，不能用来判断 fine-grained token 的实际作用域；**必须做一次真实写尝试**才能判定（本演练即按此设计）。

**诚实边界**：
- 该 token 签发自人类账号，不是 IdP 签发的 Agent 身份（AGT-003 要求的"可信 Identity Broker 签发"仍未满足）；
- 有效期（宣称 30 天）无法经 API 机器校验——租约短期性仍是**声明**而非证据。
- 因此 ID-02 记为 `tested`（作用域分域成立），不记为 `verified`。

## 2 · T-QA-03：第二凭证 ≠ 第二主体

用 agent token 创建 PR #5，再分别用 Owner 凭证与 agent token 审批：

| 审批凭证 | 结果 |
|---|---|
| Owner 凭证（gh 默认登录） | ❌ `Review Can not approve your own pull request` |
| agent token（同一 PR 的创建者） | ❌ 同一错误 |

**结论 2**：两个 token 同属 GitHub 用户 `slow-is-fast`，平台按**主体**而非**凭证**判定审批独立性。因此：

- **T-QA-03（Reviewer 独立性）不能靠第二个 PAT 覆盖**；
- 唯一路径是**第二个人类主体**（独立 GitHub 账号）或组织级 Reviewer 角色/App 身份；
- 在此之前，QA-03 / RVW-01 保持 `not_enforced`，不得凭"有两个 token"宣称独立验收。

**附带正面发现**：平台层（GitHub）对"自批"的拒绝是**服务器端强制**，与本仓库的检测层无关——再次印证"检测层≠强制层"。

## 3 · 清理与卫生

- PR #5 已关闭（未合入），分支 `drill/t-qa-03` 已删除，数据面 open PR 数为 0。
- token 仅出现在本次会话，**未写入仓库、脚本、证据或日志**；建议用后**立即轮换**（已在对话中暴露）。
