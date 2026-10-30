#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态负向用例实跑器（AASEGS v1.1.1 §13 补遗用例的可执行版本）。

对治理文件的"被篡改临时副本"运行 scripts/validate_controls.py，
断言校验以预期方式失败；同时对未篡改副本断言通过（阴性对照）。
篡改只发生在临时目录，原文件不被修改。

用法：
    python tests/negative_static.py            # 跑用例，输出结论
    EVIDENCE_DIR=evidence python tests/negative_static.py
        # 额外把逐条结果写入带时间戳的证据 JSON（append-only 语义由 git 承担）
"""
import json, os, re, shutil, subprocess, sys, tempfile, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / 'scripts' / 'validate_controls.py'
FILES = ['control-catalog.yaml', 'rule-registry.json']

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def make_tmp(mangle=None):
    """复制治理文件到临时目录，可选篡改函数（接收 json 数据，原地修改）。"""
    tmp = Path(tempfile.mkdtemp(prefix='aasegs-neg-'))
    data = {}
    for f in FILES:
        data[f] = json.loads((ROOT / f).read_text(encoding='utf8'))
    if mangle:
        mangle(data)
    for f in FILES:
        (tmp / f).write_text(json.dumps(data[f], ensure_ascii=False, indent=2),
                             encoding='utf8', newline='\n')
    # 审计清单也必须进入副本：validate_controls 的双向差异检查要读它，
    # 缺了会让"干净副本"因输入缺失而失败（阴性对照失效）。
    audit = ROOT / 'AASEGS_Audit_Issues_Full.md'
    if audit.exists():
        (tmp / audit.name).write_text(audit.read_text(encoding='utf8'),
                                      encoding='utf8', newline='\n')
    # 控制↔规则双向闭合登记同样是被校验的输入（2026-10-30 新增）
    cov = ROOT / 'governance' / 'control_coverage.json'
    if cov.exists():
        (tmp / 'governance').mkdir(exist_ok=True)
        (tmp / 'governance' / cov.name).write_text(
            cov.read_text(encoding='utf8'), encoding='utf8', newline='\n')
    # 幽灵用例拦截（2026-10-30）要解析 tests/ 与 workflow 里的真实用例名才能
    # 判断 test 字段是否成立。缺了这两处，干净副本会把所有控制判成"引用不存在"，
    # 使 T_REG_04 等用例失去阴性对照——掩盖真正的问题。
    for rel, pat in (('tests', '*.py'), ('.github/workflows', '*.yml')):
        for f in sorted((ROOT / rel).rglob(pat)):
            if '__pycache__' in f.parts:
                continue
            tgt = tmp / f.relative_to(ROOT)
            tgt.parent.mkdir(parents=True, exist_ok=True)
            tgt.write_text(f.read_text(encoding='utf8', errors='ignore'),
                           encoding='utf8', newline='\n')
    return tmp


def run_lint(target):
    r = subprocess.run([sys.executable, str(LINT), str(target)],
                       capture_output=True, text=True)
    err = (r.stderr or r.stdout).strip().splitlines()
    return r.returncode, (err[-1] if err else '')


@case
def T_REG_01_unregistered_must_clause():
    """注入带编号但未注册的 MUST 条款 → 文档侧双向差异检查必须失败。"""
    def mangle(d):
        pass
    tmp = make_tmp(mangle)
    (tmp / '00-injected.md').write_text(
        '# 注入\n\n- **FAKE-01 MUST**：这是一条未注册的强制条款。\n', encoding='utf8')
    rc, tail = run_lint(tmp)
    return rc != 0 and 'FAKE-01' in tail, rc, tail


@case
def T_REG_02_forged_verified_state():
    """把尚未 tested 的控制伪造为 verified → 六态前置条件必须拒绝。

    注意：不能固定篡改 controls[0]——它可能恰好已被推进到 tested，
    那样"伪造 verified"不再违反前置条件，用例会变成假绿。
    """
    def mangle(d):
        target = next((c for c in d['control-catalog.yaml']['controls']
                       if not c['state']['tested']), None)
        assert target is not None, '夹具中没有未 tested 的控制可选'
        target['state']['verified'] = True
    tmp = make_tmp(mangle)
    rc, tail = run_lint(tmp)
    return rc != 0 and 'verified' in tail, rc, tail


@case
def T_AUD_01_missing_test_field():
    """删除一条控制的 test 字段 → 五要素完整性校验必须失败。"""
    def mangle(d):
        d['control-catalog.yaml']['controls'][0].pop('test')
    tmp = make_tmp(mangle)
    rc, tail = run_lint(tmp)
    return rc != 0 and 'missing fields' in tail, rc, tail


@case
def T_REG_03_orphan_control_without_disposition():
    """双向闭合：让控制失去全部规则引用且未登记处置 → 必须失败。

    这正是 2026-10-30 发现的反向漏洞：控制可以凭空存在，
    覆盖检查只做「规则→控制」一个方向，看不见它。
    """
    tmp = make_tmp()
    reg_path = tmp / 'rule-registry.json'
    reg = json.loads(reg_path.read_text(encoding='utf8'))
    cov = json.loads((tmp / 'governance' / 'control_coverage.json')
                     .read_text(encoding='utf8'))
    declared = set(cov.get('dispositions') or {})

    # 找一条"只被一个规则引用、且没有处置登记"的控制，摘掉它唯一的引用
    counts = {}
    for r in reg['rules']:
        for cid in r['enforcement']['controls']:
            counts[cid] = counts.get(cid, 0) + 1
    victim = next((cid for cid, n in sorted(counts.items())
                   if n == 1 and cid not in declared), None)
    assert victim is not None, '夹具中找不到可摘除唯一引用的控制'
    for r in reg['rules']:
        if victim in r['enforcement']['controls']:
            r['enforcement']['controls'].remove(victim)
            if not r['enforcement']['controls']:
                r['enforcement']['gap'] = 'injected gap for negative test'
    reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2),
                        encoding='utf8', newline='\n')
    rc, tail = run_lint(tmp)
    return rc != 0 and 'control_coverage' in tail, rc, tail


@case
def T_REG_04_control_without_risk_level():
    """任一控制缺 risk_level → 必须失败（不再只要求"服务规则的控制"）。"""
    def mangle(d):
        d['control-catalog.yaml']['controls'][0]['risk_level'] = None
    tmp = make_tmp(mangle)
    rc, tail = run_lint(tmp)
    return rc != 0 and 'risk_level' in tail, rc, tail


@case
def T_REG_05_ghost_test_ref():
    """幽灵用例：test 字段指向仓库里不存在的用例 → 必须失败。

    "有测试引用"和"测试真的存在"是两件事。2026-10-30 记账复核发现
    QA-04 的 test 字段写着 T-QA-05，而仓库里根本没有这个用例——
    旧的唯一性检查只比对字段值是否重复，查不到引用是否可解析。
    """
    def mangle(d):
        for c in d['control-catalog.yaml']['controls']:
            if c['status'] == 'tested' and c.get('evidence_kind') == 'automated':
                c['test'] = 'T-GHOST-99'
                break
    tmp = make_tmp(mangle)
    rc, tail = run_lint(tmp)
    return rc != 0 and 'no real case' in tail, rc, tail


@case
def T_REG_06_tested_without_evidence_kind():
    """tested 控制未声明 evidence_kind（automated/drill）→ 必须失败。

    不区分"每次 CI 都会再跑一遍"和"只有一次历史演练"，
    tested 就会把一次性演练记录当成常态化保障。
    """
    def mangle(d):
        for c in d['control-catalog.yaml']['controls']:
            if c['status'] == 'tested':
                c.pop('evidence_kind', None)
                break
    tmp = make_tmp(mangle)
    rc, tail = run_lint(tmp)
    return rc != 0 and 'evidence_kind' in tail, rc, tail


def main():
    out = []
    all_ok = True

    # 阴性对照：未篡改副本必须通过
    tmp_clean = make_tmp()
    rc, tail = run_lint(tmp_clean)
    clean_ok = rc == 0
    out.append(dict(case='NEGATIVE-CONTROL(clean copy)', passed=clean_ok,
                    exit=rc, detail=tail))
    all_ok &= clean_ok

    for fn in CASES:
        try:
            ok, rc, tail = fn()
        except Exception as e:                       # noqa: BLE001
            ok, rc, tail = False, -1, f'exception: {e}'
        all_ok &= ok
        out.append(dict(case=fn.__name__, passed=bool(ok), exit=rc, detail=tail))

    ev_dir = os.environ.get('EVIDENCE_DIR')
    if ev_dir:
        d = Path(ev_dir)
        d.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        path = d / f'static_negative_{ts}.json'
        path.write_text(json.dumps({
            'generated_at': ts,
            'runner': 'tests/negative_static.py',
            'lint': 'scripts/validate_controls.py',
            'all_passed': all_ok,
            'results': out,
        }, ensure_ascii=False, indent=2), encoding='utf8', newline='\n')
        print(f'evidence written: {path.name}')

    for r in out:
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['case']}  exit={r['exit']}  "
              f"{r['detail'][:90]}")
    print('RESULT:', 'ALL PASSED' if all_ok else 'FAILED')
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
