# -*- coding: utf-8 -*-
"""端到端：Owner 工作清单里那条命令链，必须真的能跑通。

`governance/owner_worklist.md` 给 Owner 的模板是：
    accept-evidence -> record_signoff -> apply --dry-run -> apply --by -> 重生成清单

此前每一段都有单测，但**没有一条测试把它们串起来**。模板写错一个参数、
某一步的路径约定对不上、或者清单投影没反映签署——Owner 照着做到一半才发现，
比不给清单更糟。这条用例就是"文档里的命令必须真的可执行"。

全程在临时目录、用合成主体（alice/builder），不产生任何真实签署，
不触碰仓库的 governance/signoffs.jsonl。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')


def _policy():
    return {
        'version': '1.0',
        'trail_path': 'evidence/audit/trail.jsonl',
        'gate_audit_path': 'evidence/audit/gate.jsonl',
        'quarantine_dir': 'evidence/audit/quarantine',
        'sources': [
            {'name': 'gov-run', 'writer': 'test',
             'event_types': ['gov.check.completed']},
            {'name': 'gov-verify', 'writer': 'test',
             'event_types': ['gov.trail.verified', 'gov.trail.finding']},
            {'name': 'gov-evidence', 'writer': 'test',
             'event_types': ['gov.evidence.registered']},
        ],
        'retention': {'gov.check.completed': 3650, 'gov.trail.verified': 3650,
                      'gov.trail.finding': 3650, 'gov.evidence.registered': 3650},
        'evidence_retention': {'evidence': 3650},
        'check_args': {},
    }


def _matrix():
    return {'issues': {
        'AUD-001': {
            'severity': 'P0', 'criteria': 'x',
            'close_condition': '提交覆盖率报告与人工抽样复核记录',
            'assertions': [
                {'id': 'AUD-001-01', 'kind': 'script', 'text': '自动检查'},
                {'id': 'AUD-001-03', 'kind': 'manual',
                 'human_gate': 'sampling_review',                  'text': '人工抽样复核记录'},
            ]}},
    }


def _run(cmd, cwd, env_extra=None):
    env = dict(os.environ)
    env['GOV_ACTING_IDENTITY'] = 'builder'
    env.update(env_extra or {})
    return subprocess.run([sys.executable, *cmd], cwd=str(cwd), env=env,
                          capture_output=True, text=True)


def out(r):
    return r.stdout + r.stderr


class OwnerChainE2ETests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _write(self.root / 'governance' / 'acceptance_matrix.json', _matrix())
        _write(self.root / 'governance' / 'audit_policy.json', _policy())
        _write(self.root / 'governance' / 'quality_baseline.json',
               {'exceptions': [{'id': 'EXC-01', 'expires': '2027-01-31'}]})
        self.ev = self.root / 'evidence' / 'AUD-001-03_sampling.md'
        self.ev.parent.mkdir(parents=True, exist_ok=True)
        self.ev.write_text('抽样复核：覆盖 5 条控制，结论一致。\n', encoding='utf-8')

    def _matrix(self):
        return json.loads((self.root / 'governance' / 'acceptance_matrix.json')
                          .read_text(encoding='utf-8'))

    def test_full_chain_from_worklist_template(self):
        # 步骤 0：登记证据（清单模板第一行）
        r = _run([str(ROOT / 'scripts' / 'gov_run.py'), '--root', str(self.root),
                  '--accept-evidence', '--by', 'alice',
                  '--reason', '端到端演练：登记抽样证据'], self.root)
        self.assertEqual(r.returncode, 0, out(r))

        # 步骤 1：记录独立复核签署（reviewer 必须 ≠ 执行主体 builder）
        r = _run([str(ROOT / 'scripts' / 'record_signoff.py'),
                  '--assertion-id', 'AUD-001-03',
                  '--reviewer', 'alice',
                  '--role', 'independent-reviewer',
                  '--verdict', 'approved',
                  '--evidence', str(self.ev),
                  '--basis', '逐条核对 5 条控制与证据，结论一致',
                  '--store', str(self.root / 'governance' / 'signoffs.jsonl')],
                 self.root)
        self.assertEqual(r.returncode, 0, out(r))

        # 步骤 2：dry-run 投影，不动矩阵
        before = self._matrix()
        r = _run([str(ROOT / 'scripts' / 'apply_signoffs.py'),
                  '--signoffs', str(self.root / 'governance' / 'signoffs.jsonl'),
                  '--matrix', str(self.root / 'governance' / 'acceptance_matrix.json')],
                 self.root, {'GOV_ACTING_IDENTITY': 'builder'})
        self.assertEqual(r.returncode, 0, out(r))
        self.assertEqual(self._matrix(), before, 'dry-run 不应改动矩阵')

        # 步骤 3：apply 落盘
        r = _run([str(ROOT / 'scripts' / 'apply_signoffs.py'),
                  '--signoffs', str(self.root / 'governance' / 'signoffs.jsonl'),
                  '--matrix', str(self.root / 'governance' / 'acceptance_matrix.json'),
                  '--apply', '--by', 'builder'],
                 self.root, {'GOV_ACTING_IDENTITY': 'builder'})
        self.assertEqual(r.returncode, 0, out(r))
        a = [x for x in self._matrix()['issues']['AUD-001']['assertions']
             if x['id'] == 'AUD-001-03'][0]
        self.assertIn('signoff', a, 'apply 后断言必须带 signoff 字段')
        # 矩阵里 reviewer 存在 `by` 字段（历史命名），role 单独存
        self.assertEqual(a['signoff']['by'], 'alice')
        self.assertEqual(a['signoff']['role'], 'independent-reviewer')
        self.assertEqual(a['signoff']['applied_by'], 'builder')

        # 步骤 4：重生成清单 -> 该条必须出现在「已签署」
        r = _run([str(ROOT / 'scripts' / 'export_owner_worklist.py'),
                  '--root', str(self.root)], self.root)
        self.assertEqual(r.returncode, 0, out(r))
        text = (self.root / 'governance' / 'owner_worklist.md').read_text(encoding='utf-8')
        self.assertIn('### 已签署', text)
        self.assertIn('alice', text)
        self.assertIn('已签 1 ／ 未签 0', text)

        # 步骤 5：清单自检必须绿（模板最后一行）
        r = _run([str(ROOT / 'scripts' / 'export_owner_worklist.py'),
                  '--root', str(self.root), '--check'], self.root)
        self.assertEqual(r.returncode, 0, out(r))

    def test_self_sign_is_blocked(self):
        # 模板里"Agent 不得代签"不是口号：reviewer == 执行主体直接拒
        r = _run([str(ROOT / 'scripts' / 'record_signoff.py'),
                  '--assertion-id', 'AUD-001-03',
                  '--reviewer', 'builder',
                  '--role', 'independent-reviewer',
                  '--verdict', 'approved',
                  '--evidence', str(self.ev),
                  '--basis', '我自己看了觉得没问题所以签了',
                  '--store', str(self.root / 'governance' / 'signoffs.jsonl')],
                 self.root)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('禁止自签', out(r))
        self.assertFalse((self.root / 'governance' / 'signoffs.jsonl').exists())

    def test_apply_requires_independent_reviewer(self):
        # 签署人用了非独立角色 -> apply 必须整批中止
        r = _run([str(ROOT / 'scripts' / 'record_signoff.py'),
                  '--assertion-id', 'AUD-001-03', '--reviewer', 'alice',
                  '--role', 'independent-reviewer', '--verdict', 'approved',
                  '--evidence', str(self.ev),
                  '--basis', '核对后认为满足要求，同意关闭该断言',
                  '--store', str(self.root / 'governance' / 'signoffs.jsonl')],
                 self.root)
        self.assertEqual(r.returncode, 0, out(r))
        # 篡改 role 成非法值：apply 侧必须拒绝
        p = self.root / 'governance' / 'signoffs.jsonl'
        e = json.loads(p.read_text(encoding='utf-8').splitlines()[0])
        e['role'] = 'self'
        p.write_text(json.dumps(e, ensure_ascii=False) + '\n', encoding='utf-8')
        before = self._matrix()
        r = _run([str(ROOT / 'scripts' / 'apply_signoffs.py'),
                  '--signoffs', str(p),
                  '--matrix', str(self.root / 'governance' / 'acceptance_matrix.json'),
                  '--apply', '--by', 'builder'],
                 self.root)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self._matrix(), before, '非法签署必须整批中止、零改动')


if __name__ == '__main__':
    unittest.main(verbosity=2)
