#!/usr/bin/env python3
"""Schema/completeness lint only. Does NOT enforce real-world security policies."""
import json, sys
from pathlib import Path
# 可选：argv[1] 指定治理目录（供负向测试对篡改副本运行）；默认校验仓库自身
BASE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
p = BASE / 'control-catalog.yaml'
x = json.loads(p.read_text(encoding='utf8'))  # JSON is YAML 1.2 subset

required = {'id', 'requirement_ref', 'owner', 'enforcer', 'evidence', 'failure',
            'test', 'status', 'integration_evidence_uri'}
STATES = ('documented', 'configured', 'tested', 'verified', 'degraded', 'excepted')

assert x['version'] == '1.1.1', f"unexpected catalog version: {x['version']}"

seen = set()
for c in x['controls']:
    assert required <= c.keys(), f"missing fields: {c.get('id')}"
    assert c['id'] not in seen, f"duplicate id: {c['id']}"
    seen.add(c['id'])
    assert all(c[k] for k in ('owner', 'enforcer', 'evidence', 'failure', 'test')), \
        f"empty mandatory field: {c['id']}"
    assert c['status'] in ('not_enforced', 'tested', 'enforced'), \
        f"bad status: {c['id']}"
    if c['status'] in ('tested', 'enforced'):
        assert c['integration_evidence_uri'], f"missing verified evidence: {c['id']}"
        # RVF-01：没有验证时间戳的证据无法判断新鲜度，等于不可复验
        assert c.get('evidence_at'), f"missing evidence_at (unverifiable freshness): {c['id']}"

    # v1.1.1 §1：控制状态必须能区分六态
    st = c.get('state')
    assert isinstance(st, dict), f"missing state block: {c['id']}"
    assert set(st) == set(STATES), f"bad state keys: {c['id']}"
    assert all(isinstance(v, bool) for v in st.values()), f"non-bool state: {c['id']}"
    if st['verified']:
        assert st['documented'] and st['configured'] and st['tested'], \
            f"verified without documented/configured/tested: {c['id']}"
        assert c['integration_evidence_uri'], f"verified without evidence: {c['id']}"

# v1.1.1 新增控制必须声明风险等级、来源章节与所应答的审计问题
LEGACY = ('ID', 'CTX', 'WF', 'REC', 'QA', 'AUD')
for c in x['controls']:
    if c['id'].split('-')[0] in LEGACY:
        continue
    assert c.get('risk_level') in ('P0', 'P1', 'P2'), f"missing risk_level: {c['id']}"
    assert c.get('source_ref'), f"missing source_ref: {c['id']}"
    assert c.get('addresses'), f"missing audit mapping: {c['id']}"

# 一条控制一个独立负向测试，避免复用导致的覆盖假象
tests = [c['test'] for c in x['controls']]
assert len(tests) == len(set(tests)), \
    f"duplicate test ref: {[t for t in tests if tests.count(t) > 1]}"

# ---- v1.1.1 §1 规则注册表（rule-registry.json）----
REG_FIELDS = {'rule_id', 'source_location', 'statement', 'requirement', 'scope',
              'risk_level', 'owner', 'enforcement', 'evidence_required',
              'failure_behavior', 'verification', 'status', 'exception_ref'}
rp = BASE / 'rule-registry.json'
reg = json.loads(rp.read_text(encoding='utf8'))
assert reg['version'] == '1.1.1', f"unexpected registry version: {reg['version']}"

rids = set()
for r in reg['rules']:
    assert REG_FIELDS <= r.keys(), f"registry missing fields: {r.get('rule_id')}"
    assert r['rule_id'] not in rids, f"duplicate rule_id: {r['rule_id']}"
    rids.add(r['rule_id'])
    assert r['statement'] and r['source_location'], f"empty rule body: {r['rule_id']}"
    assert r['requirement'] in ('MUST', 'MUST NOT'), f"bad requirement: {r['rule_id']}"
    assert r['risk_level'] in ('P0', 'P1', 'P2'), f"bad risk: {r['rule_id']}"
    st = r['status']
    assert set(st) == set(STATES), f"bad state keys: {r['rule_id']}"
    # 控制引用必须真实存在；无控制引用的规则必须说明 gap
    for cid in r['enforcement']['controls']:
        assert cid in seen, f"rule {r['rule_id']} references unknown control {cid}"
    if not r['enforcement']['controls']:
        assert r['enforcement'].get('gap'), \
            f"rule {r['rule_id']} has no control and no gap explanation"

