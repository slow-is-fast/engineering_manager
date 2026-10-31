# 放行路径体检：审计闭合评估（check_audit_closure.py / --enforce）

- 关联：发现 8「给剩余必需检查做放行路径变异体检」的收尾项之一
- 检查：`scripts/check_audit_closure.py` 的 `--enforce` 路径，底层为
  `executor/closure.ClosureEvaluator.assert_no_unbacked_closure()`
- 结论：此前该路径**没有任何用例守护**；已补 3 条守卫用例，2 处 fail-open
  变异全部被抓（0 逃逸）。

## 背景（为什么这是真缺口）

`check_audit_closure.py --enforce` 只做一件事：调 `assert_no_unbacked_closure()`，
发现「声明 CLOSED / ACCEPTED_RISK 但控制级证据不成立」就抛 `ClosureIntegrityError`
（退出码 1）。这正是要防的「把文档改完就当问题关闭」。

但仓库里 `tests/` 没有任何用例触达 `assert_no_unbacked_closure`。一旦有人把
`evaluate()` 里的违规判定弱化（或直接把 `assert_no_unbacked_closure` 改成永远
通过），CI 的 `--enforce` 会安静地放过虚假关闭——而没有任何测试会响。

## 补的守卫（tests/test_audit_closure.py，T-AUD-CLS×3）

1. `test_unbacked_closure_rejected`：控制 `state.tested=False` 却声明 `CLOSED`
   → 必须判 `unbacked_closure` 违规。
2. `test_stale_evidence_blocks_closure`：控制声称 `tested` 但 `evidence_at` 拨到
   2020 年（P0 TTL=30 天）→ 仍不算 `machine_ready` → 必须判违规。这条专门钉住
   「证据新鲜度」在闭合判定里的权重，避免老化证据被当成持续有效。
3. `test_open_issue_not_closure_violation`：正向对照——仍在 `IN_PROGRESS` 的问题
   不构成闭合违规（拒绝不是永远拒绝）。

## 放行路径变异体检（2 处，0 逃逸）

变异注入方式：备份 `executor/closure.py` 到内存 → 改写 → 跑守卫用例 → 立即还原
（还原后 `git status` 确认干净）。判据：用例退出码非 0 = 被抓。

| 变异 | 手法 | 守卫反应 | 结果 |
|------|------|----------|------|
| M1 | `assert_no_unbacked_closure` 的 `if res["violations"]:` 改成 `if False:`（永远通过） | `test_unbacked_closure_rejected` / `test_stale_evidence_blocks_closure` 不再抛异常 → 失败 | CAUGHT |
| M2 | `evaluate()` 里 `if status in CLAIMED_DONE and not machine_ready:` 改成 `if False:`（屏蔽 unbacked 检测分支） | 同上两条用例失败 | CAUGHT |

逃逸：0 / 2。

## 诚实边界

- 本体检只覆盖「未落实就被声明关闭」这一类（unbacked_closure）。同一 `assert`
  还会因 `closure_without_acceptance`（声明关闭但 §四 验收未满足）判违规，那条
  走的是另一个分支，本次未单独隔离变异，但同样由 `assert_no_unbacked_closure`
  的同一道门兜底。
- `--enforce` 的 CLI 装配很薄（check_audit_closure.py 直接转发 `assert_no_*`），
  已随 `gov_run --check` 进审计流，未单列变异。
- 受 EXC-01 约束，`CLOSED` 的最终裁定仍须独立人类复核，本检查只拦「机器可判定
  的虚假关闭」，不替代独立复核。
- 净增 3 条守卫用例；质量基线 `min_test_count` 263→269（§10.31）再 +3 → 实际 272，
  下限 269 仍成立（新增用例不要求审批）。
