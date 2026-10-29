import json, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'control-catalog.yaml'
LEGACY = ('ID', 'CTX', 'WF', 'REC', 'QA', 'AUD')


def load():
    return json.loads(CATALOG.read_text(encoding='utf8'))


class CatalogTests(unittest.TestCase):
    def test_ids_unique_and_mapped(self):
        c = load()['controls']
        ids = [x['id'] for x in c]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(44, len(ids))
        for x in c:
            for k in ('owner', 'enforcer', 'evidence', 'failure', 'test'):
                self.assertTrue(x[k])

    def test_rule_registry_coverage(self):
        cat = {x['id'] for x in load()['controls']}
        reg = json.loads((ROOT / 'rule-registry.json').read_text(encoding='utf8'))
        rules = reg['rules']
        rids = [r['rule_id'] for r in rules]
        self.assertEqual(len(rids), len(set(rids)))
        self.assertEqual(52, len(rids))
        for r in rules:
            for cid in r['enforcement']['controls']:
                self.assertIn(cid, cat, f"{r['rule_id']} -> unknown control {cid}")
            if not r['enforcement']['controls']:
                self.assertTrue(r['enforcement'].get('gap'),
                                f"{r['rule_id']} lacks control and gap note")

    def test_no_fake_attestation(self):
        c = load()['controls']
        for x in c:
            if x['status'] == 'enforced':
                self.assertTrue(x['integration_evidence_uri'])

    def test_v111_controls_declare_risk_and_audit_mapping(self):
        c = load()['controls']
        new = [x for x in c if x['id'].split('-')[0] not in LEGACY]
        self.assertEqual(24, len(new))
        for x in new:
            self.assertIn(x['risk_level'], ('P0', 'P1', 'P2'))
            self.assertTrue(x['source_ref'])
            self.assertTrue(x['addresses'])

    def test_every_control_has_own_negative_test(self):
        tests = [x['test'] for x in load()['controls']]
        self.assertEqual(len(tests), len(set(tests)), 'duplicate test reference')

    def test_verified_state_requires_evidence(self):
        for x in load()['controls']:
            st = x['state']
            self.assertEqual({'documented', 'configured', 'tested',
                              'verified', 'degraded', 'excepted'}, set(st))
            if st['verified']:
                self.assertTrue(st['documented'] and st['configured'] and st['tested'])
                self.assertTrue(x['integration_evidence_uri'])


if __name__ == '__main__':
    unittest.main()
