# -*- coding: utf-8 -*-
"""`AUD-002-03` 六态报告的守卫用例（scripts/export_sixstate_report.py）。

这份报告是拿去给人下判断的，所以钉的不是"排版好看"，是四件会让它变成假话的事：

1. **"谁读这个字段"必须是扫出来的**，不能写死。写死的话，将来有人加了消费者，
   报告还在说"零读取"，而那句话正好是复核者要引用的结论。
2. **跨层撞名必须分开算。** `excepted` 同时被断言层的 `kind=excepted` 使用；
   宽正则会把它算成控制层 `state.excepted` 的消费者，制造"这个字段有人在读"的错觉。
3. **指纹必须对换行不敏感**——Windows 磁盘 CRLF、仓库/CI LF，这个坑本月已经踩过一次。
4. **报告里必须有"这是产物，不是复核记录"这句话。** 少了它，下一个人会把报告
   当成结论引用，而这条断言的全部要求恰恰是"由人下判断"。
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

from scripts import export_sixstate_report as six  # noqa: E402


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf8', newline='\n')


class ConsumerScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='aasegs-six-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_write_only_field_reports_no_reader(self):
        """只写不读 → 读取点为空。这正是 degraded 的处境。"""
        _write(self.tmp / 'scripts' / 'w.py',
               "def f(state):\n    state['degraded'] = True\n")
        defs, writes, reads, other = six._scan_consumers(self.tmp, 'degraded')
        self.assertEqual(len(writes), 1)
        self.assertEqual(reads, [], '只写的字段不该被扫出读取点')
        self.assertEqual(other, [])

    def test_reader_detected(self):
        """正向对照：真有人读就要扫出来。只测红不测绿，不知道检查是否在工作。"""
        _write(self.tmp / 'scripts' / 'r.py',
               "def f(state):\n    return state['verified'] is True\n")
        defs, writes, reads, other = six._scan_consumers(self.tmp, 'verified')
        self.assertEqual(len(reads), 1)

    def test_closure_excepted_is_other_layer(self):
        """closure.py 里的 excepted 是断言层，不能算控制层 state 的消费者。

        判据在源码里：那里的 `s` 来自 `self._assertion_state(a)`。
        """
        _write(self.tmp / 'executor' / 'closure.py',
               'def f(states):\n    return [s for s in states if s.get("excepted")]\n')
        defs, writes, reads, other = six._scan_consumers(self.tmp, 'excepted')
        self.assertEqual(reads, [], '断言层的 excepted 被误算成控制层读取')
        self.assertEqual(len(other), 1)

    def test_self_export_scripts_are_excluded(self):
        """报告自己不能算消费者，否则会自我指涉地"证明"这个字段有人读。"""
        _write(self.tmp / 'scripts' / 'export_owner_worklist.py',
               "X = ['excepted']\n")
        defs, writes, reads, other = six._scan_consumers(self.tmp, 'excepted')
        self.assertEqual(defs + writes + reads + other, [])


class RealRepoReportTests(unittest.TestCase):
    def test_report_is_in_sync(self):
        """真实仓库里报告必须与数据一致（数据变了报告没重生成 → 红）。"""
        m = six.main(['--check'])
        self.assertEqual(m, 0, '六态报告已过期——python scripts/export_sixstate_report.py')

    def test_report_declares_it_is_not_a_record(self):
        """报告不是复核记录，这句话必须在。"""
        text = (ROOT / 'governance' / 'sixstate_report.md').read_text(encoding='utf8')
        self.assertIn('这是产物，不是复核记录', text)

    def test_zero_states_are_reported_consistently(self):
        """"从未取值为真的状态"这一行必须与数据同步——有 0 就写，没 0 就不写。

        不硬性要求"一定有 0"：将来真给某个控制置了 verified，那是对的演进，
        报告跟着变即可。要钉的是**报告与数据不许各说各话**。
        """
        text = (ROOT / 'governance' / 'sixstate_report.md').read_text(encoding='utf8')
        rules, controls, _ = six._load(ROOT)
        zero = [s for s in six.STATES
                if not any((c.get('state') or {}).get(s) is True for c in controls)]
        if zero:
            self.assertIn('从未取值为真的状态', text)
            for s in zero:
                self.assertIn(f'`{s}`', text)
        else:
            self.assertNotIn('从未取值为真的状态', text)


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_ignores_crlf(self):
        """同一份内容、不同换行 → 同一指纹（autocrlf 坑，本月已踩过一次）。"""
        a = Path(tempfile.mkdtemp(prefix='aasegs-fp-a-'))
        b = Path(tempfile.mkdtemp(prefix='aasegs-fp-b-'))
        self.addCleanup(shutil.rmtree, a, True)
        self.addCleanup(shutil.rmtree, b, True)
        rules = {'rules': [{'rule_id': 'R-01', 'status': {'documented': True}}]}
        controls = {'controls': [{'id': 'C-01', 'state': {'documented': True}}]}
        matrix = {'issues': {}}
        for base, nl in ((a, '\n'), (b, '\r\n')):
            for rel, obj in (('rule-registry.json', rules),
                             ('control-catalog.yaml', controls),
                             ('governance/acceptance_matrix.json', matrix)):
                p = base / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                # 必须 indent=2：单行 json 里没有 \n，`replace('\n', nl)` 什么
                # 都不做，两边字节完全相同——那样的测试对换行是瞎的，
                # 它会稳定通过，从而让"指纹换行不敏感"这件事看起来被钉住了。
                p.write_bytes(json.dumps(obj, indent=2).replace('\n', nl).encode('utf8'))
        fa = six._fingerprint(a, rules['rules'], controls['controls'], matrix)
        fb = six._fingerprint(b, rules['rules'], controls['controls'], matrix)
        self.assertEqual(fa, fb, '指纹对换行敏感——CI 上会永久"过期"')


if __name__ == '__main__':
    unittest.main()
