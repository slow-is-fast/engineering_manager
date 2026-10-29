# GATE_SETUP · 分支保护与必需检查配置指南

本指南对应 AASEGS v1.1.1 的 BASE-01（受保护质量基线）、QA-01（受保护合并绑定可信检查）、QA-02（治理文件修改触发独立审核）。以下配置在 GitHub 仓库的**服务器端**生效，是本地无法模拟的部分，也是 T-QA-01 / T-QA-02 / T-AUD-03 等负向用例的前提。

## 一、分支保护（Settings → Branches → Add branch protection rule）

对 `main` 分支：

| 设置 | 值 | 对应控制 |
|---|---|---|
| Require a pull request before merging | 开启， approvals = 1 | QA-03 / RVW-01 |
| Require review from Code Owners | 开启 | QA-02 |
| Require status checks to pass | 开启，必需检查勾选 `governance / static-gate` | QA-01 / QA-04 |
| Require branches to be up to date | 开启 | QA-01（绑定最新 SHA） |
| Do not allow force pushes | 开启 | WFL-003（禁止 --force） |
| Do not allow deletions | 开启 | EVD-01 |
| Restrict who can push to matching branches | 仅 Owner | GOV-07（禁止自改规则） |

命令行等价（需要 admin 权限的 token）：

```bash
gh api -X PUT repos/slow-is-fast/engineering_manager/branches/main/protection \
  -f required_status_checks.strict=true \
  -f 'required_status_checks.contexts[]=governance / static-gate' \
  -F enforce_admins=false \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F required_pull_request_reviews.require_code_owner_reviews=true \
  -F restrictions=null \
  -F allow_force_pushes=false \
  -F allow_deletions=false
```

> 注意：`enforce_admins` 若设为 true，Owner 自己也会被拦。试点阶段建议先 false，熟悉流程后收紧。

## 二、必需检查的生效前提

`governance / static-gate` 这个检查名来自 `.github/workflows/governance.yml` 的 `jobs.static-gate`。**必须先有一次成功运行记录**，分支保护里才能勾选它。顺序：

1. 推送本仓库到 GitHub
2. 等 Actions 跑完第一次 `governance` workflow
3. 再回到 Branch protection 勾选该检查

## 三、验证配置是否生效（试点演练）

配置完成后，以下注入应当被服务器端拒绝：

| 注入 | 预期 |
|---|---|
| 直接 push 到 main（绕过 PR） | rejected（require PR） |
| PR 中把 `validate_controls.py` 改成 `sys.exit(0)` | CI 状态检查失败，无法合并 |
| PR 修改 `control-catalog.yaml` 且无 Owner 审批 | merge blocked（CODEOWNERS） |
| force push main | rejected |
| 删除旧检查结果后重用旧 SHA 的结论 | 不可能：check 绑定 commit SHA |

以上即 T-QA-01、T-QA-02、QA-04、WFL-003 的运行时验证路径。

## 四、边界声明

本文件描述的是**仓库平台层**的强制。它不覆盖：Agent 本地沙箱行为（需 Claude Code / Codex 受限执行环境配置）、身份签发（需 Identity Broker）、审计存储（需独立审计服务）。这些属于 v1.1.1 §2/§9 的范围，试点阶段按 GOV-14 的 gap 声明处理。
