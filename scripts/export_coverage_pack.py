#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUD-001-03 的复核材料：覆盖率报告 + 差异报告 + 人工抽样清单。

为什么要单独有这个脚本
----------------------
`AUD-001-03` 是 `manual` / `human_gate=sampling_review`，它的原文是
「人工抽样复核记录（覆盖率的完备性无法自动判定）」，所属问题的闭合条件写着
「提交覆盖率报告、差异报告和人工抽样复核记录」。

也就是说，这条断言要的不是"再跑一遍校验器"，而是**一个人看着具体样本下判断**。
但在此之前仓库里只有校验器的单行 PASS，没有任何"可以拿去判断"的材料——
让 Owner 从 59 条规则里自己想从哪看起，等于把成本推给了他，然后他多半会
说"你帮我签了吧"。本脚本把这份成本压到"10 条，每条三个勾"。

边界（写在这里，因为它正是这条断言的核心）
------------------------------------------
本脚本产出的是**复核材料**，不是复核记录。它不下判断、不选 verdict、
不写 `signoffs.jsonl`。抽样清单里的三个勾必须由人打；`--accept-evidence`
登记这份材料之后，人对着它写结论，那份结论才是 `AUD-001-03` 的证据。

抽样方法（可复现，不随机）
--------------------------
按 `sha256(rule_id)` 升序排列取前 N 条（默认 10）——不用 `random`，
是因为"上次抽到哪几条"必须能被第二个人一模一样地重算出来；用哈希而不是
字母序，是为了避免"前 10 条恰好都在同一章"这种结构性偏差。

发现会直接写进差异报告
----------------------
本脚本第一次跑就抓到一件真实的事：`rule-registry.json` 里有 10 处用例引用
（5 个编号）指向**不存在的测试方法**，而当时的校验器只查控制目录侧（且只查
`status=tested & evidence_kind=automated` 的控制），**规则侧无人校验**。
这不是抽样抽出来的，是算差异算出来的——所以它进"差异报告"，不进"待判断"。

