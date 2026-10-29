#!/usr/bin/env python3
"""RVW-02（候选）：评审 Agent 凭证只读性校验——多 Agent / 单人开发场景适配。

场景：只有一名人类开发者，但有**多个 Agent**。此时"第二人类审批主体"不可得，
QA-03/RVW-01 的平台级独立审批无法达成（已实证：第二 PAT ≠ 第二主体）。
退而求其次的补偿控制：让**评审 Agent 使用只读凭证**——它可以看、可以下结论，
但改不动被评审的代码；写操作只能由写入 Agent（或人类）用另一把凭证执行。

判定（对本仓库做一次真实写尝试）：
  --expect-deny：写尝试必须被 403/401 拒绝；若成功（并已清理）→ 非零退出，
    说明"评审"与"写入"没有分凭证，独立性不成立。
  无参数：只报告结果，不判定。

使用：GH_TOKEN=<reviewer token> python scripts/verify_reviewer_credential.py --expect-deny
注意：不要把 token 写进仓库；用环境变量传入，用完轮换。
"""
import subprocess
import sys

DATA_PLANE = 'slow-is-fast/engineering_manager'
PROBE_REF = 'refs/heads/drill/reviewer-write-probe'


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(['gh', 'api', *args], capture_output=True)


def main() -> None:
    expect_deny = '--expect-deny' in sys.argv

    read = gh(f'repos/{DATA_PLANE}')
    if read.returncode != 0:
        sys.exit('FAIL(RVW-02): 评审凭证连读取都失败，无法参与评审')

    head = gh(f'repos/{DATA_PLANE}/git/ref/heads/main')
    sha = ''
    if head.returncode == 0:
        import json
        sha = json.loads(head.stdout)['object']['sha']

    r = gh('-X', 'POST', f'repos/{DATA_PLANE}/git/refs',
           '-f', f'ref={PROBE_REF}', '-f', f'sha={sha}')
    allowed = r.returncode == 0
    if allowed:
        gh('-X', 'DELETE', f'repos/{DATA_PLANE}/git/refs/heads/drill/reviewer-write-probe')

    if not expect_deny:
        print(f'INFO(RVW-02): reviewer credential write on data plane: '
              f'{"ALLOWED（已清理）— 该凭证不是只读，不可用于评审" if allowed else "DENIED（符合只读评审要求）"}')
        return

    if allowed:
        sys.exit('FAIL(RVW-02): 评审凭证具备写权限（已清理探测分支）。'
                 '评审与写入必须分凭证，否则"独立评审"不成立。')
    print('PASS(RVW-02): reviewer credential is read-only on data plane '
          f'({(r.stderr or b"").decode()[:80].strip()})')


if __name__ == '__main__':
    main()
