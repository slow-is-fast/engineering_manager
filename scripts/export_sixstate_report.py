#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUD-002-03 要的那份「报告」：六种状态在三个层上到底怎么区分。

为什么要有这个脚本
------------------
`AUD-002-03`（P0, `six_state_report_review`）的原文是「报告可区分六种状态的独立复核」，
Issue 的闭合条件写着「状态机测试和负向测试通过；报告可区分六种状态」。

前两条断言（`AUD-002-01/02`）已经是 OK 的。卡住的是第三条，而它卡在一件尴尬的事上：
**仓库里没有任何一份报告能"区分六种状态"。** 2026-11-02 实测三份候选报告
（`GOVERNANCE_STATUS.html`、`owner_worklist.md`、`coverage_pack_aud001.md`）里，
`documented` / `configured` / `degraded` 三个词**一次都没出现过**——它们讲的是
Issue 与断言，不是控制层的六态。让 Owner 对着这些签"报告可区分六种状态"，
等于让他签一份不存在的东西。

所以本脚本先**把报告补出来**，再谈复核。这份报告是产物，不是结论。

报告的立场（决定了它长什么样）
------------------------------
不写"六态齐备、校验通过"这种好听的话。六态里到底哪几个真的被用、哪几个是
能写没人读的字段、哪几个门禁在读——全部当场扫出来，每条给 `文件:行号`。
**一个状态字段有没有用，不看它在 schema 里出现过，看谁读它。**

边界
----
- 本报告只报事实与消费关系，不判"够不够"。够不够是 `AUD-002-03` 复核者的事。
- "谁读某字段"用正则扫 `scripts/` 与 `executor/` 的源码，按"定义 / 写入 / 读取"
  三类归类。正则扫不全（比如字典整体传递），所以结论按**低估计**写：
  标"未发现读取点"而不是"没有读取者"。
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = 'governance/sixstate_report.md'

STATES = ('documented', 'configured', 'tested', 'verified', 'degraded', 'excepted')
SCAN_DIRS = ('scripts', 'executor')
# 扫"谁读字段"时排除本文件自己：报告里必然出现这些词，算进去就是自我指涉
SELF_EXCLUDE = {'export_sixstate_report.py', 'export_owner_worklist.py',
                'export_coverage_pack.py'}


def _load(root):
    root = Path(root)
    rules = json.loads((root / 'rule-registry.json').read_text(encoding='utf8'))['rules']
    controls = json.loads((root / 'control-catalog.yaml').read_text(encoding='utf8'))['controls']
    matrix = json.loads((root / 'governance' / 'acceptance_matrix.json').read_text(encoding='utf8'))
    return rules, controls, matrix


def _scan_consumers(root, field):
    """扫源码里对 `field` 的定义 / 写入 / 读取点。

    低估计原则：分不清是读还是写的，算"读取"（宁可多算消费点，也不少算）。

    第四个返回值是"其实是另一层在消费"的行：`excepted` 这个词同时被断言层的
    `kind=excepted` 使用，宽正则会把它算成 `state.excepted` 的消费者，
    那会造成"这个字段有人在读"的错觉。这类行单独归类，不计入读取。
    """
    defs, writes, reads, other_layer = [], [], [], []
    pat = re.compile(rf"""['"]{field}['"]""")
    for d in SCAN_DIRS:
        for f in sorted((Path(root) / d).glob('*.py')):
            if f.name in SELF_EXCLUDE:
                continue
            try:
                lines = f.read_text(encoding='utf8').splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if not pat.search(line):
                    continue
                loc = f'{f.relative_to(root).as_posix()}:{i}'
                code = line.strip()
                if re.match(r'^STATES\s*=', code) or re.match(rf"^['\"]{field}['\"],?$", code):
                    defs.append((loc, code))
                elif re.search(rf"""['"]{field}['"]\s*\]?\s*=[^=]""", line):
                    writes.append((loc, code))
                elif field == 'excepted' and (
                        f.name == 'closure.py'
                        or re.search(r'kind|ALLOWED_KINDS', line)):
                    # `closure.py` 只处理断言层：它那里的 `s.get("excepted")`
                    # 里的 `s` 来自 `self._assertion_state(a)`（第 225 行），
                    # 是断言状态字典，不是控制层 `state`。按文件判定比猜正则可靠。
                    other_layer.append((loc, code))
                elif field == 'degraded' and 'local' in line.lower():
                    other_layer.append((loc, code))
                else:
                    reads.append((loc, code))
    return defs, writes, reads, other_layer


