# -*- coding: utf-8 -*-
"""T-EXP-01 例外到期检查：到期即红、临界告警、格式非法失败关闭。

背景：`expires` 字段此前只被要求"是合法日期"，从不与今天比较——
带到期日的例外实际等价于永久例外，只是它自己不知道。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'verify_exception_expiry.py'


def _repo(tmp, exceptions):
    (tmp / 'governance').mkdir(parents=True, exist_ok=True)
    (tmp / 'governance' / 'quality_baseline.json').write_text(
        json.dumps({'exceptions': exceptions}), encoding='utf-8')


def _run(root, extra=None):
    return subprocess.run([sys.executable, str(SCRIPT), *(extra or []), str(root)],
                          capture_output=True, text=True)


def out(r):
    return r.stdout + r.stderr


def _day(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


class ExceptionExpiryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_far_future_passes(self):
        _repo(self.tmp, [{'id': 'EXC-X', 'expires': _day(400)}])
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 0, out(r))
        self.assertIn('PASS(T-EXP-01)', r.stdout)

    def test_expired_fails(self):
        _repo(self.tmp, [{'id': 'EXC-OLD', 'expires': _day(-1)}])
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 2, out(r))
        self.assertIn('EXC-OLD', out(r))
        self.assertIn('已于', out(r))
        self.assertIn('不可默认沿用', out(r))

    def test_within_warn_window_warns_but_passes(self):
        # 提前量是提醒，不是事实判定——不能把到期前三个月做成红
        _repo(self.tmp, [{'id': 'EXC-SOON', 'expires': _day(30)}])
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 0, out(r))
        self.assertIn('WARN(T-EXP-01)', r.stdout)
        self.assertIn('EXC-SOON', r.stdout)

    def test_warn_days_is_configurable(self):
        _repo(self.tmp, [{'id': 'EXC-MID', 'expires': _day(60)}])
        r = _run(self.tmp, ['--warn-days', '10'])
        self.assertEqual(r.returncode, 0, out(r))
        self.assertNotIn('WARN', r.stdout)
        r2 = _run(self.tmp, ['--warn-days', '90'])
        self.assertIn('WARN', r2.stdout)

    def test_missing_expires_fails_closed(self):
        _repo(self.tmp, [{'id': 'EXC-NOEXP'}])
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 2, out(r))
        self.assertIn('例外必须有终点', out(r))

    def test_bad_date_format_fails(self):
        _repo(self.tmp, [{'id': 'EXC-BAD', 'expires': '2027/01/31'}])
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 2, out(r))
        self.assertIn('YYYY-MM-DD', out(r))

    def test_no_exceptions_is_fine(self):
        # 没有例外是好事，不是缺配置
        _repo(self.tmp, [])
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 0, out(r))
        self.assertIn('未登记任何例外', r.stdout)

    def test_duplicate_exception_id_fails(self):
        _repo(self.tmp, [{'id': 'EXC-D', 'expires': _day(100)},
                         {'id': 'EXC-D', 'expires': _day(200)}])
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 2, out(r))
        self.assertIn('重复', out(r))

    def test_real_repo_selfcheck(self):
        # EXC-01（2027-01-31）/ EXC-02（2027-04-30）当前都应未过期
        r = _run(ROOT)
        self.assertEqual(r.returncode, 0, out(r))
        self.assertIn('个例外全部未过期', r.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