那 10 处已于 2026-11-02 清理完（3 处改对引用、7 处删除并写 `enforcement.gap`），
并由 `scripts/check_rule_tests.py`（T-REF-03）接管为门禁。本脚本从此只负责
**报告**这件事，不负责拦它——报告没人读时不会有人红，那正是当初的漏洞。
"""
import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_OUT = 'governance/coverage_pack_aud001.md'
SAMPLE_N = 10
SNIPPET_LINES = 18


# ---------------------------------------------------------------- 载入

def _load(root):
    root = Path(root)
    rules = json.loads((root / 'rule-registry.json').read_text(encoding='utf8'))['rules']
    catalog = json.loads((root / 'control-catalog.yaml').read_text(encoding='utf8'))
    return rules, catalog


def _test_index(root):
    """{小写方法名: (相对路径, 起行, 止行)}——ast 取行号，正则取不到的缩进层级它知道。"""
    index = {}
    for fn in sorted((Path(root) / 'tests').glob('*.py')):
        src = fn.read_text(encoding='utf8')
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                index.setdefault(node.name.lower(), (
                    str(fn.relative_to(root)).replace('\\', '/'),
                    node.lineno, getattr(node, 'end_lineno', node.lineno)))
    return index


# ---------------------------------------------------------------- 解析用例引用

def _slug(ref):
    return ref.lower().replace('-', '_')


def resolve_test(ref, index, root):
    """`T-QA-02` → `test_t_qa_02_*`（tests/ 里大小写与下划线两种写法都认）。

    与 `validate_controls._ref_exists` 同口径，另加 workflow 兜底：有些 ref
    指向的是 CI 步骤名而不是用例方法（如 `T-VD-01b` 对应一条检查脚本）。
    """
    slug = _slug(ref)
    for name in index:
        if name == slug or name == 'test_' + slug or \
                name.startswith(slug + '_') or name.startswith('test_' + slug + '_'):
            return ('method', name)
    for wf in (Path(root) / '.github' / 'workflows').glob('*.yml'):
        if ref in wf.read_text(encoding='utf8'):
            return ('workflow', wf.name)
    return (None, None)


# ---------------------------------------------------------------- 三份材料

def coverage(rules, catalog, index, root):
    controls = {c['id']: c for c in catalog['controls']}
    stats = {
        'rules': len(rules),
        'rules_with_controls': 0,
        'rules_with_tests': 0,
        'rules_tests_all_resolve': 0,
        'controls': len(controls),
        'controls_with_test': 0,
        'controls_test_resolves': 0,
    }
    rows = []                              # 规则级逐条（只用于统计，不整表渲染）
    for r in rules:
        ctls = [c for c in ((r.get('enforcement') or {}).get('controls') or [])]
        refs = list(((r.get('verification') or {}).get('tests') or []))
        if ctls:
            stats['rules_with_controls'] += 1
        if refs:
            stats['rules_with_tests'] += 1
        ok = [t for t in refs if resolve_test(t, index, root)[0]]
        if refs and len(ok) == len(refs):
            stats['rules_tests_all_resolve'] += 1
        rows.append({'rule': r['rule_id'], 'risk': r.get('risk_level'),
                     'controls': ctls, 'tests': refs,
                     'missing': [t for t in refs if t not in ok]})
    for cid, c in controls.items():
        if c.get('test'):
            stats['controls_with_test'] += 1
            if resolve_test(c['test'], index, root)[0]:
                stats['controls_test_resolves'] += 1
    return stats, rows, controls


def diff_report(rules, rows, controls, index, root):
    """双向差异 + 悬空引用。每一条都是"某个地方声称存在、其实不存在"。"""
    out = {'rule_without_control': [], 'control_orphan': [],
           'dangling_tests': [], 'test_field_missing': []}
    referenced = set()
    for r in rules:
        ctls = (r.get('enforcement') or {}).get('controls') or []
        referenced.update(ctls)
        if not ctls:
            out['rule_without_control'].append((r['rule_id'], r.get('risk_level'),
                                                r.get('statement', '')[:40]))
    for cid, c in sorted(controls.items()):
        if cid not in referenced:
            out['control_orphan'].append((cid, c.get('status'), c.get('source_ref', '')[:40]))
        if not c.get('test'):
            out['test_field_missing'].append(cid)
    for row in rows:
        for t in row['missing']:
            out['dangling_tests'].append((row['rule'], t, row['risk']))
    return out


def sample(rows, n):
    """按 sha256(rule_id) 升序取前 n 条——可复现、无随机、无字母序偏差。"""
    ranked = sorted(rows, key=lambda r: hashlib.sha256(r['rule'].encode()).hexdigest())
    return ranked[:n]


def _clip(text, n=56):
    """控制目录里的 evidence/failure 是整句话，直接内联会把列表撑成散文。"""
    t = str(text or '?').strip()
    return t if len(t) <= n else t[:n] + '…'


def _snippet(index, ref, root):
    kind, name = resolve_test(ref, index, root)
    if kind != 'method':
        return ('未解析到真实用例或 CI 步骤（见差异报告 2.3）——'
                '本条只能判断「为什么它不在」，不能判断用例质量'), None
    rel, a, b = index[name]
    lines = (Path(root) / rel).read_text(encoding='utf8').splitlines()
    body = lines[a - 1:min(b, a - 1 + SNIPPET_LINES)]
    more = '  （已截断）' if b - a + 1 > SNIPPET_LINES else ''
    return f'{rel}:{a}-{b}{more}', body


# ---------------------------------------------------------------- 渲染

def render(stats, rows, controls, diff, picks, index, root, fp, rules):
    L = []
    w = L.append
    w('# AUD-001-03 复核材料：覆盖率 · 差异 · 抽样清单')
    w('')
    w('> **自动生成，勿手改。** 重新生成：`python scripts/export_coverage_pack.py`')
    w(f'> 材料指纹：`{fp}`（`--check` 会比对，材料变了就红）')
    w('>')
    w('> **但 `--check` 现在没有任何门禁在调用**：材料过期不会让 CI 红，只有你自己跑才会发现。')
    w('> 要把它变成硬约束，得走接线三条腿（`required_checks` 注册 + workflow 步骤 + `check_args`），')
    w('> 那是另一个决定——不做，就在这里写明，而不是让人以为"有指纹就等于有人看着"。')
    w('>')
    w('> **这是复核材料，不是复核记录。** 三个勾必须由人打；本文件不产生任何签署，')
    w('> 也不关闭任何断言。人对着它写下的结论，才是 `AUD-001-03` 的证据。')
    w('')
    w('## 一、覆盖率报告（机器可算的部分）')
    w('')
    w('口径先说清楚，因为这个数字最容易被读大：')
    w('')
    w('| 层 | 意思 | 数量 |')
    w('|---|---|---|')
    w(f"| 规则 | `rule-registry.json` 注册的 MUST/MUST NOT 条款 | {stats['rules']} |")
    w(f"| 规则→控制 | 声明了至少一条 `enforcement.controls` | {stats['rules_with_controls']} / {stats['rules']} |")
    w(f"| 规则→用例（字符串） | 声明了至少一条 `verification.tests` | {stats['rules_with_tests']} / {stats['rules']} |")
    w(f"| 规则→用例（**可解析**） | 引用能落到真实存在的方法或 CI 步骤 | {stats['rules_tests_all_resolve']} / {stats['rules']} |")
    w(f"| 控制 | `control-catalog.yaml` 注册的控制 | {stats['controls']} |")
    w(f"| 控制→用例（可解析） | `test` 字段能落到真实方法/CI 步骤 | {stats['controls_test_resolves']} / {stats['controls_with_test']} |")
    w('')
    w('**「追踪覆盖率 100%」这句话在什么意义上成立、在什么意义上不成立：**')
    w('')
    w(f"- 成立：每条规则都能被追到至少一条控制（{stats['rules_with_controls']}/{stats['rules']}），"
      f"控制目录与控制定义双向无缺项——这是校验器管的部分。")
    dangling_rules = stats['rules_with_tests'] - stats['rules_tests_all_resolve']
    if dangling_rules:
        w(f"- **不成立**：有 {dangling_rules} 条规则的用例引用"
          f"落不到任何真实用例上（见第二节）。它们的状态本来就是 `tested=false`，所以没有人"
          f"声称它们被测过；但 `verification.tests` 里写着一个不存在的编号，读的人会以为有。")
    else:
        w(f"- 成立：声明了 `verification.tests` 的 {stats['rules_with_tests']} 条规则，"
          f"引用全部落得到真实方法或 CI 步骤——这一条自 T-REF-03 起由门禁强制，"
          f"不再依赖本材料被谁读到。")
    w('')
    w('> **同一栏里两个数不能相减当覆盖率。** 「字符串」数的是"声明了至少一条引用"，')
    w('> 「可解析」数的是"声明的引用全都落得到"；分母都是 59 条规则，但含义不同。')
    w('> 一次整改如果把悬空引用**删掉**，该规则会同时从这两栏里消失——比值可能因此上升，')
    w('> 而事情只是"不再声称有覆盖"，不是"有了覆盖"。判断覆盖有没有变好，看 2.3 与第三节，')
    w('> 不看这两个数字的比值。2026-11-02 那次整改就是这种情况，拆开看是三件事同时发生：')
    w('> ① 3 条规则靠**改对引用**重回可解析（`T-ID-02`×2 → `T-VD-01b`，`T-QA-05` → `T-CLOSE`）；')
    w('> ② 1 条规则（`AASEGS-SEC-003`）删掉悬空的那 1 处后，剩余引用全部可解析；')
    w('> ③ 4 条规则（`GOV-02`/`AASEGS-AGT-001`/`AASEGS-SEC-002`/`AASEGS-SUP-002`）把引用')
    w('> 全删了，于是从两栏里同时消失（「字符串」一栏因此 53 → 49）。')
    w('> 只有 ① 是真的变好；② 是账面变干净；③ 是承认缺口——三种都算进步，但不是同一种。')
    w('')
    w('## 二、差异报告（双向，含悬空引用）')
    w('')
    if diff['rule_without_control']:
        w(f"### 2.1 有规则、没有运行时控制（{len(diff['rule_without_control'])} 条）")
        w('')
        w('| 规则 | 风险 | 条款 |')
        w('|---|---|---|')
        for rid, risk, text in diff['rule_without_control']:
            w(f'| `{rid}` | {risk} | {text} |')
        w('')
    else:
        w('### 2.1 有规则、没有运行时控制：0 条')
        w('')
    if diff['control_orphan']:
        w(f"### 2.2 有控制、没有规则引用（孤儿控制，{len(diff['control_orphan'])} 条）")
        w('')
        w('| 控制 | 状态 | 来源 |')
        w('|---|---|---|')
        for cid, st, ref in diff['control_orphan']:
            w(f'| `{cid}` | {st} | {ref} |')
        w('')
    else:
        w('### 2.2 有控制、没有规则引用：0 条')
        w('')
    w(f"### 2.3 悬空用例引用（{len(diff['dangling_tests'])} 处）")
    w('')
    if diff['dangling_tests']:
        w('声明了 `T-XXX` 这个用例，仓库里没有这个方法，也不在任何 workflow 步骤里。')
        w('')
        w('| 规则 | 引用的用例 | 风险 |')
        w('|---|---|---|')
        for rid, t, risk in diff['dangling_tests']:
            w(f'| `{rid}` | `{t}` | {risk} |')
        w('')
        w('> 为什么校验器没拦住：`validate_controls.py` 的幽灵用例检查只覆盖'
          '**控制目录侧**，且只查 `status=tested & evidence_kind=automated`；'
          '**规则侧的 `verification.tests` 没有任何检查**。两半合起来才算完整，'
          '现在只有一半。')
        w('')
    else:
        w('无。')
        w('')
        w('> 这一栏空了，但**不是因为从来没出过问题**。2026-11-02 之前它列着 10 处，')
        w('> 分属 5 个编号：`T-ID-02` / `T-QA-03` / `T-RVW-01` / `T-QA-05` / `T-AUD-02`。')
        w('> 用 `git log -S` 查 `tests/` 全历史，这五个编号一次都没出现过——它们不是')
        w('> 「被删掉的用例」，是从来就没有过。')
        w('>')
        w('> 处理方式按"控制有没有真东西可引用"分成两类：控制已 `tested` 且有自己的 `test`')
        w('> 字段的，把引用**改对**（那是抄错编号）；控制本身 `not_enforced` 的，**删掉引用**')
        w('> 并在 `enforcement.gap` 里写明缺口为什么补不出来——单人类环境里写一条"两个 token')
        w('> 不相等"的用例不是补覆盖，是给缺口加一层伪装。')
        w('>')
        w('> 同年同日新增 `T-REF-03`（`scripts/check_rule_tests.py`）补上这个空档：它是第一个')
        w('> 真正校验规则侧 `verification.tests` 的门禁。此前 T-REF-01 与 T-REF-02 的 docstring')
        w('> 都写着"T-* 由审计闭环管"——而审计闭环判的是 §四 断言的 verdict 与证据，从不解析')
        w('> 这个字段。两处注释指向了同一个不存在的执行者，那才是这 10 处能躺这么久的真正原因。')
        w('')
    if diff['test_field_missing']:
        w(f"### 2.4 `test` 字段为空的控制（{len(diff['test_field_missing'])} 条）")
        w('')
        w('`' + '`、`'.join(diff['test_field_missing']) + '`')
        w('')
    w('## 三、人工抽样清单（{0} 条，请逐条判断）'.format(len(picks)))
    w('')
    w('抽样方法：全部规则按 `sha256(rule_id)` 升序，取前 ' + str(len(picks)) +
      ' 条。可复现、无随机、不按字母序（避免"前几条恰好同一章"的结构性偏差）。')
    w('')
    w('每条问三件事——**这三问工具答不了，因为要判断的是语义，不是存在性**：')
    w('')
    w('1. 引用的控制，是否真的回应了这条规则？（不是"编号对上了"，是"意思对上了"）')
    w('2. 引用的用例，是否真的在验证这条控制？（读下面的源码，别看方法名）')
    w('3. 若 1 或 2 不成立，这是"引用挂错"（可修）还是"根本没有覆盖"（是真缺口）？')
    w('')
    by_id = {x['rule_id']: x for x in rules}
    for i, row in enumerate(picks, 1):
        rid = row['rule']
        r = by_id[rid]
        w(f"### 样本 {i} · `{rid}`（{row['risk']}）")
        w('')
        w(f"**规则原文**：{r.get('statement', '').strip()}")
        w('')
        w(f"- 强度：`{r.get('requirement')}`　责任：`{r.get('owner')}`")
        if row['controls']:
            for cid in row['controls']:
                c = controls.get(cid) or {}
                ev = _clip(c.get('evidence'))
                fa = _clip(c.get('failure'))
                w(f'- 控制 `{cid}`：证据＝{ev}；失败行为＝{fa}')
                w(f"  - 该控制自己的 `test` 字段＝`{c.get('test')}`，状态＝`{c.get('status')}`")
        else:
            w('- 控制：**无**（规则未声明运行时控制）')
        if row['tests']:
            for t in row['tests']:
                head, body = _snippet(index, t, root)
                w(f"- 用例 `{t}` → {head}")
                if body:
                    w('')
                    w('  ```python')
                    for ln in body:
                        w('  ' + ln)
                    w('  ```')
        else:
            w('- 用例：**无**')
        w('')
        w('| 判断 | 结论 |')
        w('|---|---|')
        w('| 控制回应了规则吗 | ☐ 是　☐ 否　☐ 无法判断 |')
        w('| 用例在验证该控制吗 | ☐ 是　☐ 否　☐ 无法判断 |')
        w('| 若不成立，性质 | ☐ 引用挂错　☐ 真缺口　☐ 不适用 |')
        w('| 备注 |  |')
        w('')
    w('---')
    w('')
    w('## 四、你签完之后怎么落账（命令，不是建议）')
    w('')
    w('```bash')
    w('# 1) 这份材料先登记（哈希当场存证）')
    w('python scripts/gov_run.py --accept-evidence --by <执行者> --reason "AUD-001-03 复核材料"')
    w('')
    w('# 2) 你对着清单写的结论，作为证据落盘（自己写，别让 Agent 代写判断）')
    w('#    evidence/aud001_sampling_review_<日期>.md')
    w('')
    w('# 3) 记录签署（reviewer 是你，执行者是 Agent——两者必须不同名）')
    w('export GOV_ACTING_IDENTITY=agent-runner')
    w('python scripts/record_signoff.py --assertion-id AUD-001-03 \\')
    w('  --reviewer slow-is-fast --role independent-reviewer --verdict approved \\')
    w('  --evidence evidence/aud001_sampling_review_<日期>.md \\')
    w('  --basis "<≥10 字：抽了哪几条、结论是什么、哪些不成立>")')
    w('')
    w('# 4) 投影 diff 看一眼，再落盘；矩阵变了就重生成 owner_worklist')
    w('python scripts/apply_signoffs.py --dry-run')
    w('python scripts/apply_signoffs.py --apply --by agent-runner')
    w('python scripts/export_owner_worklist.py')
    w('```')
    w('')
    w('> 若抽样发现有"真缺口"，`verdict` 不该写 `approved`——写 `needs-work` 也是有效结论，')
    w('> 而且比 `approved` 有用：它把缺口变成了下一步的工作项，而不是一个看起来干净的绿。')
    return '\n'.join(L) + '\n'


# ---------------------------------------------------------------- 指纹

def fingerprint(stats, rows, fp_src, picks):
    """指纹只覆盖"材料内容"，不覆盖散文。

    但**必须含抽样结果本身**：只改 `--sample` 条数时，统计与 rows 都不变，
    若指纹不含 picks，材料已经换了样本、`--check` 却仍然通过——那就是
    "算出来却没人看"的第三例。
    """
    payload = json.dumps({
        'src': fp_src,
        'stats': stats,
        'rows': [(r['rule'], r['tests'], r['missing']) for r in rows],
        'picks': [r['rule'] for r in picks],
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]


def build(root=ROOT):
    rules, catalog = _load(root)
    index = _test_index(root)
    stats, rows, controls = coverage(rules, catalog, index, root)
    diff = diff_report(rules, rows, controls, index, root)
    # 与 verify_executor_pin 同一 autocrlf 坑：Windows 磁盘 CRLF、仓库/CI LF，
    # 字节指纹必须先规范化，否则材料在 CI 上永远"过期"。
    src = hashlib.sha256(
        (Path(root) / 'rule-registry.json').read_bytes().replace(b'\r\n', b'\n') +
        (Path(root) / 'control-catalog.yaml').read_bytes().replace(b'\r\n', b'\n')
    ).hexdigest()[:12]
    picks = sample(rows, SAMPLE_N)
    fp = fingerprint(stats, rows, src, picks)
    return (render(stats, rows, controls, diff, picks, index, root, fp, rules),
            fp, diff, len(rules))


def main(argv=None):
    ap = argparse.ArgumentParser(description='AUD-001-03 复核材料生成器')
    ap.add_argument('--root', default=None)
    ap.add_argument('--out', default=None)
    ap.add_argument('--check', action='store_true',
                    help='只比对材料是否过期（不写文件）')
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else ROOT
    out = Path(args.out) if args.out else root / DEFAULT_OUT
    text, fp, diff, n_rules = build(root)

    if args.check:
        if not out.exists():
            print(f'FAIL(AUD-001-PACK): {out} 不存在——先跑一次生成')
            return 1
        old = out.read_text(encoding='utf8')
        m = re.search(r'材料指纹：`([0-9a-f]{12})`', old)
        if not m:
            print('FAIL(AUD-001-PACK): 现有材料里找不到指纹，无法判断是否过期')
            return 1
        if m.group(1) != fp:
            print(f'FAIL(AUD-001-PACK): 材料已过期（{m.group(1)} → {fp}）——'
                  f'规则或控制目录变了，重新生成')
            return 1
        print(f'PASS(AUD-001-PACK): 材料与当前注册表一致（{fp}）')
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding='utf8', newline='\n')
    print(f'已生成 {out}')
    print(f"  规则 {n_rules} · 悬空用例引用 {len(diff['dangling_tests'])} 处 · "
          f"孤儿控制 {len(diff['control_orphan'])} · 指纹 {fp}")
    if diff['dangling_tests']:
        print('  注意：差异报告里有悬空引用，抽样复核时应把这些列为待查项。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
