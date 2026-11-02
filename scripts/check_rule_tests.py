#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-REF-03：规则侧用例引用完整性——`verification.tests` 必须指得到东西。

为什么要有这条检查
------------------
`check_governance_refs.py`（T-REF-01）的 docstring 写着「唯一的豁免是 T-*（用例名）
——它是否存在由审计闭环判，本脚本不扫 tests/」；`check_control_refs.py`（T-REF-02）
的防误报段写着「`T-*` 一律跳过：那是测试用例名……由审计闭环管」。**两处都这么写，
而「审计闭环」并不做这件事**：`check_audit_closure.py` 判的是 §四 断言的 verdict
与证据，从不解析 `rule-registry.json` 的 `verification.tests`。全仓库唯一读这个
字段的是 `export_coverage_pack.py`，而它没有接线——`--check` 没有任何门禁在调用。

于是 10 处悬空引用安静地躺了很久。用 `git log -S` 查 `tests/` 全历史，`T-QA-03`、
`T-RVW-01`、`T-AUD-02` 一次都没出现过——它们从来不是「被删掉的用例」，是从来
就没有过。指向不存在的用例比不写用例更糟：读的人会以为有。

两处注释都指向一个不存在的执行者，这本身就是「文档也会说谎」的同族。
所以本脚本出现之后，那两处注释要跟着改指向本脚本——不修注释等于没修完。

判据（三条，全部失败关闭）
--------------------------
A. **引用可解析**：`verification.tests` 每一项必须落到真实方法（`test_*`）或
   workflow 里出现过的 CI 步骤名。解析器**只保留一份实现**——直接复用
   `export_coverage_pack.resolve_test`。这是刻意制造的耦合：材料生成与门禁
   判「一条引用算不算数」必须是同一把尺子，两个解析器一定会漂移，而漂移
   正是本类缺陷的成因。
B. **缺口不空转**：规则引用的控制里只要有一个 `not_enforced`，`enforcement.gap`
   必须是非空字符串。`type=technical` + `gap=null` 读起来是「有技术手段、无缺口」，
   那句话是整套登记里最容易骗人的形态——它看起来像结论，其实什么都没说。
C. **空串不算写了**：`gap` 为 `""` 或全空白一样判红。写一个空格不是声明缺口。

边界（诚实声明）
----------------
- 不判断用例**内容**对不对（那是审计闭环与人工复核的事），只判断「是否存在」。
- 不要求每条规则都引用用例：`verification.tests: []` 是合法且诚实的表达，
  只要 `gap` 说清了为什么没有。
- workflow 兜底意味着一个编号只要在任意 `.yml` 里出现过就算「可解析」。这是
  与 `resolve_test` 同口径的弱保证——`T-VD-01b` / `T-CLOSE` 这类确实是 CI
  步骤名而非 `def test_*`，它们算证据，但不是单元用例。弱就弱在明处，不假装。

退出码：0 通过；1 有未解析引用或空转缺口；2 不可判定（注册表/控制目录缺失）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from export_coverage_pack import _test_index, resolve_test  # noqa: E402


def _load(root):
    root = Path(root)
    try:
        rules = json.loads((root / 'rule-registry.json').read_text(encoding='utf8'))['rules']
        controls = json.loads((root / 'control-catalog.yaml').read_text(encoding='utf8'))['controls']
    except (OSError, KeyError, json.JSONDecodeError) as e:
        return None, None, f'无法读取注册表/控制目录：{e}（不可判定即拒绝，不猜）'
    return rules, {c['id']: c for c in controls}, None


def check(root=ROOT):
    """返回 findings 列表；空列表表示通过。"""
    rules, controls, err = _load(root)
    if err:
        return None, err
    index = _test_index(root)
    findings = []

    for r in rules:
        rid = r.get('rule_id') or '<无 rule_id>'
        refs = (r.get('verification') or {}).get('tests') or []
        if not isinstance(refs, list):
            findings.append({'kind': 'tests_not_list', 'id': rid,
                             'detail': f'verification.tests 不是列表：{refs!r}'})
            refs = []

        # A. 每条引用必须解析得到
        for ref in refs:
            kind, target = resolve_test(ref, index, root)
            if not kind:
                findings.append({'kind': 'dangling_test_ref', 'id': rid,
                                 'detail': f'{ref} 既不是 tests/ 里的用例方法，'
                                           f'也不在任何 workflow 步骤里'})

        # B/C. 空转缺口：有 not_enforced 控制就必须写清 gap
        enf = r.get('enforcement') or {}
        idle = [c for c in (enf.get('controls') or [])
                if (controls.get(c) or {}).get('status') == 'not_enforced']
        if idle:
            gap = enf.get('gap')
            if gap is None:
                findings.append({'kind': 'gap_silent', 'id': rid,
                                 'detail': f'控制 {",".join(idle)} 是 not_enforced，'
                                           f'但 enforcement.gap 为 null——'
                                           f'"技术强制、无缺口"这句话在这里不成立'})
            elif not str(gap).strip():
                findings.append({'kind': 'gap_blank', 'id': rid,
                                 'detail': f'控制 {",".join(idle)} 是 not_enforced，'
                                           f'enforcement.gap 只写了一个空串'})
    return findings, None


def main(argv=None):
    argv = argv or []
    root = Path(argv[0]).resolve() if argv else ROOT
    findings, err = check(root)
    if err:
        print(f'FAIL(T-REF-03): {err}')
        return 2
    if findings:
        print(f'FAIL(T-REF-03): {len(findings)} 处规则侧引用/缺口登记不成立')
        for f in findings:
            print(f'  [{f["kind"]}] {f["id"]} :: {f["detail"]}')
        return 1
    print('PASS(T-REF-03): 规则侧用例引用全部可解析；'
          '有空转控制的规则都写明了 enforcement.gap')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
