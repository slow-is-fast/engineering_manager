# -*- coding: utf-8 -*-
"""ALC-01 / DG-01 的**生产路径**用例（scripts/gov_run.py）。

与 `test_executor_negative.py` 的分界：
  - 那边测的是模块**自身语义**（ProvenanceRegistry 会不会认出来、DataGate
    删了还能不能读）。模块对了，不代表它被接进门禁了。
  - 这边测的是**接线**：检查有没有真的记进流、链坏了会不会拒绝写、
    必需检查缺席能不能被发现、证据被改/被删会不会红。

这层用例的存在理由，就是"测试绿不等于控制生效"——模块全绿但没人调用，
是这套规范最想防的那种自欺。
"""
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.gov_run as gov  # noqa: E402
from executor.audit import AuditLog  # noqa: E402

DAY = 86400
OK_SCRIPT = 'scripts/ok_check.py'
BAD_SCRIPT = 'scripts/bad_check.py'


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf8')


def _mkroot(tmpdir, *, retention_days=180, extra_evidence=0):
    """造一个最小可运行的治理根目录。"""
    root = Path(tmpdir)
    # 带 --fail 时退出 1：用来验证"参数来自策略，不来自调用方"
    _write(root / OK_SCRIPT,
           'import sys\nsys.exit(1 if "--fail" in sys.argv else 0)\n')
    _write(root / BAD_SCRIPT, 'import sys\nsys.exit(3)\n')

    policy = {
        'version': '1.0',
        'trail_path': 'evidence/audit/trail.jsonl',
        'gate_audit_path': 'evidence/audit/gate.jsonl',
        'quarantine_dir': 'evidence/audit/quarantine',
        'sources': [
            {'name': 'gov-run', 'writer': 'test',
             'event_types': ['gov.check.completed']},
            {'name': 'gov-verify', 'writer': 'test',
             'event_types': ['gov.trail.verified', 'gov.trail.finding']},
            # 每个会被写入的来源都必须在策略里声明——漏一个，
            # 它写下的每条事件都会被判为"未登记来源"。这是刻意的：
            # 策略是白名单，不是"没写就默认允许"。
            {'name': 'gov-evidence', 'writer': 'test',
             'event_types': ['gov.evidence.registered']},
        ],
        'retention': {
            'gov.check.completed': retention_days,
            'gov.trail.verified': retention_days,
            'gov.trail.finding': 365,
            'gov.evidence.registered': 365,
        },
        'evidence_retention': {'evidence': 365, 'test-artifact': 90},
    }
    _write(root / 'governance' / 'audit_policy.json',
           json.dumps(policy, ensure_ascii=False, indent=2))
    _write(root / 'governance' / 'quality_baseline.json',
           json.dumps({'required_checks': [OK_SCRIPT]}, ensure_ascii=False))

    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    for i in range(extra_evidence + 1):
        _write(root / 'evidence' / f'ev{i}_{stamp}.md', f'证据 {i}\n')

    # 台账先按当前磁盘状态登记
    code, msgs = gov.accept_evidence(root=root, by='tester', reason='setup')
    assert code == gov.EXIT_OK, msgs
    return root


def _complete_run(root, run_id):
    codes = [gov.run_check(n, root=root, run_id=run_id) for n in
             gov.baseline_of(root)['required_checks']]
    assert all(c == gov.EXIT_OK for c, _ in codes), codes


def _append_raw(log, event_type, source, ts, **fields):
    """手写一条链上自洽的事件（用于构造超期/伪造来源场景）。"""
    prev = log._last_hash()
    seq = len(log._lines()) + 1
    e = {'seq': seq, 'event_id': f'raw-{seq}', 'timestamp': ts,
         'event_type': event_type, 'source': source, **fields,
         'prev_hash': prev}
    e['hash'] = AuditLog._hash(e)
    with log.path.open('a', encoding='utf8') as f:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
    return e


class GovRunCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='aasegs-gov-')
        self.root = _mkroot(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.trail = self.root / 'evidence' / 'audit' / 'trail.jsonl'

    def test_GOV_01_check_recorded_with_source(self):
        code, msgs = gov.run_check(OK_SCRIPT, root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_OK, msgs)
        ev = AuditLog(self.trail).read('gov.check.completed')
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]['source'], 'gov-run')
        self.assertEqual(ev[0]['check'], OK_SCRIPT)
        self.assertEqual(ev[0]['verdict'], 'ok')
        self.assertEqual(ev[0]['run_id'], 'r1')
        ok, errors = AuditLog(self.trail).verify()
        self.assertTrue(ok, errors)

    def test_GOV_02_failed_check_still_recorded(self):
        """失败了也要留痕：只在成功时记账，出事时就查不到任何东西。"""
        # 它会失败，所以不能进默认基线（否则 _complete_run 过不去）；
        # 这里单独把它加进基线，测的是"失败仍记账"。
        base = gov.baseline_of(self.root)
        base['required_checks'].append(BAD_SCRIPT)
        _write(self.root / 'governance' / 'quality_baseline.json',
               json.dumps(base, ensure_ascii=False))
        code, msgs = gov.run_check(BAD_SCRIPT, root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_CHECK_FAILED, msgs)
        ev = AuditLog(self.trail).read('gov.check.completed')
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]['verdict'], 'failed')
        self.assertEqual(ev[0]['exit_code'], 3)

    def test_GOV_03_refuses_check_outside_baseline(self):
        """能让调用方随意指定"写什么进流"，这条流就不值钱了。"""
        code, msgs = gov.run_check('scripts/not_required.py', root=self.root,
                                   run_id='r1')
        self.assertEqual(code, gov.EXIT_REFUSED, msgs)
        # 拒绝的意思是"一个字都没写进去"，不是"写了但返回非零"
        self.assertEqual(AuditLog(self.trail).read('gov.check.completed'), [])

    def test_GOV_20_check_args_come_from_policy_not_caller(self):
        """门禁强度由治理配置决定。

        CI 若能自己传 `--enforce` / `--expect-deny`，它就能悄悄用弱模式跑一遍、
        照样记账成 ok——"跑了、也绿了、但不是那个档位"的假绿最难发现。
        所以参数只从 audit_policy.check_args 读，调用方无权指定。
        """
        pol = gov.policy_of(self.root)
        pol['check_args'] = {OK_SCRIPT: [['--fail']]}
        _write(self.root / 'governance' / 'audit_policy.json',
               json.dumps(pol, ensure_ascii=False))

        code, msgs = gov.run_check(OK_SCRIPT, root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_CHECK_FAILED, msgs)   # 参数生效了
        ev = AuditLog(self.trail).read('gov.check.completed')[0]
        self.assertEqual(ev['args'], [['--fail']])            # 且留痕
        self.assertEqual(ev['invocations'], 1)

    def test_GOV_04_broken_chain_refuses_append_and_quarantines(self):
        """链断了不许往上接新事件，坏段必须原样交出来。"""
        gov.run_check(OK_SCRIPT, root=self.root, run_id='r1')
        before = len(AuditLog(self.trail)._lines())
        lines = self.trail.read_text(encoding='utf8').splitlines(True)
        tampered = json.loads(lines[0])
        tampered['verdict'] = 'forged'
        lines[0] = json.dumps(tampered, ensure_ascii=False) + '\n'
        self.trail.write_text(''.join(lines), encoding='utf8')

        code, msgs = gov.run_check(OK_SCRIPT, root=self.root, run_id='r2')
        self.assertEqual(code, gov.EXIT_TRAIL_UNUSABLE, msgs)
        self.assertIn('审计流损坏', msgs[0])
        self.assertIn('hash', msgs[0])              # 说清楚坏在哪
        qdir = self.root / 'evidence' / 'audit' / 'quarantine'
        files = list(qdir.glob('*.jsonl'))
        self.assertEqual(len(files), 1)
        self.assertIn('forged', files[0].read_text(encoding='utf8'))
        # 拒绝追加：流长度没变（坏链上多写一条，等于把问题盖住）
        self.assertEqual(len(AuditLog(self.trail)._lines()), before)


class GovRunVerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='aasegs-govv-')
        self.root = _mkroot(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.trail = self.root / 'evidence' / 'audit' / 'trail.jsonl'

    def test_GOV_05_verify_without_run_id_refuses(self):
        """判不了就拒绝，不要"跳过这项检查"——跳过等于放行。"""
        _complete_run(self.root, 'r1')
        code, msgs = gov.verify(root=self.root, run_id=None)
        self.assertEqual(code, gov.EXIT_INCOMPLETE, msgs)
        self.assertIn('run_id', msgs[0])

    def test_GOV_06_missing_check_is_caught(self):
        """必需检查没跑 → 红。不跑就算过，门禁可以静默缺席。"""
        gov.run_check(OK_SCRIPT, root=self.root, run_id='r1')
        # 基线多一项，但没人跑它
        base = gov.baseline_of(self.root)
        base['required_checks'].append(BAD_SCRIPT)
        _write(self.root / 'governance' / 'quality_baseline.json',
               json.dumps(base, ensure_ascii=False))
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_INCOMPLETE, msgs)
        self.assertIn(BAD_SCRIPT, msgs[0])

    def test_GOV_07_complete_run_passes(self):
        _complete_run(self.root, 'r1')
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_OK, msgs)

    def test_GOV_08_missing_trail_fails(self):
        """缺流当"没问题"是最贵的一种假绿。"""
        self.trail.unlink()                       # 连登记事件一起没了
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_TRAIL_UNUSABLE, msgs)
        # 钉住是哪道闸门拦的：只断言退出码的话，把"缺流"这一道关掉，
        # 后面的链校验也会拦出同样的码，用例照样绿——变异逃逸。
        self.assertIn('审计流不存在', msgs[0])

    def test_GOV_09_undeclared_source_flagged(self):
        _complete_run(self.root, 'r1')
        log = AuditLog(self.trail)
        log.append('gov.check.completed', source='ghost', run_id='r1',
                   check=OK_SCRIPT, verdict='ok', exit_code=0)
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_PROVENANCE, msgs)
        self.assertIn('undeclared_source', msgs[0])

    def test_GOV_10_event_without_source_flagged(self):
        _complete_run(self.root, 'r1')
        AuditLog(self.trail).append('gov.check.completed', run_id='r1',
                                    check=OK_SCRIPT, verdict='ok')
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_PROVENANCE, msgs)
        self.assertIn('missing_source', msgs[0])

    def test_GOV_11_expired_event_flagged(self):
        _complete_run(self.root, 'r1')
        _append_raw(AuditLog(self.trail), 'gov.check.completed', 'gov-run',
                    time.time() - 400 * DAY, run_id='r1', check=OK_SCRIPT,
                    verdict='ok')
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_RETENTION, msgs)
        self.assertIn('EXPIRED', msgs[0])


class GovEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='aasegs-gove-')
        self.root = _mkroot(self.tmp, extra_evidence=1)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ledger = self.root / 'governance' / 'evidence_ledger.json'

    def _ev(self, i):
        return sorted((self.root / 'evidence').glob(f'ev{i}_*.md'))[0]

    def test_GOV_12_registered_evidence_passes(self):
        _complete_run(self.root, 'r1')
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_OK, msgs)

    def test_GOV_13_modified_evidence_fails(self):
        """证据被悄悄改一个字节，台账哈希就对不上。"""
        _complete_run(self.root, 'r1')
        p = self._ev(0)
        p.write_text('被改过的内容\n', encoding='utf8')
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_EVIDENCE, msgs)
        self.assertTrue(any('哈希不符' in m for m in msgs), msgs)

    def test_GOV_14_unregistered_evidence_fails(self):
        """不登记就出现的证据，本来就不该被当成证据。"""
        _complete_run(self.root, 'r1')
        _write(self.root / 'evidence' / 'smuggled_20260101T000000Z.md',
               '偷偷加的\n')
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_EVIDENCE, msgs)
        self.assertTrue(any('未登记' in m for m in msgs), msgs)

    def test_GOV_15_unapproved_deletion_fails(self):
        """台账里有、磁盘上没有、又没批准记录 → 就是未经批准的删除。"""
        _complete_run(self.root, 'r1')
        self._ev(0).unlink()
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_EVIDENCE, msgs)
        self.assertTrue(any('未经批准的删除' in m for m in msgs), msgs)

    def test_GOV_16_approved_deletion_passes_but_resurrect_fails(self):
        """有批准的删除放行；删除后再出现必须红。"""
        _complete_run(self.root, 'r1')
        target = self._ev(0)
        rel = target.relative_to(self.root).as_posix()
        target.unlink()
        ledger = json.loads(self.ledger.read_text(encoding='utf8'))
        ledger['deletions'] = [{'id': rel,
                                'approval': {'approver': 'owner',
                                             'reason': '超过保留期'}}]
        self.ledger.write_text(json.dumps(ledger, ensure_ascii=False),
                               encoding='utf8')

        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_OK, msgs)

        # 删除后再现
        _write(target, '换皮回来\n')
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_EVIDENCE, msgs)
        self.assertTrue(any('删除后再现' in m for m in msgs), msgs)

    def test_GOV_17_deletion_without_approver_rejected(self):
        """删除登记没有批准人 → 登记本身不成立，不是空操作。"""
        _complete_run(self.root, 'r1')
        target = self._ev(0)
        rel = target.relative_to(self.root).as_posix()
        target.unlink()
        ledger = json.loads(self.ledger.read_text(encoding='utf8'))
        ledger['deletions'] = [{'id': rel, 'approval': {}}]
        self.ledger.write_text(json.dumps(ledger, ensure_ascii=False),
                               encoding='utf8')
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_EVIDENCE, msgs)
        self.assertTrue(any('删除登记不成立' in m for m in msgs), msgs)

    def test_GOV_18_accept_requires_signature(self):
        """无署名的登记等于没人负责。"""
        code, msgs = gov.accept_evidence(root=self.root, by=None, reason='x')
        self.assertEqual(code, gov.EXIT_REFUSED, msgs)
        code, msgs = gov.accept_evidence(root=self.root, by='tester',
                                         reason=None)
        self.assertEqual(code, gov.EXIT_REFUSED, msgs)

    def test_GOV_19_accept_cannot_resurrect_deleted_evidence(self):
        """重新登记等于绕过 resurrect 的双人隔离，必须挡。"""
        target = self._ev(0)
        rel = target.relative_to(self.root).as_posix()
        target.unlink()
        ledger = json.loads(self.ledger.read_text(encoding='utf8'))
        ledger['deletions'] = [{'id': rel,
                                'approval': {'approver': 'owner'}}]
        self.ledger.write_text(json.dumps(ledger, ensure_ascii=False),
                               encoding='utf8')
        # 关键场景：文件被放回磁盘，然后"顺手重新登记一下"——
        # 这就是绕过 resurrect 双人隔离的最短路径。
        _write(target, '复活血\n')
        code, msgs = gov.accept_evidence(root=self.root, by='someone',
                                         reason='悄悄复活血')
        self.assertEqual(code, gov.EXIT_REFUSED, msgs)
        self.assertIn('resurrect', msgs[0])

    def test_GOV_20_stale_evidence_fails_verify(self):
        """证据超期必须被 gov_run --verify 自身抓出（不能只靠 RVF-01 兜底）。
        钉死 verify_evidence 里的 sweep_retention 调用——删掉它就不会报警。
        做法：保留期不动，把某条证据的 created_at 拨到远古使其超期。"""
        import datetime
        _complete_run(self.root, 'r1')
        ledger = json.loads(self.ledger.read_text(encoding='utf8'))
        ledger['items'][0]['created_at'] = datetime.datetime(2000, 1, 1).timestamp()
        self.ledger.write_text(json.dumps(ledger, ensure_ascii=False),
                               encoding='utf8')
        code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_EVIDENCE, msgs)
        self.assertTrue(any('超期' in m for m in msgs), msgs)

    def test_GOV_21_leaky_tombstone_fails(self):
        """删除后内容仍可读 = 深层泄漏。verify_evidence 必须标红——这条检查
        独立于 DataGate 当前是否正确（防御它未来退化）。模拟一个会泄漏的
        闸门，确认检查本身会拦截，从而钉死 verify_evidence 第 261 行的判定。"""
        from unittest import mock
        from executor.datagate import DataGate

        _complete_run(self.root, 'r1')
        target = self._ev(0)
        rel = target.relative_to(self.root).as_posix()
        target.unlink()
        ledger = json.loads(self.ledger.read_text(encoding='utf8'))
        ledger['deletions'] = [{'id': rel,
                                'approval': {'approver': 'owner',
                                             'reason': '超过保留期'}}]
        self.ledger.write_text(json.dumps(ledger, ensure_ascii=False),
                               encoding='utf8')

        class _LeakyGate(DataGate):
            def get(self, item_id):
                r = super().get(item_id)
                if r.get('state') == 'TOMBSTONE':
                    r['content'] = '泄露的内容'
                return r

        with mock.patch.object(gov, 'DataGate', _LeakyGate):
            code, msgs = gov.verify(root=self.root, run_id='r1')
        self.assertEqual(code, gov.EXIT_EVIDENCE, msgs)
        self.assertTrue(any('删除后仍能从出口读到内容' in m for m in msgs),
                        msgs)


if __name__ == '__main__':
    unittest.main(verbosity=2)
