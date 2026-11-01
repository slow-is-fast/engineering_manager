# -*- coding: utf-8 -*-
"""matrix_caretaker 的只读巡检行为：结构不变量 + 快照基线 + 漂移告警。

核心不变量：仅读治理 JSON；结构违反→退出 2；首次运行写基线→0；
重复运行无漂移→0；结构变化→告警（默认 0 / --strict 3）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'matrix_caretaker.py'


def _write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')


def _valid_set(tmp):
    matrix = {'version': '1.0', 'issues': {
        'AUD-001': {'severity': 'P0', 'assertions': [
            {'id': 'AUD-001-01', 'kind': 'test'}]}}}
    coverage = {'version': '1.0', 'dispositions': {
        'REG-02': {'type': 'audit_driven', 'issue': 'AASEGS-AUD-002',
                   'reason': 'x', 'owner': 'governance_owner'}}}
    ledger = {'version': '1.0', 'items': [
        {'id': 'evidence/x.md', 'sha256': 'abc', 'category': 'evidence',
         'created_at': 1}]}
    mp, cp, lp = (tmp / 'm.json', tmp / 'c.json', tmp / 'e.json')
    _write(mp, matrix)
    _write(cp, coverage)
    _write(lp, ledger)
    return mp, cp, lp


class CaretakerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mp, self.cp, self.lp = _valid_set(self.tmp)
        self.state = self.tmp / 'state.json'

    def _run(self, extra=None, env_extra=None):
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        cmd = [sys.executable, str(SCRIPT), '--matrix', str(self.mp),
               '--coverage', str(self.cp), '--ledger', str(self.lp),
               '--state', str(self.state)]
        if extra:
            cmd += extra
        return subprocess.run(cmd, env=env, capture_output=True, text=True)

    # ---- 结构不变量 ----
    def test_structural_invariants_pass(self):
        r = self._run(['--no-state'])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('OK(caretaker)', r.stdout)

    def test_duplicate_assertion_id_fails(self):
        m = json.loads(self.mp.read_text(encoding='utf-8'))
        m['issues']['AUD-001']['assertions'].append(
            {'id': 'AUD-001-01', 'kind': 'test'})
        _write(self.mp, m)
        r = self._run(['--no-state'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('断言 id 重复', r.stdout)

    def test_missing_owner_fails(self):
        c = json.loads(self.cp.read_text(encoding='utf-8'))
        del c['dispositions']['REG-02']['owner']
        _write(self.cp, c)
        r = self._run(['--no-state'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('缺 owner', r.stdout)

    def test_missing_sha256_fails(self):
        e = json.loads(self.lp.read_text(encoding='utf-8'))
        del e['items'][0]['sha256']
        _write(self.lp, e)
        r = self._run(['--no-state'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('缺 sha256', r.stdout)

    # ---- 基线 / 漂移 ----
    def test_first_run_writes_baseline(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('BASELINE', r.stdout)
        self.assertTrue(self.state.is_file())

    def test_second_run_no_drift(self):
        self._run()
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('无漂移', r.stdout)

    def test_drift_detected_nonstrict_is_zero(self):
        self._run()
        m = json.loads(self.mp.read_text(encoding='utf-8'))
        m['issues']['AUD-002'] = {'severity': 'P0', 'assertions': [
            {'id': 'AUD-002-01', 'kind': 'test'}]}
        _write(self.mp, m)
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('DRIFT', r.stdout)

    def test_drift_detected_strict_is_three(self):
        self._run()
        m = json.loads(self.mp.read_text(encoding='utf-8'))
        m['issues']['AUD-002'] = {'severity': 'P0', 'assertions': [
            {'id': 'AUD-002-01', 'kind': 'test'}]}
        _write(self.mp, m)
        r = self._run(['--strict'])
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn('DRIFT', r.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
