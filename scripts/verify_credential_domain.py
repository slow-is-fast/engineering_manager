#!/usr/bin/env python3
"""T-VD-01b：凭证域分离校验（控制 VD-01 / 规则 GOV-14）。

数据面运行时凭证（CI 中的 GITHUB_TOKEN）只应授给数据面仓库，不得对
控制面仓库 slow-is-fast/aasegs-gov-plane 有任何写权限。

行为
----
`--expect-deny`：对控制面做一次无害写尝试（创建 label），预期被 403 拒绝。
  被拒 → 通过。
  成功 → 先看在哪跑：
    - CI 环境（GITHUB_ACTIONS/CI）→ 凭证域**被破坏**，失败关闭，阻止合并。
    - 非 CI 环境 → **无法判定**，同样失败关闭。原因见下。
  两种情形都清理痕迹（删除刚创建的 label）。

为什么非 CI 下"能写"也算失败（2026-10-31 改）
--------------------------------------------
本检查要验的是「**数据面运行时凭证**不得写控制面」。本地拿人类 Owner 的个人
PAT 跑，测的是「个人 PAT 能不能写控制面」——这是**另一件事**，而且是已知为
真的另一件事（PAT 本来就横跨两域）。测不到要测的东西，正确结论是"无法判定"；
按本规范失败关闭的原则，不可判定即拒绝。

改之前这里的写法是：非 `--expect-deny` 时只打印 `INFO ... 人类 Owner 横跨两域
属预期` 然后**退出 0**。那是一条放行路径——只要不传 `--expect-deny`，跨平面
凭证就自动变绿，而本脚本此前没有任何单元测试盯着它。**一条没人测的放行路径，
等于一个默认开启的开关。**

诚实代价：本地 `gov_run.py --all` 会在这一步红。这是**事实**——本地凭证不足以
完成这项判定，应该让人看见，而不是给一个假的绿。有效判定请在 CI 中运行
（GITHUB_TOKEN 按仓库作用域），或改用仅数据面作用域的 token 后重跑。

无害性：写尝试使用固定 drill 标签名；若意外成功会立即删除。
"""
import os
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


def in_ci() -> bool:
    """是否在 CI 中运行。判定依据是平台注入的环境变量，不是"我觉得"。"""
    for k in ('GITHUB_ACTIONS', 'CI'):
        if str(os.environ.get(k, '')).strip().lower() in ('1', 'true', 'yes'):
            return True
    return False


def main() -> int:
    r = attempt_write()
    allowed = r.returncode == 0

    if allowed:
        # 写成功了就必须把痕迹清掉——演练标签留在控制面上，本身就是污染。
        cleanup()

    if not allowed:
        print(f'PASS(T-VD-01b): data-plane credential denied on control plane '
              f'({(r.stderr or b"").decode()[:80].strip()})')
        return 0

    if in_ci():
        sys.exit('FAIL(T-VD-01b): data-plane credential WROTE to control plane! '
                 '凭证域被破坏（期望 403 拒绝，实际成功，已清理痕迹）。阻止合并。')

    sys.exit('FAIL(T-VD-01b): 无法判定——当前凭证可写控制面，但本检查要验的是'
             '「数据面运行时凭证」不得写控制面；非 CI 环境下的人类 PAT 本来就'
             '横跨两域，测不到要测的东西，因此不能据此判定通过（已清理痕迹）。'
             '不可判定即拒绝：请在 CI 中运行（GITHUB_TOKEN 按仓库作用域），'
             '或改用仅数据面作用域的 token 后重跑。')


if __name__ == '__main__':
    sys.exit(main())
