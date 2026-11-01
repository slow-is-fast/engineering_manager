# -*- coding: utf-8 -*-
"""apply_signoffs 的失败关闭守卫 + dry-run/apply 行为。

核心不变量：任一签署条目不合法 → 整批原子中止，不写任何字段、不改任何文件。
含 #6 review-agent 绑定守卫（opt-in，环境变量 GOV_REVIEW_AGENT）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'apply_signoffs.py'
sys.path.insert(0, str(ROOT / 'scripts'))
import apply_signoffs as app  # noqa: E402
from record_signoff import _ev_hash  # noqa: E402


def _matrix_with(assertions_by_issue):
    issues = {}
    for iid, asrts in assertions_by_issue.items():
        issues[iid] = {'severity': 'P0', 'assertions': asrts}
    return {'issues': issues}


def _valid_entry(assertion_id, evidence, reviewer='alice', role='independent-reviewer',
                verdict='approved', reviewed_at='2026-11-01T10:00:00+08:00'):
    return {
        'assertion_id': assertion_id,
        'reviewer': reviewer,
        'role': role,
        'reviewed_at': reviewed_at,
        'evidence_refs': [str(evidence)],
        'evidence_hash': _ev_hash([str(evidence)]),
        'verdict': verdict,
        'basis': '抽样覆盖若干控制，结论一致',
        'signature': 'sigplaceholder',
    }


class ApplySignoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.matrix_path = Path(self.tmp) / 'acceptance_matrix.json'
        self.signoffs_path = Path(self.tmp) / 'signoffs.jsonl'
        self.ev = Path(self.tmp) / 'ev.md'
        self.ev.write_text('AUD-001-03 抽样复核记录：覆盖 5 条控制。\n', encoding='utf-8')
        # 默认矩阵：AUD-001 含 manual 断言；AUD-002 含非 manual 断言
        self.matrix = _matrix_with({
            'AUD-001': [{'id': 'AUD-001-01', 'kind': 'script', 'text': 'x'},
                        {'id': 'AUD-001-03', 'kind': 'manual', 'human_gate': 'sampling',
                         'text': 'y'}],
            'AUD-002': [{'id': 'AUD-002-01', 'kind': 'test', 'text': 'z'}],
        })
        self.matrix_path.write_text(json.dumps(self.matrix, ensure_ascii=False),
                                    encoding='utf-8')

    def _write_signoffs(self, entries):
        with self.signoffs_path.open('w', encoding='utf-8') as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + '\n')

    def _run(self, extra=None, acting='slow-is-fast'):
        env = dict(os.environ)
        env['GOV_ACTING_IDENTITY'] = acting
        cmd = [sys.executable, str(SCRIPT), '--signoffs', str(self.signoffs_path),
               '--matrix', str(self.matrix_path)]
        if extra:
            cmd += extra
        return subprocess.run(cmd, env=env, capture_output=True, text=True)

    def _run_env(self, extra, env_extra, acting='slow-is-fast'):
        env = dict(os.environ)
        env['GOV_ACTING_IDENTITY'] = acting
        env.update(env_extra)
        cmd = [sys.executable, str(SCRIPT), '--signoffs', str(self.signoffs_path),
               '--matrix', str(self.matrix_path)]
        if extra:
            cmd += extra
        return subprocess.run(cmd, env=env, capture_output=True, text=True)

    def _matrix_after(self):
        return json.loads(self.matrix_path.read_text(encoding='utf-8'))

    # ---- dry-run 不改动文件 ----
    def test_dry_run_does_not_mutate(self):
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev)])
        before = self.matrix_path.read_text(encoding='utf-8')
        r = self._run([])  # dry-run
        self.assertEqual(r.returncode, 0)
        self.assertIn('DRY-RUN', r.stdout)
        after = self.matrix_path.read_text(encoding='utf-8')
        self.assertEqual(before, after)  # 文件未动

    # ---- 合法签署 apply 后写入 signoff 字段 ----
    def test_apply_valid_writes_signoff(self):
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev)])
        r = self._run(['--apply', '--by', 'bob'])
        self.assertEqual(r.returncode, 0, r.stderr)
        m = self._matrix_after()
        a = [x for x in m['issues']['AUD-001']['assertions']
             if x['id'] == 'AUD-001-03'][0]
        self.assertIn('signoff', a)
        self.assertEqual(a['signoff']['by'], 'alice')
        self.assertEqual(a['signoff']['role'], 'independent-reviewer')
        self.assertEqual(a['signoff']['date'], '2026-11-01')
        self.assertEqual(a['signoff']['ref'], str(self.ev))
        self.assertEqual(a['signoff']['applied_by'], 'bob')
        # #6 审计增强字段
        self.assertIn('review_agent', a['signoff'])
        self.assertIn('flipped_at', a['signoff'])

    # ---- 失败关闭：各类非法条目整批中止 ----
    def test_self_sign_aborts(self):
        # reviewer==acting
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev, reviewer='carol')])
        r = self._run(['--apply', '--by', 'bob'], acting='carol')
        self.assertEqual(r.returncode, 2)
        self.assertIn('ABORT', r.stdout)
        self.assertNotIn('signoff',
                          self._matrix_after()['issues']['AUD-001']['assertions'][1])

    def test_bad_role_aborts(self):
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev, role='foo')])
        r = self._run(['--apply', '--by', 'bob'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('bad_role', r.stdout)

    def test_not_approved_aborts(self):
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev, verdict='needs-work')])
        r = self._run(['--apply', '--by', 'bob'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('not_approved', r.stdout)

    def test_evidence_missing_aborts(self):
        e = _valid_entry('AUD-001-03', self.ev)
        e['evidence_refs'] = [str(Path(self.tmp) / 'nope.md')]
        e['evidence_hash'] = _ev_hash(e['evidence_refs'])
        self._write_signoffs([e])
        r = self._run(['--apply', '--by', 'bob'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('evidence_missing', r.stdout)

    def test_hash_mismatch_aborts(self):
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev)])
        # 签完再改证据内容 → 哈希不符
        self.ev.write_text('篡改后的证据内容。\n', encoding='utf-8')
        r = self._run(['--apply', '--by', 'bob'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('evidence_hash_mismatch', r.stdout)

    def test_unknown_assertion_aborts(self):
        self._write_signoffs([_valid_entry('NOPE-999', self.ev)])
        r = self._run(['--apply', '--by', 'bob'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('unknown_assertion', r.stdout)

    def test_not_manual_aborts(self):
        # 签署指向非 manual 断言（AUD-002-01 是 test）
        self._write_signoffs([_valid_entry('AUD-002-01', self.ev)])
        r = self._run(['--apply', '--by', 'bob'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('not_manual', r.stdout)

    # ---- apply 必须带 --by ----
    def test_apply_requires_by(self):
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev)])
        r = self._run(['--apply'])
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('signoff',
                         self._matrix_after()['issues']['AUD-001']['assertions'][1])

    # ---- 混合：一条合法 + 一条非法 → 整批中止，合法那条也不写 ----
    def test_mixed_atomic_abort(self):
        ok = _valid_entry('AUD-001-03', self.ev, reviewer='alice')
        bad = _valid_entry('AUD-001-03', self.ev, reviewer='carol')  # 自签
        self._write_signoffs([ok, bad])
        r = self._run(['--apply', '--by', 'bob'], acting='carol')
        self.assertEqual(r.returncode, 2)
        # 合法那条也不该被写（原子）
        self.assertNotIn('signoff',
                         self._matrix_after()['issues']['AUD-001']['assertions'][1])

    # ---- 空 jsonl ----
    def test_empty_signoffs_exits_clean(self):
        self._write_signoffs([])
        r = self._run([])
        self.assertEqual(r.returncode, 0)
        self.assertIn('NO SIGNINGS', r.stdout)

    # ---- validate_entry 单元 ----
    def test_validate_entry_unit(self):
        self.assertTrue(app.validate_entry(
            _valid_entry('AUD-001-03', self.ev), 'slow-is-fast', self.matrix)[0])
        self.assertFalse(app.validate_entry(
            _valid_entry('AUD-001-03', self.ev, reviewer='x'), 'x', self.matrix)[0])

    # ---- #6 review-agent 绑定（opt-in via GOV_REVIEW_AGENT） ----
    def test_review_agent_opt_in_disabled_keeps_old_behavior(self):
        # 不设 GOV_REVIEW_AGENT：维持原行为，--by 任意值即可
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev)])
        r = self._run_env(['--apply', '--by', 'bob'], {})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('CLOSED', r.stdout)

    def test_review_agent_binding_ok(self):
        # GOV_REVIEW_AGENT 设置且 --by 匹配、且 ≠ 作者：翻转成功
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev)])
        r = self._run_env(
            ['--apply', '--by', 'reviewbot'],
            {'GOV_REVIEW_AGENT': 'reviewbot', 'GOV_AUTHOR_IDENTITY': 'hy3'})
        self.assertEqual(r.returncode, 0, r.stderr)
        m = self._matrix_after()
        a = [x for x in m['issues']['AUD-001']['assertions']
             if x['id'] == 'AUD-001-03'][0]
        self.assertEqual(a['signoff']['review_agent'], 'reviewbot')

    def test_review_agent_binding_executor_mismatch_aborts(self):
        # --by 不等于 GOV_REVIEW_AGENT：拒绝
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev)])
        r = self._run_env(
            ['--apply', '--by', 'bob'],
            {'GOV_REVIEW_AGENT': 'reviewbot'})
        self.assertEqual(r.returncode, 2)
        self.assertIn('executor_not_review_agent', r.stdout)

    def test_review_agent_is_author_rejected(self):
        # review-agent 与作者身份相同：拒绝（防自批）
        self._write_signoffs([_valid_entry('AUD-001-03', self.ev)])
        r = self._run_env(
            ['--apply', '--by', 'reviewbot'],
            {'GOV_REVIEW_AGENT': 'reviewbot', 'GOV_AUTHOR_IDENTITY': 'reviewbot'})
        self.assertEqual(r.returncode, 2)
        self.assertIn('review_agent_is_author', r.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
