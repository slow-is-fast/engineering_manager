# -*- coding: utf-8 -*-
"""T-CLM-01：声明诚实性 lint（AGT-005「不得声称完美即时撤销」）。

负向：无证据支撑的绝对化声明必须被抓（非零退出）。
正向：带实测数据/证据引用的表述必须放行；仓库自身文档必须 PASS。
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'check_claims.py'


def run(directory):
    return subprocess.run([sys.executable, str(SCRIPT), str(directory)],
                          capture_output=True, text=True)


class ClaimsLintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aasegs-claims-"))

    def test_unbacked_absolute_claim_rejected(self):
        (self.tmp / 'doc.md').write_text(
            '# 能力说明\n\n本系统支持即时撤销，权限立即失效，100% 生效。\n',
            encoding='utf8')
        r = run(self.tmp)
        self.assertNotEqual(r.returncode, 0, '无依据的绝对化声明未被拦截')
        self.assertIn('CLM-01', r.stdout)

    def test_pure_absolute_claim_rejected(self):
        # 隔离 fixture：纯绝对化声明，无撤销/失效/100% 语境——专门钉死
        # ABSOLUTE_RE 匹配本身。组合文档会被 100%撤销规则顺带抓到，掩盖
        # "删掉绝对词匹配"这一放行路径。
        (self.tmp / 'doc.md').write_text(
            '# 能力说明\n\n本系统万无一失，绝对可靠，绝无遗漏。\n',
            encoding='utf8')
        r = run(self.tmp)
        self.assertNotEqual(r.returncode, 0, '纯绝对化声明（无撤销/100%语境）未被拦截')

    def test_pct_in_revocation_context_rejected(self):
        # 隔离 fixture：撤销语境下的 100%，不含其它绝对词——专门钉死
        # `return bool(PCT_RE and REVOCATION_CTX)` 这一支。
        (self.tmp / 'doc.md').write_text(
            '# 能力说明\n\n撤销操作使权限覆盖率达到 100%，不留残留。\n',
            encoding='utf8')
        r = run(self.tmp)
        self.assertNotEqual(r.returncode, 0, '撤销语境下的 100% 声明未被拦截')

    def test_backed_claim_allowed(self):
        (self.tmp / 'doc.md').write_text(
            '# 能力说明\n\n撤销传播实测 P95=820ms，evidence: run 40844814576，'
            '非即时生效。\n', encoding='utf8')
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, f'有依据的表述被误杀: {r.stdout}')

    def test_disclaimer_not_flagged(self):
        (self.tmp / 'doc.md').write_text(
            '# 说明\n\n覆盖率达到 100% 不代表控制有效率为 100%。\n',
            encoding='utf8')
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, f'免责声明被误判: {r.stdout}')

    def test_repo_docs_pass(self):
        r = run(ROOT)
        self.assertEqual(r.returncode, 0, f'仓库文档存在无依据声明: {r.stdout}')


if __name__ == '__main__':
    unittest.main()
