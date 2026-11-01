#!/usr/bin/env python3
"""T-QA-04b：必需检查接线校验（控制 BASE-01 / T-QA-04 的第二半）。

`verify_quality_baseline.py` 只保证 `required_checks` **列表本身**完整、
且指向的文件存在。它保证不了另一件事：**列表里的每一条，真的被 CI 调用过**。
2026-11-01 实测：required_checks 已增至 15 项，而 workflow 只有 13 个
`gov_run.py --check` 步骤——`check_control_refs.py`（9fbe189 引入）与
`matrix_caretaker.py`（e29e2a8 接入）注册了却从未在 CI 落地。本地全套
unittest 全绿对此毫无感知（suite 跑测试，不记账），直到推送到 CI 才被
`gov_run.py --verify` 的「本次运行必需检查是否全部落地」拦下（exit 5）。

这属于最隐蔽的一类"控制没生效"：它看起来被管住了（有编号、在基线里、
文件也存在），实际上没有执行者。所以把检测前移——不必等推送：

  A. 双向核对 required_checks <-> 所有 workflow 里的 `--check <path>`
     - 基线里有、workflow 里没有  -> 失败（注册了但没跑）
     - workflow 里有、基线里没有  -> 失败（跑了但没记账，或漏更新基线）
  B. 步骤指向的文件必须存在（打错路径的检查永远绿不了，却可能被误读成"已覆盖"）
  C. 不可判定即拒绝：找不到 workflow / 一个 `--check` 都没有 -> 失败关闭

边界（诚实声明）
----------------
- 只认 `gov_run.py --check <path>` 这一种接线方式。直接 `python scripts/x.py`
  的步骤不在本检查范围（而那种写法本身就不记账，属于另一个问题）。
- 被 `#` 注释掉的行不算执行——注释里的命令不产生事件。
- 本检查不判断检查内容对不对，只判断「注册的都被接了线、接线的都被注册」。

用法：python scripts/verify_required_checks_wired.py [repo_root]
退出码：0 通过；非零失败（失败关闭）。
"""
import json
import re
import sys
from pathlib import Path

BASE = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1])
BASELINE_REL = 'governance/quality_baseline.json'
WORKFLOW_DIR = BASE / '.github' / 'workflows'

# `python scripts/gov_run.py --check scripts/xxx.py`；允许引号，不支持跨行续行
CHECK_RE = re.compile(r'gov_run\.py\s+--check\s+([^\s"\'#]+)')


def fail(msg):
    sys.exit(f'FAIL(T-QA-04b): {msg}')


def strip_comment(line):
    """去掉整行注释与行内注释。注释里的命令不会执行，也不产生审计事件。"""
    if line.lstrip().startswith('#'):
        return ''
    return line.split('#', 1)[0]


def wired_targets():
    """workflow 里所有被 `--check` 调用的目标路径 -> 出现的文件名集合。"""
    if not WORKFLOW_DIR.is_dir():
        fail(f'no workflow directory at {WORKFLOW_DIR} — 无法判定接线，拒绝放行')
    files = sorted(list(WORKFLOW_DIR.glob('*.yml')) + list(WORKFLOW_DIR.glob('*.yaml')))
    if not files:
        fail(f'no workflow files under {WORKFLOW_DIR} — 无法判定接线，拒绝放行')
    found = {}
    for wf in files:
        for raw in wf.read_text(encoding='utf8').splitlines():
            line = strip_comment(raw)
            if 'gov_run.py' not in line:
                continue
            for target in CHECK_RE.findall(line):
                found.setdefault(target.strip('"\''), set()).add(wf.name)
    if not found:
        fail('no `gov_run.py --check <path>` step found in any workflow — '
             '没有任何必需检查会被记账，这不可能是一个健康状态')
    return found


def main():
    bp = BASE / BASELINE_REL
    if not bp.is_file():
        fail(f'missing {BASELINE_REL}')
    try:
        baseline = json.loads(bp.read_text(encoding='utf8'))
    except json.JSONDecodeError as exc:
        fail(f'{BASELINE_REL} is not valid JSON: {exc}')

    required = baseline.get('required_checks') or []
    if not required:
        fail('required_checks is empty — 没有必需检查等于没有基线')
    if any(not isinstance(c, str) or not c.strip() for c in required):
        fail(f'required_checks contains non-string entry: {required!r}')

    wired = wired_targets()
    req_set, wired_set = set(required), set(wired)

    # A1. 注册了但没接线
    unwired = sorted(req_set - wired_set)
    # A2. 接线了但没注册（多跑不记账，或漏更新基线）
    unregistered = sorted(wired_set - req_set)
    # B. 接线目标文件必须存在
    missing_files = sorted(t for t in wired_set if not (BASE / t).exists())

    problems = []
    if unwired:
        problems.append('required_checks 里这些项没有对应的 CI --check 步骤'
                        f'（注册了但不会执行）：{unwired}')
    if unregistered:
        problems.append('CI 里有这些 --check 步骤，但 required_checks 未收录'
                        f'（跑了但不在基线内）：{unregistered}')
    if missing_files:
        problems.append(f'CI 步骤指向不存在的文件：{missing_files}')
    if problems:
        for p in problems:
            print(f'  - {p}')
        fail('必需检查与 CI 接线不一致（双向核对）——注册不等于执行，'
             '执行不等于记账；两者必须闭合')

    print(f'PASS(T-QA-04b): {len(req_set)} required checks all wired in CI '
          f'({len(wired)} --check steps across workflow files, bidirectional match)')
    for t in sorted(wired_set):
        print(f'  - {t}  <- {", ".join(sorted(wired[t]))}')


if __name__ == '__main__':
    main()
