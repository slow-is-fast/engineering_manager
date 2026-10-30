# -*- coding: utf-8 -*-
"""T-QA-01 / T-QA-02 / T-QA-04 的负向用例。

2026-10-30 记账复核把 QA-01、QA-02、BASE-01 从 drill（只有一次性演练记录）
转为 automated（每次改动都会再跑）。转过来就得配独立负向用例——否则"校验器
存在"和"校验器真的拦得住"又变成两件事。
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'


def run_script(name, cwd):
    r = subprocess.run([sys.executable, str(SCRIPTS / name), str(cwd)],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


class BaselineNegativeTests(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='aasegs-qa-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    # ---- T-QA-01：CI action 未 pin 到 SHA → 必须失败 ----
    def test_t_qa_01_unpinned_action_rejected(self):
        wf = self.tmp / '.github' / 'workflows'
        wf.mkdir(parents=True)
        (wf / 'ci.yml').write_text(
            'jobs:\n  j:\n    steps:\n      - uses: actions/checkout@v4\n',
            encoding='utf8')
        rc, out = run_script('verify_ci_app_binding.py', self.tmp)
        self.assertNotEqual(rc, 0, '浮动 tag 竟然通过了')
        self.assertIn('T-QA-01', out)
        self.assertIn('actions/checkout@v4', out)

    def test_t_qa_01_pinned_action_passes(self):
        """正向对照：证明上面的拒绝不是"永远拒绝"。"""
        wf = self.tmp / '.github' / 'workflows'
        wf.mkdir(parents=True)
        (wf / 'ci.yml').write_text(
            'jobs:\n  j:\n    steps:\n'
            '      - uses: actions/checkout@' + 'a' * 40 + '  # v4\n',
            encoding='utf8')
        rc, out = run_script('verify_ci_app_binding.py', self.tmp)
        self.assertEqual(rc, 0, out)

    # ---- T-QA-02：验收用例数低于基线 → 必须失败 ----
    def test_t_qa_02_test_count_drop_rejected(self):
        (self.tmp / 'governance').mkdir()
        (self.tmp / 'governance' / 'quality_baseline.json').write_text(
            json.dumps({'test_thresholds': {'min_test_count': 110}}),
            encoding='utf8')
        (self.tmp / 'tests').mkdir()
        (self.tmp / 'tests' / 'test_x.py').write_text(
            'def test_only_one():\n    pass\n', encoding='utf8')
        rc, out = run_script('verify_test_floor.py', self.tmp)
        self.assertNotEqual(rc, 0, '删掉 109 条用例竟然通过了')
        self.assertIn('dropped', out)

    def test_t_qa_02_missing_baseline_fails_closed(self):
        """没有基线就不能判"通过"——不可判定即失败关闭。"""
        rc, out = run_script('verify_test_floor.py', self.tmp)
        self.assertNotEqual(rc, 0)
        self.assertIn('missing', out)

    # ---- T-QA-04：治理已变而基线未重审 → 必须失败 ----
    def test_t_qa_04_baseline_drift_rejected(self):
        def git(*args):
            r = subprocess.run(
                ['git', '-C', str(self.tmp), '-c', 'user.email=qa@example.com',
                 '-c', 'user.name=qa', '-c', 'commit.gpgsign=false', *args],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout.strip()

        git('init', '-q')
        (self.tmp / 'governance').mkdir()
        baseline = {
            'required_checks': ['a'], 'trusted_ci_sources': ['b'],
            'executor_pin_version': {'pinned_commit': 'c'},
            'test_thresholds': {'min_test_count': 1},
            'applies_to_sha': 'x', 'exceptions': [], 'change_approval': {'rule': 'r'},
            'reviewed_by': 'owner', 'reviewed_at': '2026-10-30T00:00:00+08:00',
        }
        (self.tmp / 'governance' / 'quality_baseline.json').write_text(
            json.dumps(baseline), encoding='utf8')
        (self.tmp / 'scripts').mkdir()
        (self.tmp / 'scripts' / 'x.py').write_text('# v1\n', encoding='utf8')
        git('add', '.')
        git('commit', '-qm', 'baseline + governance')

        rc, out = run_script('verify_quality_baseline.py', self.tmp)
        self.assertEqual(rc, 0, out)          # 同批提交 → 通过

        # 只改治理文件、不碰基线 → 旧审核不得复用
        (self.tmp / 'scripts' / 'x.py').write_text('# v2\n', encoding='utf8')
        git('add', '.')
        git('commit', '-qm', 'change governance only')
        rc, out = run_script('verify_quality_baseline.py', self.tmp)
        self.assertNotEqual(rc, 0, '治理变了基线没动，竟然通过')
        self.assertIn('drift', out)

    def test_t_qa_04_incomplete_baseline_rejected(self):
        (self.tmp / 'governance').mkdir()
        (self.tmp / 'governance' / 'quality_baseline.json').write_text(
            json.dumps({'required_checks': ['a']}), encoding='utf8')
        rc, out = run_script('verify_quality_baseline.py', self.tmp)
        self.assertNotEqual(rc, 0)
        self.assertIn('incomplete', out)


if __name__ == '__main__':
    unittest.main()
