# -*- coding: utf-8 -*-
"""T-VD-01b（scripts/verify_credential_domain.py）的负向用例。

这条检查此前**没有任何单元测试**——它只在 CI 里被引用一次，而它有一条
"不传 --expect-deny 就只打印 INFO 然后退出 0"的放行路径。没人测的放行路径
等于默认开启的开关：本地拿横跨两域的个人 PAT 跑，脚本会说"属预期"然后变绿。

要钉死的是三件事：
1. 能写控制面 → 无论在哪跑都必须非零退出（CI 判"被破坏"，非 CI 判"无法判定"）。
   **"无法判定"不是"通过"**——测不到要测的东西和测过了通过，是两回事。
2. 写尝试成功了必须清理痕迹，演练标签不能留在控制面上。
3. 环境判定来自平台注入的环境变量，不是"我觉得我在 CI"。
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.verify_credential_domain as vcd  # noqa: E402


class _Proc:
    def __init__(self, rc, err=b''):
        self.returncode = rc
        self.stderr = err


class CredentialDomainTests(unittest.TestCase):
    def setUp(self):
        self._env = dict(vcd.os.environ)
        for k in ('CI', 'GITHUB_ACTIONS'):
            vcd.os.environ.pop(k, None)
        self.addCleanup(self._restore_env)
        self.cleaned = []
        self.addCleanup(setattr, vcd, 'cleanup', vcd.cleanup)
        vcd.cleanup = lambda: self.cleaned.append(1)

    def _restore_env(self):
        vcd.os.environ.clear()
        vcd.os.environ.update(self._env)

    def _run(self, rc, ci=False):
        if ci:
            vcd.os.environ['GITHUB_ACTIONS'] = 'true'
        with mock.patch.object(vcd, 'attempt_write', return_value=_Proc(rc)):
            return vcd.main()

    def test_T_CD_01_denied_passes(self):
        """被拒 = 通过。这是唯一一条能证明分域有效的读数。"""
        self.assertEqual(self._run(1), 0)
        self.assertEqual(self.cleaned, [])  # 没写成功就没什么可清理的

    def test_T_CD_02_allowed_in_ci_is_a_broken_domain(self):
        """CI 里能写控制面 = 凭证域被破坏，不是"环境差异"。"""
        with self.assertRaises(SystemExit) as cm:
            self._run(0, ci=True)
        self.assertIn('凭证域被破坏', str(cm.exception))
        self.assertIn('阻止合并', str(cm.exception))
        self.assertEqual(self.cleaned, [1], '写成功了必须清理痕迹')

    def test_T_CD_03_allowed_outside_ci_is_inconclusive_not_pass(self):
        """核心：非 CI 下能写控制面，结论是"无法判定"，不是"属预期"。

        改之前这条会 return 0 并打印 INFO——即本地跨平面凭证自动变绿。
        """
        with self.assertRaises(SystemExit) as cm:
            self._run(0, ci=False)
        msg = str(cm.exception)
        self.assertIn('无法判定', msg)
        self.assertNotIn('属预期', msg)
        self.assertIn('不可判定即拒绝', msg)
        self.assertEqual(self.cleaned, [1], '写成功了必须清理痕迹')

    def test_T_CD_04_expect_deny_flag_does_not_create_a_pass_path(self):
        """--expect-deny 与否不改变"能写就失败"的结论。

        曾几何时"不传 --expect-deny"本身就是一个弱化开关。现在参数不再
        影响判定，只读环境变量决定诊断文案。
        """
        for flag in (True, False):
            with mock.patch.object(sys, 'argv',
                                   ['x'] + (['--expect-deny'] if flag else [])):
                with self.assertRaises(SystemExit):
                    self._run(0, ci=False)

    def test_T_CD_05_ci_detection_comes_from_env_not_guess(self):
        """环境判定读平台注入的变量；`CI=1` 与 `GITHUB_ACTIONS=true` 都应识别。"""
        for k, v in (('CI', '1'), ('GITHUB_ACTIONS', 'true'),
                     ('CI', 'yes'), ('GITHUB_ACTIONS', 'TRUE')):
            vcd.os.environ[k] = v
            self.assertTrue(vcd.in_ci(), f'{k}={v} 应判为 CI')
            vcd.os.environ.pop(k, None)
        for k, v in (('CI', ''), ('GITHUB_ACTIONS', 'false'), ('CI', '0')):
            vcd.os.environ[k] = v
            self.assertFalse(vcd.in_ci(), f'{k}={v} 不应判为 CI')
            vcd.os.environ.pop(k, None)
        self.assertFalse(vcd.in_ci(), '两个变量都不存在时不应判为 CI')


if __name__ == '__main__':
    unittest.main(verbosity=2)
