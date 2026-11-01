# -*- coding: utf-8 -*-
"""T-QA-04b 接线校验的行为：注册 <-> 执行 必须双向闭合。

背景（2026-11-01）：required_checks 增至 15 项而 workflow 只有 13 个
`--check` 步骤，本地 suite 全绿毫无感知，推送后才被 `--verify` 拦下。
本测试锁住该检测：缺步骤红、多余步骤红、注释不算、不可判定即拒。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'verify_required_checks_wired.py'


def _repo(tmp, required, steps, args_map='default'):
    (tmp / 'governance').mkdir(parents=True, exist_ok=True)
    (tmp / '.github' / 'workflows').mkdir(parents=True, exist_ok=True)
    (tmp / 'governance' / 'quality_baseline.json').write_text(
        json.dumps({'required_checks': required}), encoding='utf-8')
    # D 段：每项必需检查都要在 audit_policy.check_args 里显式声明
    args = {t: [[]] for t in required} if args_map == 'default' else args_map
    (tmp / 'governance' / 'audit_policy.json').write_text(
        json.dumps({'check_args': args}), encoding='utf-8')
    for target in required + [s for s in steps if s not in required]:
        p = tmp / target
        if p.suffix and not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('# stub\n', encoding='utf-8')
    lines = ['name: governance', 'jobs:', '  g:', '    steps:']
    for i, s in enumerate(steps):
        lines.append(f'      - name: "step {i}"')
        lines.append(f'        run: python scripts/gov_run.py --check {s}')
    (tmp / '.github' / 'workflows' / 'governance.yml').write_text(
        '\n'.join(lines) + '\n', encoding='utf-8')


def _run(root):
    return subprocess.run([sys.executable, str(SCRIPT), str(root)],
                          capture_output=True, text=True)


def out(r):
    # fail() 走 sys.exit(msg) -> stderr（项目惯例），问题清单走 stdout
    return r.stdout + r.stderr


class RequiredChecksWiredTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_bidirectional_match_passes(self):
        _repo(self.tmp, ['scripts/a.py', 'tests/b.py'],
              ['scripts/a.py', 'tests/b.py'])
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('PASS(T-QA-04b)', r.stdout)

    def test_unwired_check_fails(self):
        # 注册了两条，只接了一条线 -> 红（本次事故的最小复现）
        _repo(self.tmp, ['scripts/a.py', 'scripts/c.py'], ['scripts/a.py'])
        r = _run(self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('没有对应的 CI --check 步骤', out(r))
        self.assertIn('scripts/c.py', r.stdout)

    def test_unregistered_step_fails(self):
        # 跑了但不在基线里 -> 红（记账事件不属于基线，或漏更新基线）
        _repo(self.tmp, ['scripts/a.py'], ['scripts/a.py', 'scripts/b.py'])
        r = _run(self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('未收录', out(r))

    def test_commented_step_not_counted(self):
        # 注释掉的 run 不产生事件，不能算接线
        _repo(self.tmp, ['scripts/a.py'], ['scripts/a.py'])
        wf = self.tmp / '.github' / 'workflows' / 'governance.yml'
        wf.write_text('name: g\njobs:\n  g:\n    steps:\n'
                      '      # run: python scripts/gov_run.py --check scripts/a.py\n',
                      encoding='utf-8')
        r = _run(self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('no `gov_run.py --check <path>` step found', out(r))

    def test_missing_workflow_dir_fails_closed(self):
        (self.tmp / 'governance').mkdir(parents=True)
        (self.tmp / 'governance' / 'quality_baseline.json').write_text(
            json.dumps({'required_checks': ['scripts/a.py']}), encoding='utf-8')
        r = _run(self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('no workflow directory', out(r))

    def test_step_target_missing_file_fails(self):
        # 打错路径的步骤永远绿不了，却可能被误读成"已覆盖"
        (self.tmp / 'governance').mkdir(parents=True)
        (self.tmp / '.github' / 'workflows').mkdir(parents=True)
        (self.tmp / 'governance' / 'quality_baseline.json').write_text(
            json.dumps({'required_checks': ['scripts/typo.py']}), encoding='utf-8')
        (self.tmp / 'governance' / 'audit_policy.json').write_text(
            json.dumps({'check_args': {'scripts/typo.py': [[]]}}), encoding='utf-8')
        (self.tmp / '.github' / 'workflows' / 'governance.yml').write_text(
            'jobs:\n  g:\n    steps:\n'
            '      - run: python scripts/gov_run.py --check scripts/typo.py\n',
            encoding='utf-8')
        r = _run(self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('指向不存在的文件', out(r))

    # ---- D 段：调用参数必须显式声明 ----
    def test_undeclared_check_args_fails(self):
        # 注册了但没声明参数 -> 会走隐式默认档位（弱模式假绿的入口）
        _repo(self.tmp, ['scripts/a.py', 'scripts/b.py'],
              ['scripts/a.py', 'scripts/b.py'],
              args_map={'scripts/a.py': [[]]})
        r = _run(self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('未在 audit_policy.check_args 显式声明', out(r))
        self.assertIn('scripts/b.py', out(r))

    def test_orphan_check_args_fails(self):
        # 配置了某检查的参数，但它不在 required_checks 里 -> 配了不会跑
        _repo(self.tmp, ['scripts/a.py'], ['scripts/a.py'],
              args_map={'scripts/a.py': [[]], 'scripts/ghost.py': [[]]})
        r = _run(self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('配置了不会跑的检查', out(r))

    def test_bad_check_args_shape_fails(self):
        # 空列表 / 非列表 -> 结构非法（空列表意味着"零次调用"，等于不跑）
        _repo(self.tmp, ['scripts/a.py'], ['scripts/a.py'],
              args_map={'scripts/a.py': []})
        r = _run(self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('非空列表的列表', out(r))

    def test_missing_audit_policy_fails_closed(self):
        _repo(self.tmp, ['scripts/a.py'], ['scripts/a.py'])
        (self.tmp / 'governance' / 'audit_policy.json').unlink()
        r = _run(self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('audit_policy.json', out(r))

    def test_real_repo_selfcheck(self):
        # 真实仓库当前必须双向一致——这条是本次事故的回归锁
        r = _run(ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('required checks all wired in CI', r.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
