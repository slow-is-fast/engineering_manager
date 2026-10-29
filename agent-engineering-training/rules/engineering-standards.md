# Engineering Standards v0.1
Status: DRAFT — requires human approval.

## Before work
- Understand issue, scope, constraints, acceptance criteria, and affected interfaces.
- Clarify missing requirements or record assumptions with explicit approval for risky changes.
- Inspect current design before proposing changes. No speculative unrelated refactors.

## Execution
- Use isolated branch/worktree; never write directly to protected branches.
- No bypassing permission gates, weakening tests, or concealing failures.
- Use smallest appropriate change; document architectural decisions if interfaces/behavior change.

## Verification
- Record commands, exit codes, environment, test results and omissions.
- New behavior requires corresponding tests or explicit test limitation.
- Passing tests do not prove complete correctness.

## Review and release
- Independent review provides findings, not guaranteed correctness.
- Merge/release according to external CI status and human policy.
- Never self-certify graduation, quietly alter acceptance criteria, or auto-promote new skills.