n_gap = sum(1 for r in reg['rules'] if not r['enforcement']['controls'])

# ---- 风险等级传播：控制不得宽松于其所服务规则的最高等级 ----
# 规则层说"必须做什么"，控制层说"靠什么强制"。若控制等级标低，会连带把
# 证据复验周期拉长（RVF-01 TTL）并绕过准入判定（GOV-18）。从严（控制 > 规则）允许。
SEVERITY = {'P0': 0, 'P1': 1, 'P2': 2}
served = {}
for r in reg['rules']:
    for cid in r['enforcement']['controls']:
        served.setdefault(cid, set()).add(r['risk_level'])
for c in x['controls']:
    levels = served.get(c['id'])
    cur = c.get('risk_level')
    if not levels:
        continue
    # 未声明等级的控制会整条逃过传播检查（None 既非"更严"也非"更宽"），
    # 使 P0 规则可以由一条"无等级"控制背书。这不是从严，是漏检。
    assert cur, (f"control {c['id']} serves {sorted(levels)} rules but declares "
                 f"no risk_level (escapes risk propagation check)")
    highest = min(levels, key=lambda k: SEVERITY[k])
    assert SEVERITY[cur] <= SEVERITY[highest], (
        f"risk level propagation violated: control {c['id']}={cur} is looser than "
        f"highest served rule {highest}")

# ---- 文档侧双向差异：规范文档中带编号的 MUST/MUST NOT 条款必须已注册 ----
import re
doc_ids = set()
for md in sorted(BASE.glob('*.md')):
    for m in re.finditer(r'\*\*([A-Z]{2,4}-\d{2})\s+(?:MUST NOT|MUST)\*\*',
                         md.read_text(encoding='utf8')):
        doc_ids.add(m.group(1))
known = {c['requirement_ref'] for c in x['controls']} | set(rids)
unknown = sorted(doc_ids - known)
assert not unknown, f"unregistered MUST clauses found in docs: {unknown}"

# ---- 审计映射双向差异（§12.3 明确要求，此前只有文字承诺） ----
# 目录里写 `AASEGS-AUD-001`、清单里写 `AUD-001`：跨文档比对必须先归一化，
# 否则两边永远"对得上"（因为根本不比较），检查等于没做。
def _norm_issue(x):
    s = str(x or '').strip()
    return s[len('AASEGS-'):] if s.upper().startswith('AASEGS-') else s

_audit_md = BASE / 'AASEGS_Audit_Issues_Full.md'
assert _audit_md.exists(), 'missing audit issue list'
_issues = set(re.findall(r'###\s*AASEGS-(AUD-\d{3})',
                         _audit_md.read_text(encoding='utf8')))
assert _issues, 'no audit issues parsed from §四'

_mapped = set()
for c in x['controls']:
    for a in (c.get('addresses') or []):
        n = _norm_issue(a)
        assert n in _issues, f"control {c['id']} addresses unknown audit issue {a}"
        _mapped.add(n)
_unanswered = sorted(_issues - _mapped)
assert not _unanswered, f"audit issues with no addressing control: {_unanswered}"

print(f'PASS: {len(seen)} control definitions structurally complete; '
      f'{sum(1 for c in x["controls"] if c["risk_level"] == "P0")} declared P0; '
      f'{len(rids)} rules registered ({n_gap} without runtime control); '
      f'{len(doc_ids)} inline MUST clauses all registered; '
      f'runtime enforcement NOT verified')