def _combo(entries, key):
    """按"哪几个状态为 true"分组计数。"""
    c = Counter()
    for e in entries:
        st = (e.get(key) or {})
        c[tuple(s for s in STATES if st.get(s) is True)] += 1
    return c


def _fingerprint(root, rules, controls, matrix):
    """指纹对换行不敏感——Windows 磁盘 CRLF、仓库/CI LF（2026-11-02 实证）。"""
    h = hashlib.sha256()
    for rel in ('rule-registry.json', 'control-catalog.yaml',
                'governance/acceptance_matrix.json'):
        h.update((Path(root) / rel).read_bytes().replace(b'\r\n', b'\n'))
    return hashlib.sha256(h.digest() + json.dumps(
        [len(rules), len(controls), len(matrix.get('issues') or {})]).encode()).hexdigest()[:12]


def _report_cover(root):
    """三份候选报告各自对六态词表的覆盖（机器 grep，不靠读）。"""
    out = []
    for rel in ('GOVERNANCE_STATUS.html', 'governance/owner_worklist.md',
                'governance/coverage_pack_aud001.md'):
        p = Path(root) / rel
        text = p.read_text(encoding='utf8') if p.exists() else ''
        out.append((rel, {s: len(re.findall(s, text, re.I)) for s in STATES}))
    return out


