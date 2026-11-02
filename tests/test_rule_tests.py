# -*- coding: utf-8 -*-
"""T-REF-03 规则侧用例引用校验器的守卫用例（scripts/check_rule_tests.py）。

钉的是四件容易退化成假绿的事：

1. 悬空引用必须红——这是本检查存在的全部理由。若它在"引用指不到东西"时
   仍然绿，那它就只是又一圈装饰。
2. 正向对照必须绿——只测红不测绿，等于不知道检查是会误报还是真的在工作。
   误报的下场通常不是被修正，而是被关掉。
3. 空转缺口必须红：`not_enforced` + `gap=null` 是"技术强制、无缺口"这句话
   最容易骗人的形态；写个空格糊过去同样算没写。
4. 真实仓库自检：本次修的 3 处改引用 + 6 条 gap 必须留在原地。否则下一次
   有人"顺手清理"就能把它们悄悄改回去，而没有任何门禁会响——这正是这批
   缺陷活了这么久的原因。
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

from scripts import check_rule_tests as crt  # noqa: E402


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf8', newline='\n')


def _rule(rid, tests=None, controls=None, gap=None, risk='P1'):
    return {'rule_id': rid, 'statement': f'{rid} 的条款原文。', 'requirement': 'MUST',
            'owner': 'governance_owner', 'risk_level': risk,
            'enforcement': {'type': 'technical', 'controls': controls or [], 'gap': gap},
            'verification': {'tests': tests if tests is not None else []},
            'status': {'documented': True, 'configured': False, 'tested': False,
                       'verified': False, 'degraded': False, 'excepted': False},
            'exception_ref': None}


def _control(cid, status='tested'):
    return {'id': cid, 'requirement_ref': cid, 'owner': 'x', 'enforcer': 'y',
            'evidence': '证据文本', 'failure': '失败行为',
            'test': 'T-AA-01', 'status': status,
            'state': {'documented': True, 'tested': status == 'tested'}}


def _root(tmp, rules, controls, test_src='def test_t_aa_01_ok(self):\n    assert True\n',
          workflow=None):
    tmp = Path(tmp)
    _write(tmp / 'rule-registry.json', json.dumps({'rules': rules}, ensure_ascii=False))
    _write(tmp / 'control-catalog.yaml', json.dumps({'controls': controls}, ensure_ascii=False))
    _write(tmp / 'tests' / 'test_fixture.py', test_src)
    if workflow is not None:
        _write(tmp / '.github' / 'workflows' / 'w.yml', workflow)
    return tmp


class RuleTestRefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='aasegs-tref03-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _kinds(self, findings):
        return [f['kind'] for f in findings]

    def test_dangling_ref_fails(self):
        """引用指不到任何用例 → 必须红。"""
        root = _root(self.tmp, [_rule('R-01', ['T-XX-99'])], [_control('C-01')])
        findings, err = crt.check(root)
        self.assertIsNone(err, err)
        self.assertIn('dangling_test_ref', self._kinds(findings))

    def test_method_ref_passes(self):
        """正向对照：引用能落到 tests/ 里的方法 → 绿。"""
        root = _root(self.tmp, [_rule('R-01', ['T-AA-01'])], [_control('C-01')])
        findings, err = crt.check(root)
        self.assertIsNone(err, err)
        self.assertEqual(findings, [])

    def test_workflow_step_ref_passes(self):
        """CI 步骤名（不是 def test_*）也算可解析——与 resolve_test 同口径。

        这类引用是弱证据：它证明"CI 里有这一步"，不证明"有一个单元用例"。
        弱就弱在明处，但不该被判成悬空——否则 T-VD-01b / T-CLOSE 会被误杀。
        """
        root = _root(self.tmp, [_rule('R-01', ['T-WF-01'])], [_control('C-01')],
                     workflow='      - name: "T-WF-01 something"\n')
        findings, err = crt.check(root)
        self.assertIsNone(err, err)
        self.assertEqual(findings, [])

    def test_not_enforced_without_gap_fails(self):
        """控制 not_enforced 而 gap 为 null → '技术强制、无缺口'是假的，必须红。"""
        root = _root(self.tmp, [_rule('R-01', ['T-AA-01'], ['C-09'], gap=None)],
                     [_control('C-09', status='not_enforced')])
        findings, err = crt.check(root)
        self.assertIsNone(err, err)
        self.assertIn('gap_silent', self._kinds(findings))

    def test_blank_gap_fails(self):
        """写个空格不是声明缺口。"""
        root = _root(self.tmp, [_rule('R-01', ['T-AA-01'], ['C-09'], gap='   ')],
                     [_control('C-09', status='not_enforced')])
        findings, err = crt.check(root)
        self.assertIsNone(err, err)
        self.assertIn('gap_blank', self._kinds(findings))

    def test_not_enforced_with_gap_passes(self):
        """正向对照：写了具体缺口 → 绿，检查不该逼人把缺口写成段子。"""
        root = _root(self.tmp, [_rule('R-01', ['T-AA-01'], ['C-09'],
                                      gap='需要第二人类主体，当前不可得。')],
                     [_control('C-09', status='not_enforced')])
        findings, err = crt.check(root)
        self.assertIsNone(err, err)
        self.assertEqual(findings, [])

    def test_enforced_control_needs_no_gap(self):
        """控制已被强制时，gap=null 是正常表达，不得误报。"""
        root = _root(self.tmp, [_rule('R-01', ['T-AA-01'], ['C-01'], gap=None)],
                     [_control('C-01', status='tested')])
        findings, err = crt.check(root)
        self.assertIsNone(err, err)
        self.assertEqual(findings, [])

    def test_missing_registry_fails_closed(self):
        """读不到注册表 → 不可判定即拒绝，不返回空 findings 冒充通过。"""
        findings, err = crt.check(self.tmp / 'nowhere')
        self.assertIsNone(findings)
        self.assertTrue(err)

    def test_real_repo_selfcheck(self):
        """真实仓库必须干净，且本次修的引用不能被"顺手清理"改回去。"""
        findings, err = crt.check(ROOT)
        self.assertIsNone(err, err)
        self.assertEqual(findings, [], f'规则侧引用不成立：{findings}')
        reg = {r['rule_id']: r for r in json.loads(
            (ROOT / 'rule-registry.json').read_text(encoding='utf8'))['rules']}
        # 3 处改引用：编号按控制目录实际 test 字段对齐，不是随手换一个能通过的值
        self.assertEqual(reg['GOV-01']['verification']['tests'], ['T-VD-01b'])
        self.assertEqual(reg['AASEGS-AGT-002']['verification']['tests'],
                         ['T-ID-01', 'T-VD-01b'])
        self.assertEqual(reg['GOV-03']['verification']['tests'], ['T-EVD-01', 'T-CLOSE'])
        # 7 处删悬空引用：删完可以变空，但不能换成另一个指不到东西的编号
        for rid in ('GOV-02', 'AASEGS-AGT-001', 'AASEGS-SEC-002', 'AASEGS-SUP-002'):
            self.assertEqual(reg[rid]['verification']['tests'], [], rid)
        self.assertEqual(reg['AASEGS-SEC-003']['verification']['tests'],
                         ['T-QA-01', 'T-QA-02'])
        # 6 条 gap：必须写着话，不能退回 null
        for rid in ('GOV-02', 'AASEGS-AGT-001', 'AASEGS-WFL-007',
                    'AASEGS-SEC-002', 'AASEGS-SEC-003', 'AASEGS-SUP-002'):
            self.assertTrue(str(reg[rid]['enforcement'].get('gap') or '').strip(), rid)


if __name__ == '__main__':
    unittest.main()
