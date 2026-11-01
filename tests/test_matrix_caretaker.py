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

    # ---- F6 补测：结构不变量的未测分支 ----
    def test_invalid_kind_fails(self):
        m = json.loads(self.mp.read_text(encoding='utf-8'))
        m['issues']['AUD-001']['assertions'][0]['kind'] = 'guess'
        _write(self.mp, m)
        r = self._run(['--no-state'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('非法 kind', r.stdout)

    def test_audit_driven_disposition_missing_issue_fails(self):
        c = json.loads(self.cp.read_text(encoding='utf-8'))
        del c['dispositions']['REG-02']['issue']
        _write(self.cp, c)
        r = self._run(['--no-state'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('缺 issue', r.stdout)

    def test_defense_in_depth_disposition_missing_derived_from_fails(self):
        c = {'version': '1.0', 'dispositions': {
            'REG-09': {'type': 'defense_in_depth', 'reason': 'x',
                       'owner': 'governance_owner'}}}
        cp2 = self.tmp / 'c2.json'
        _write(cp2, c)
        cmd = [sys.executable, str(SCRIPT), '--matrix', str(self.mp),
               '--coverage', str(cp2), '--ledger', str(self.lp), '--no-state']
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn('缺 derived_from', r.stdout)

    # ---- F5：kind 变更必须触发漂移（id 集合不变也不行） ----
    def test_kind_change_is_drift(self):
        self._run()
        m = json.loads(self.mp.read_text(encoding='utf-8'))
        m['issues']['AUD-001']['assertions'][0]['kind'] = 'manual'
        _write(self.mp, m)
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('DRIFT', r.stdout)

    # ---- F3：--state 写路径 fail-closed ----
    def test_state_pointing_at_governance_file_rejected(self):
        target = ROOT / 'governance' / 'executor_pin.json'
        cmd = [sys.executable, str(SCRIPT), '--matrix', str(self.mp),
               '--coverage', str(self.cp), '--ledger', str(self.lp),
               '--state', str(target)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn('受保护目录', r.stdout)
        # 治理文件未被覆写
        self.assertIn('commit_sha', target.read_text(encoding='utf-8'))

    def test_state_same_as_input_rejected(self):
        cmd = [sys.executable, str(SCRIPT), '--matrix', str(self.mp),
               '--coverage', str(self.cp), '--ledger', str(self.lp),
               '--state', str(self.mp)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn('不允许与输入文件相同', r.stdout)

    # ---- F4：state 缺失/损坏时的基线回退 ----
    def test_corrupt_state_degrades_to_baseline(self):
        # 非 git 目录：git 回退不可用 -> 优雅降级为写新基线，exit 0
        self.state.write_text('{corrupt json!!', encoding='utf-8')
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('BASELINE', r.stdout)

    def test_git_history_baseline_detects_drift(self):
        # 真实 git 仓库：提交 v1 -> 改矩阵再提交 -> 删 state -> 应从 HEAD~1
        # 回退基线并报 DRIFT（CI 无状态文件时漂移不再失聪）
        self.tmp.joinpath('m.json').exists()  # noop keep linters calm
        for args in (['init'], ['config', 'user.email', 't@t'],
                     ['config', 'user.name', 't'], ['add', '.'],
                     ['commit', '-m', 'v1', '--no-gpg-sign']):
            subprocess.run(['git', '-C', str(self.tmp), *args],
                           capture_output=True)
        m = json.loads(self.mp.read_text(encoding='utf-8'))
        m['issues']['AUD-002'] = {'severity': 'P0', 'assertions': [
            {'id': 'AUD-002-01', 'kind': 'test'}]}
        _write(self.mp, m)
        subprocess.run(['git', '-C', str(self.tmp), 'add', '.'],
                       capture_output=True)
        subprocess.run(['git', '-C', str(self.tmp),
                        'commit', '-m', 'v2', '--no-gpg-sign'],
                       capture_output=True)
        # 不写 state：模拟 CI 首跑
        r = self._run()
        self.assertIn('DRIFT', r.stdout, r.stdout + r.stderr)
        self.assertIn('git:HEAD~1', r.stdout)
        # git 回退命中后 state 被固化，二跑无漂移
        r2 = self._run()
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn('无漂移', r2.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
