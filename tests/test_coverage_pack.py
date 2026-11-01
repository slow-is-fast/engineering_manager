# -*- coding: utf-8 -*-
"""AUD-001-03 复核材料的守卫用例（scripts/export_coverage_pack.py）。

钉的不是"文档长得好看"，是四件容易退化成假绿的事：

1. 覆盖率统计把"字符串里有引用"和"引用能解析"分开算——合成一个数，
   90.9% 这种数字就会冒充 100%；
2. 悬空引用必须被列出来（现有校验器只查控制目录侧，规则侧没人管）；
3. 抽样可复现：同输入两次必须同一批，且不是字母序；
4. 指纹必须覆盖抽样结果——只改条数时，若指纹不含 picks，材料换了样本
   而 --check 仍然通过，那就是"算出来却没人看"的又一例。
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.export_coverage_pack as pack  # noqa: E402


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf8')


def _rule(rid, controls=None, tests=None, risk='P1'):
    return {'rule_id': rid, 'statement': f'{rid} 的条款原文。', 'requirement': 'MUST',
            'owner': 'governance_owner', 'risk_level': risk,
            'enforcement': {'type': 'technical', 'controls': controls or [], 'gap': None},
            'verification': {'tests': tests or []},
            'status': {'documented': True, 'configured': False, 'tested': False,
                       'verified': False, 'degraded': False, 'excepted': False},
            'exception_ref': None}


def _control(cid, test, status='tested'):
    return {'id': cid, 'requirement_ref': cid, 'owner': 'x', 'enforcer': 'y',
            'evidence': '证据文本', 'failure': '失败行为', 'test': test,
            'status': status, 'integration_evidence_uri': 'evidence/x.md',
            'source_ref': 'v1.1.1 §1', 'state': {'documented': True},
            'evidence_at': '2026-10-30'}


def _root(tmp, rules, controls, test_src=None):
    tmp = Path(tmp)
    _write(tmp / 'rule-registry.json',
           json.dumps({'rules': rules}, ensure_ascii=False))
    _write(tmp / 'control-catalog.yaml',
           json.dumps({'controls': controls}, ensure_ascii=False))
    _write(tmp / 'tests' / 'test_fixture.py',
           test_src if test_src is not None
           else 'def test_t_aa_01_ok(self):\n    assert True\n')
    return tmp


class CoveragePackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='aasegs-pack-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_pack_separates_string_refs_from_resolvable_refs(self):
        """'写了引用' 与 '引用能解析' 必须是两个数，否则数字会冒充覆盖率。"""
        root = _root(self.tmp,
                     [_rule('R-01', ['AA-01'], ['T-AA-01']),
                      _rule('R-02', ['AA-02'], ['T-GHOST-99'])],
                     [_control('AA-01', 'T-AA-01'), _control('AA-02', 'T-AA-02')])
        stats, rows, _ = pack.coverage(*pack._load(root), pack._test_index(root), root)
        self.assertEqual(stats['rules'], 2)
        self.assertEqual(stats['rules_with_tests'], 2)
        self.assertEqual(stats['rules_tests_all_resolve'], 1, stats)
        missing = {r['rule']: r['missing'] for r in rows}
        self.assertEqual(missing['R-02'], ['T-GHOST-99'])

    def test_pack_lists_dangling_rule_refs(self):
        """规则侧的悬空引用没有人校验——这里至少要让它在材料里出现。"""
        root = _root(self.tmp,
                     [_rule('R-01', [], ['T-NOWHERE-01'])],
                     [_control('AA-01', 'T-AA-01')])
        text, fp, d, n = pack.build(root)
        self.assertEqual(n, 1)
        self.assertEqual(len(d['dangling_tests']), 1)
        self.assertIn('T-NOWHERE-01', text)
        self.assertIn('悬空用例引用（1 处）', text)

    def test_pack_sample_is_reproducible_and_not_alphabetical(self):
        ids = [f'R-{i:02d}' for i in range(12)]
        rows = [{'rule': i, 'risk': 'P1', 'controls': [], 'tests': [], 'missing': []}
                for i in ids]
        a = [r['rule'] for r in pack.sample(rows, 5)]
        b = [r['rule'] for r in pack.sample(rows, 5)]
        self.assertEqual(a, b, '同输入两次抽样结果不同——不可复现的样本不能当复核材料')
        import hashlib
        expect = sorted(ids, key=lambda x: hashlib.sha256(x.encode()).hexdigest())[:5]
        self.assertEqual(a, expect)
        self.assertNotEqual(a, sorted(ids)[:5], '抽样退化成了字母序')

    def test_pack_fingerprint_covers_sample_set(self):
        """只改条数：材料换了样本，指纹必须跟着变。"""
        rules = [_rule(f'R-{i:02d}', [], []) for i in range(6)]
        root = _root(self.tmp, rules, [_control('AA-01', 'T-AA-01')])
        old = pack.SAMPLE_N
        try:
            pack.SAMPLE_N = 2
            _, fp_small, _, _ = pack.build(root)
            pack.SAMPLE_N = 4
            _, fp_big, _, _ = pack.build(root)
        finally:
            pack.SAMPLE_N = old
        self.assertNotEqual(fp_small, fp_big,
                            '抽样条数变了指纹没变——材料已过期但 --check 会说通过')

    def test_pack_check_red_when_registry_changes(self):
        rules = [_rule('R-01', ['AA-01'], ['T-AA-01'])]
        root = _root(self.tmp, rules, [_control('AA-01', 'T-AA-01')])
        out = root / 'pack.md'
        self.assertEqual(pack.main(['--root', str(root), '--out', str(out)]), 0)
        self.assertEqual(pack.main(['--root', str(root), '--out', str(out), '--check']), 0)
        # 注册表变了（多一条规则）→ 材料过期
        _write(root / 'rule-registry.json',
               json.dumps({'rules': rules + [_rule('R-02', [], [])]},
                          ensure_ascii=False))
        self.assertEqual(pack.main(['--root', str(root), '--out', str(out), '--check']), 1)

    def test_pack_check_red_when_material_missing(self):
        root = _root(self.tmp, [_rule('R-01', [], [])], [])
        rc = pack.main(['--root', str(root), '--out', str(root / 'ghost.md'), '--check'])
        self.assertEqual(rc, 1, '材料不存在却判了通过——缺东西当"没问题"是最贵的假绿')

    def test_pack_says_it_is_not_a_record(self):
        """这份材料的价值全在"它不替人下判断"，这句话不能被删掉。"""
        root = _root(self.tmp, [_rule('R-01', ['AA-01'], ['T-AA-01'])],
                     [_control('AA-01', 'T-AA-01')])
        text, _, _, _ = pack.build(root)
        self.assertIn('不是复核记录', text)
        self.assertIn('不产生任何签署', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
