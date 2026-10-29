#!/usr/bin/env python3
"""T-VD-01b：凭证域分离校验（控制 VD-01 / 规则 GOV-14）。

数据面运行时凭证（CI 中的 GITHUB_TOKEN）只应授给数据面仓库，不得对
控制面仓库 slow-is-fast/aasegs-gov-plane 有任何写权限。

行为：
  --expect-deny（CI 模式）：对控制面做一次无害写尝试（创建 label），
    预期被 403 拒绝。若意外成功，立即删除该 label 并以非零退出
    （失败关闭）——说明凭证域配置被破坏，必须阻止合并。
  无参数（审计模式）：只报告写尝试结果，不判定成败。用于本地演示：
    Owner 人类凭证横跨两域是预期行为，但绝不可交给 Agent 使用。

无害性：写尝试使用固定 drill 标签名；若意外成功会立即删除。
"""
import subprocess
import sys

CONTROL_REPO = 'slow-is-fast/aasegs-gov-plane'
DRILL_LABEL = 'credential-domain-drill'
DRILL_COLOR = '999999'


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(['gh', 'api', *args], capture_output=True)


def attempt_write() -> subprocess.CompletedProcess:
    return gh('-X', 'POST', f'repos/{CONTROL_REPO}/labels',
              '-f', f'name={DRILL_LABEL}', '-f', f'color={DRILL_COLOR}')


def cleanup() -> None:
    gh('-X', 'DELETE', f'repos/{CONTROL_REPO}/labels/{DRILL_LABEL}')


def main() -> None:
    expect_deny = '--expect-deny' in sys.argv
    r = attempt_write()
    allowed = r.returncode == 0

    if allowed:
        cleanup()

    if not expect_deny:
        verdict = ('ALLOWED（已清理）——当前凭证对控制面有写权限。'
                   '人类 Owner 横跨两域属预期；但该凭证绝不可交给数据面 Agent 使用。'
                   if allowed else
                   'DENIED——当前凭证无法写控制面（符合 Agent 凭证分域要求）。')
        print(f'INFO(T-VD-01b): credential domain check: {verdict}')
        return

    if allowed:
        sys.exit('FAIL(T-VD-01b): data-plane credential WROTE to control plane! '
                 '凭证域被破坏（期望 403 拒绝，实际成功，已清理痕迹）。阻止合并。')

    print(f'PASS(T-VD-01b): data-plane credential denied on control plane '
          f'({(r.stderr or b"").decode()[:80].strip()})')


if __name__ == '__main__':
    main()