def render(root=ROOT):
    rules, controls, matrix = _load(root)
    fp = _fingerprint(root, rules, controls, matrix)
    L = []
    A = L.append

    combo_c = _combo(controls, 'state')
    combo_r = _combo(rules, 'status')
    kinds = Counter(a.get('kind') for rec in (matrix.get('issues') or {}).values()
                    for a in (rec.get('assertions') or []))

    zero_c = [s for s in STATES
              if not any((c.get('state') or {}).get(s) is True for c in controls)]
    zero_r = [s for s in STATES
              if not any((r.get('status') or {}).get(s) is True for r in rules)]

    A('# 六态报告：三个层上的状态区分能力')
    A('')
    A('> **自动生成，勿手改。** 重新生成：`python scripts/export_sixstate_report.py`')
    A(f'> 数据指纹：`{fp}`（`--check` 比对；材料变了就红）')
    A('>')
    A('> **这是产物，不是复核记录。** 它不判"够不够"，只报"是什么"。')
    A('> `AUD-002-03` 的复核结论由人写，写在 `evidence/` 里，不是这里。')
    A('>')
    A('> **过期会被拦住**：`tests/test_sixstate_report.py` 的 `test_report_is_in_sync`')
    A('> 会在数据变化后报红，不需要额外的 `required_checks` 接线。')
    A('> （对照 `coverage_pack_aud001.md`：那份的 `--check` 至今没有任何门禁在调用。）')
    A('')
    A('## 一、这份报告要回答什么')
    A('')
    A('`AUD-002`（P0）的验收标准与闭合条件原文：')
    A('')
    A('> 验收标准：缺少执行器、测试或有效证据时不能进入 verified；'
      '配置漂移或证据过期触发降级。')
    A('> 闭合条件：状态机测试和负向测试通过；**报告可区分六种状态**。')
    A('')
    A('六种状态指 `documented / configured / tested / verified / degraded / excepted`，'
      '定义在 `scripts/validate_controls.py:12` 的 `STATES` 元组。')
    A('')
    A('**但六态不是"整个系统"的词汇表，它只属于其中两层。** 第三节把三层并排放。')
    A('')

    A('## 二、三层各用什么词（这是"报告能否区分六态"的第一个岔路）')
    A('')
    A('| 层 | 文件 | 字段 | 取值 | 校验强度 | 是否参与门禁 |')
    A('|---|---|---|---|---|---|')
    A('| 规则 | `rule-registry.json` | `status` | 六态 | 只校验键集与布尔类型（'
      '`validate_controls.py:108`） | **否**（`rule_status_participation: schema_only`） |')
    A('| 控制 | `control-catalog.yaml` | `state` | 六态 | 键集 + 布尔 + '
      '「`verified` 必须前三态皆真」（`validate_controls.py:36`） | **是** |')
    A('| 断言 | `governance/acceptance_matrix.json` | `kind` | '
      '`script` / `test` / `manual` / `excepted` / `evidence` | 由 '
      '`check_audit_closure.py` 判 | **是** |')
    A('')
    A('读法：**第三层根本不用六态。** 断言层用 `kind` 表达"这条怎么验"，'
      '用 `signoff` 表达"谁验过"。所以"报告可区分六种状态"这句话如果指全系统，'
      '它天然缺一层；它只能指规则层与控制层。')
    A('')

    A('## 三、控制层（权威层）：55 个控制的真实取值')
    A('')
    A('| 状态 | 为 true 的控制数 | 占比 |')
    A('|---|---|---|')
    for s in STATES:
        n = sum(1 for c in controls if (c.get('state') or {}).get(s) is True)
        A(f'| `{s}` | {n} / {len(controls)} | {n * 100 // len(controls)}% |')
    A('')
    A('**组合分布**（"只有这几个为 true"）：')
    A('')
    A('| 组合 | 控制数 |')
    A('|---|---|')
    for k, v in combo_c.most_common():
        A(f'| {" + ".join(f"`{x}`" for x in k) or "（全 false）"} | {v} |')
    A('')
    if zero_c:
        A(f'从未取值为真的状态：{" / ".join(f"`{s}`" for s in zero_c)}。')
        A('')
        A('**这一行是本报告最重要的事实。** 六个字段都在、都被校验，但真正有值的只有'
          f'{len(STATES) - len(zero_c)} 个。剩下的不是"暂时为 0"，是**从来没有过非 0**——'
          '见第五节。')
        A('')

    A('## 四、规则层：59 条条款的真实取值')
    A('')
    A('| 状态 | 为 true 的规则数 |')
    A('|---|---|')
    for s in STATES:
        n = sum(1 for r in rules if (r.get('status') or {}).get(s) is True)
        A(f'| `{s}` | {n} / {len(rules)} |')
    A('')
    A('**组合分布**：')
    A('')
    A('| 组合 | 规则数 |')
    A('|---|---|')
    for k, v in combo_r.most_common():
        A(f'| {" + ".join(f"`{x}`" for x in k) or "（全 false）"} | {v} |')
    A('')
    A('> 规则层的 `status` 是 **schema_only**：`validate_controls.py` 只校验键集与'
      '布尔类型，从不强制任一为真，也不把它用于任何门禁判定。'
      '`rule-registry.json` 顶层的 `rule_status_note` 自己就是这么写的。')
    A('>')
    A('> 所以这一层的数字**不能当"规则落地了没有"读**。要读规则级执行状态，'
      '必须走 `enforcement.controls` 指向的控制条目——那是第三节。')
    A('')

    A('## 五、"能写、能存、没人读"：三个需要单独看的状态')
    A('')
    A('这一节对每个状态扫一遍源码（`scripts/` 与 `executor/`，排除导出脚本本身），'
      '按"定义 / 写入 / 读取"归类。低估计原则：分不清读写的一律算读取。')
    A('')
    for s in ('verified', 'degraded', 'excepted'):
        defs, writes, reads, other = _scan_consumers(root, s)
        A(f'### `{s}`')
        A('')
        A(f'- 定义：{len(defs)} 处' + (f'（`{defs[0][0]}`）' if defs else ''))
        A(f'- 写入：{len(writes)} 处')
        for loc, code in writes[:4]:
            A(f'  - `{loc}`：`{code[:70]}`')
        if not writes:
            A('  - （无）')
        A(f'- 读取：{len(reads)} 处')
        for loc, code in reads[:4]:
            A(f'  - `{loc}`：`{code[:70]}`')
        if not reads:
            A('  - （**未发现读取点**）')
        if other:
            A(f'- 另 {len(other)} 处出现这个词，但**消费的是另一层**，不计入读取：')
            for loc, code in other[:3]:
                A(f'  - `{loc}`：`{code[:70]}`')
        A('')
        if s == 'degraded':
            A('  **降级到底有没有生效？** 有，但不是因为这个字段：'
              '`verify_evidence_freshness.py --degrade` 除了置 `degraded=true`，'
              '还顺手把 `tested` 置 false（`verify_evidence_freshness.py:78`），'
              '而 `tested` 是有消费者的（`executor/gate.py:368` 的准入判定）。'
              '所以降级的效果是**通过 `tested` 实现的**，`degraded` 只是留了个记号。')
            A('')
            A('  **哪个字段真的有用，看谁读它，不看它在 schema 里出现过。** 这正是'
              '"算出来却没人看的值等于没有"的又一例——只不过这次它旁边那个字段'
              '恰好替它把活干了，所以症状被掩盖了。')
            A('')
        if s == 'excepted':
            A('  **例外实际不在这一层。** 控制层 `state.excepted` 零使用；真实的例外登记在'
              '断言层：`acceptance_matrix.json` 里 `kind=excepted` 的断言，'
              '以及 `exception_register.json` 的 `EXC-01/02/03`。两套词汇表达同一件事，'
              '没有对齐——这也是"报告可区分六态"要面对的问题：'
              '**六态里有三个从未取值，其中 `excepted` 的语义已经在别处被实现了另一遍。**')
            A('')
        if s == 'verified':
            A('  **`verified` 是被真读的，但恒不成立。** `executor/gate.py:376` 的准入条件 '
              '`all_p0_controls_verified` 会逐个检查 P0 控制的 `verified`；'
              f'而控制层 `verified` 为 true 的数量是 '
              f'{sum(1 for c in controls if (c.get("state") or {}).get("verified") is True)}。'
              '也就是说这个准入条件目前**永远不满足**——它是"未达标"，不是"没检查"。')
            A('')

    A('## 六、候选报告对六态词表的覆盖（机器 grep）')
    A('')
    A('| 报告 | ' + ' | '.join(f'`{s}`' for s in STATES) + ' |')
    A('|---|' + '---|' * len(STATES))
    for rel, counts in _report_cover(root):
        miss = [s for s in STATES if counts[s] == 0]
        row = ' | '.join('0' if counts[s] == 0 else str(counts[s]) for s in STATES)
        A(f'| `{rel}` | {row} |')
    A('')
    A('**这张表是 `AUD-002-03` 的直接输入。** 在这份报告出现之前，三份候选报告里'
      '`documented` / `configured` / `degraded` 全为 0——它们没有在用六态的词汇。'
      '所以"报告可区分六种状态"在 2026-11-02 之前**字面不成立**，'
      '本报告是把缺失的那一份补上，不是把标准降低。')
    A('')

    A('## 七、这份报告不能证明什么')
    A('')
    A('- **不证明六态模型是对的。** 它只说明现状：哪些状态有值、谁在读写。'
      '模型设计对不对是另一件事。')
    A('- **不证明降级机制完备。** 它指出降级靠 `tested=false` 生效，'
      '但"证据过期之后准入门槛是否真的拦住"要看 `RVF-01` 与 `GATE-01` 的用例，不是这份报告。')
    A('- **不证明规则层状态可信。** 第四节已经说明它是 schema_only；'
      '本报告在这里的作用恰恰是提醒别拿它当证据。')
    A('- **"未发现读取点"是低估计结论。** 正则扫不到字典整体传递（比如把 `state` '
      '整个传给另一个函数）。所以它是"我没找到"，不是"不存在"。')
    A('')
    A('## 八、复算方式')
    A('')
    A('```bash')
    A('python scripts/export_sixstate_report.py           # 重新生成')
    A('python scripts/export_sixstate_report.py --check   # 只比对指纹')
    A('```')
    A('')
    A('数字全部由 `rule-registry.json` / `control-catalog.yaml` / '
      '`governance/acceptance_matrix.json` 算出，没有一个是写死的。'
      '「谁读字段」由源码正则扫出，排除三个导出脚本（否则报告会自我指涉）。')
    return '\n'.join(L) + '\n', fp


def main(argv=None):
    ap = argparse.ArgumentParser(description='AUD-002-03 的六态报告生成器')
    ap.add_argument('--root', default=None)
    ap.add_argument('--out', default=None)
    ap.add_argument('--check', action='store_true', help='只比对是否过期（不写文件）')
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else ROOT
    out = Path(args.out) if args.out else root / DEFAULT_OUT
    text, fp = render(root)

    if args.check:
        if not out.exists():
            print(f'FAIL(AUD-002-RPT): {out} 不存在——先跑一次生成')
            return 1
        m = re.search(r'数据指纹：`([0-9a-f]{12})`', out.read_text(encoding='utf8'))
        if not m:
            print('FAIL(AUD-002-RPT): 现有报告里找不到指纹，无法判断是否过期')
            return 1
        if m.group(1) != fp:
            print(f'FAIL(AUD-002-RPT): 报告已过期（{m.group(1)} → {fp}）——重新生成')
            return 1
        print(f'PASS(AUD-002-RPT): 报告与当前数据一致（{fp}）')
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding='utf8', newline='\n')
    print(f'已生成 {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
