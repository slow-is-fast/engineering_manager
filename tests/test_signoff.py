# -*- coding: utf-8 -*-
"""T-SO：record_signoff.py 的失败关闭路径守卫。

脚手架的硬约束是"禁止自签"（签署人身份不得等于执行主体 GOV_ACTING_IDENTITY）
且必须声明独立角色、必填证据与说明。本文件覆盖：
  - 合法独立签署被记录（含 signature / evidence_hash）
  - 自签（reviewer == 执行主体）被拒
  - 非法角色被拒
  - 缺证据被拒
  - 说明过短被拒
变异体检见 evidence/signoff_scaffold_20261031T224100Z.md。
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import record_signoff as rs  # noqa: E402


def _args(**kw):
    base = dict(
        assertion_id='AUD-015-04',
        reviewer='alice',
        role='independent-reviewer',
        verdict='approved',
        evidence='evidence/x.md',
        basis='已审阅响应手册与四类隔离演练记录，确认每类场景均有对应用例覆盖，结论可信。',
    )
    base.update(kw)
    return argparse.Namespace(**base)


class SignoffTests(unittest.TestCase):
    def setUp(self):
        os.environ['GOV_ACTING_IDENTITY'] = 'agent-bravo'
        self.tmp = Path(tempfile.mkdtemp(prefix='aasegs-so-'))
        self.store = self.tmp / 'signoffs.jsonl'
        (self.tmp / 'evidence').mkdir()
        (self.tmp / 'evidence' / 'x.md').write_text('evidence', encoding='utf-8')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _run(self, **kw):
        a = _args(**kw)
        a.store = str(self.store)
        if 'evidence' not in kw:
            a.evidence = str(self.tmp / 'evidence' / 'x.md')
        try:
            return rs.record(a, self.store), None
        except SystemExit as e:
            return None, e.code if isinstance(e.code, int) else 1

    def test_valid_signoff_recorded(self):
        rc, _ = self._run(reviewer='alice')
        self.assertEqual(rc, 0, '合法独立签署应当被记录')
        lines = [l for l in self.store.read_text(encoding='utf-8').splitlines() if l]
        self.assertEqual(len(lines), 1)
        e = json.loads(lines[0])
        self.assertEqual(e['reviewer'], 'alice')
        self.assertEqual(e['assertion_id'], 'AUD-015-04')
        self.assertIn('signature', e)
        self.assertIn('evidence_hash', e)
        self.assertTrue(self.store.stat().st_size > 0)

    def test_self_sign_rejected(self):
        rc, code = self._run(reviewer='agent-bravo')
        self.assertNotEqual(rc, 0, '签署人等于执行主体必须被拒（EXC-01 防自签）')
        self.assertFalse(
            self.store.exists() and self.store.stat().st_size > 0,
            '被拒的签署不得写入任何条目')

    def test_invalid_role_rejected(self):
        rc, _ = self._run(role='dev')
        self.assertNotEqual(rc, 0, '非法角色必须被拒')

    def test_missing_evidence_rejected(self):
        rc, _ = self._run(evidence='')
        self.assertNotEqual(rc, 0, '缺证据必须被拒')

    def test_short_basis_rejected(self):
        rc, _ = self._run(basis='太短')
        self.assertNotEqual(rc, 0, '说明过短必须被拒')


if __name__ == '__main__':
    unittest.main()
