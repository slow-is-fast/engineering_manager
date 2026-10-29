# -*- coding: utf-8 -*-
"""T-RVF-01：证据新鲜度与持续复验。

负向：证据过期 / 无时间戳 → --enforce 必须非零退出。
正向：新鲜证据 → 通过；--degrade 能把过期控制降级写回目录。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'verify_evidence_freshness.py'


def make_catalog(tmp: Path, controls):
    (tmp / 'control-catalog.yaml').write_text(
        json.dumps({'version': '1.1.1', 'controls': controls},
                   ensure_ascii=False, indent=2), encoding='utf8')
    return tmp


def control(cid, risk='P0', days_old=0, with_stamp=True):
    c = {'id': cid, 'requirement_ref': cid, 'owner': 'o', 'enforcer': 'e',
         'evidence': 'ev', 'failure': 'fail', 'test': f'T-{cid}',
         'status': 'tested', 'integration_evidence_uri': 'https://example.invalid/1',
         'risk_level': risk, 'source_ref': 's', 'addresses': ['AASEGS-AUD-001'],
         'state': {'documented': True, 'configured': True, 'tested': True,
                   'verified': False, 'degraded': False, 'excepted': False}}
    if with_stamp:
        c['evidence_at'] = (date.today() - timedelta(days=days_old)).isoformat()
    return c


def run(directory, *flags):
    return subprocess.run([sys.executable, str(SCRIPT), str(directory), *flags],
                          capture_output=True, text=True)


class EvidenceFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aasegs-rvf-"))

    def test_stale_evidence_rejected(self):
        # P0 TTL=30 天，60 天前即过期
        make_catalog(self.tmp, [control('X-1', 'P0', days_old=60)])
        r = run(self.tmp, '--enforce')
        self.assertNotEqual(r.returncode, 0, '过期证据未被拦截')
        self.assertIn('STALE', r.stdout)

    def test_missing_timestamp_rejected(self):
        make_catalog(self.tmp, [control('X-2', 'P1', with_stamp=False)])
        r = run(self.tmp, '--enforce')
        self.assertNotEqual(r.returncode, 0, '无时间戳证据未被拦截')
        self.assertIn('UNKNOWN', r.stdout)

    def test_fresh_evidence_passes(self):
        make_catalog(self.tmp, [control('X-3', 'P0', days_old=1),
                                control('X-4', 'P2', days_old=100)])
        r = run(self.tmp, '--enforce')
        self.assertEqual(r.returncode, 0, f'新鲜证据被误杀: {r.stdout}')

    def test_degrade_writes_state(self):
        make_catalog(self.tmp, [control('X-5', 'P0', days_old=60)])
        r = run(self.tmp, '--degrade')
        self.assertEqual(r.returncode, 0)
        cat = json.loads((self.tmp / 'control-catalog.yaml').read_text(encoding='utf8'))
        x5 = [c for c in cat['controls'] if c['id'] == 'X-5'][0]
        self.assertTrue(x5['state']['degraded'], '过期控制未降级')
        self.assertFalse(x5['state']['tested'], '降级后 tested 应置 false')

    def test_repo_catalog_fresh(self):
        r = run(ROOT, '--enforce')
        self.assertEqual(r.returncode, 0, f'仓库证据已过期: {r.stdout}')


if __name__ == '__main__':
    unittest.main()
