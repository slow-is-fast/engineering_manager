#!/usr/bin/env python3
"""matrix_caretaker — 数据/证据矩阵的只读 caretaker（巡检 + 告警 + 留痕）。

阻塞点 #3（AUD-016-04）决策 C：数据/证据矩阵的 accountable owner 由自动化
caretaker agent 担任。本脚本是该决策的**最小可落地**实现：

  - 仅读 governance/acceptance_matrix.json、control_coverage.json、
    evidence_ledger.json 三份矩阵；
  - 校验结构不变量（字段完整性、disposition 有 owner、evidence 有 sha256、
    断言 id 唯一等）——任一违反 → 退出 2（fail-closed，硬失败）；
  - 与上次运行的快照比对，告警「结构指纹变化（新增/消失的 issue / 断言 /
    evidence）」——默认仅告警（退出 0，非阻塞），`--strict` 或环境变量
    CARETAKER_STRICT=1 时升级为退出 3（阻塞）；
  - **fail-closed 仅告警不写治理文件**：本脚本绝不修改上述三份 JSON 的语义，
    任何「关闭断言 / 改矩阵」的越权动作一律不做；如需裁定请走 #6 签署流程。

退出码：
  - 0：结构健康；若为首次运行则写基线，无漂移（或漂移仅告警并刷新基线）；
  - 2：发现结构不变量违反（corruption），硬失败；
  - 3：检测到与上次快照的漂移，且处于 --strict 模式。

本脚本只写自己的状态文件（--state，默认仓库根 .caretaker_state.json，已被
.gitignore 忽略），不触碰治理 JSON。
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / '.caretaker_state.json'
ALLOWED_KINDS = {'test', 'script', 'evidence', 'manual', 'unimplemented', 'excepted'}
DISPOSITION_TYPES = {'audit_driven', 'defense_in_depth'}


def _load(path):
    if not path.is_file():
        sys.exit(f'FAIL(caretaker): 治理文件缺失 {path}')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:  # noqa: BLE001 - 解析失败要直接报红
        sys.exit(f'FAIL(caretaker): 解析失败 {path}: {e}')


def check_matrix(doc, problems):
    issues = (doc or {}).get('issues')
    if not isinstance(issues, dict):
        problems.append('acceptance_matrix.issues 缺失或非对象')
        return
    seen = set()
    for iid, rec in issues.items():
        if not isinstance(rec, dict):
            problems.append(f'issue {iid} 非对象')
            continue
        asrts = rec.get('assertions')
        if not isinstance(asrts, list):
            problems.append(f'issue {iid}.assertions 缺失或非数组')
            continue
        for a in asrts:
            aid = (a or {}).get('id')
            if not aid:
                problems.append(f'issue {iid} 含无 id 断言')
                continue
            if aid in seen:
                problems.append(f'断言 id 重复: {aid}')
            seen.add(aid)
            if (a or {}).get('kind') not in ALLOWED_KINDS:
                problems.append(f'断言 {aid} 非法 kind: {(a or {}).get("kind")!r}')


def check_coverage(doc, problems):
    dispositions = (doc or {}).get('dispositions')
    if not isinstance(dispositions, dict):
        problems.append('control_coverage.dispositions 缺失或非对象')
        return
    for key, d in dispositions.items():
        if not isinstance(d, dict):
            problems.append(f'disposition {key} 非对象')
            continue
        if not d.get('owner'):
            problems.append(f'disposition {key} 缺 owner')
        dtype = d.get('type')
        if dtype not in DISPOSITION_TYPES:
            problems.append(f'disposition {key} 非法 type: {dtype!r}')
            continue
        if dtype == 'audit_driven' and not d.get('issue'):
            problems.append(f'disposition {key}(audit_driven) 缺 issue')
        if dtype == 'defense_in_depth' and not d.get('derived_from'):
            problems.append(f'disposition {key}(defense_in_depth) 缺 derived_from')


def check_ledger(doc, problems):
    items = (doc or {}).get('items')
    if not isinstance(items, list):
        problems.append('evidence_ledger.items 缺失或非数组')
        return
    for it in items:
        if not (it or {}).get('id'):
            problems.append('evidence_ledger 含无 id 条目')
            continue
        if not (it or {}).get('sha256'):
            problems.append(f'evidence {(it or {}).get("id")} 缺 sha256')


def fingerprint(matrix, coverage, ledger):
    m = [(iid, sorted((a or {}).get('id') for a in rec.get('assertions', [])))
         for iid, rec in sorted((matrix or {}).get('issues', {}).items())]
    c = sorted((k, d.get('owner'))
               for k, d in (coverage or {}).get('dispositions', {}).items())
    e = sorted((it or {}).get('id') for it in (ledger or {}).get('items', []))
    raw = json.dumps({'m': m, 'c': c, 'e': e}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _now():
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def _save_state(state_path, fp, counts):
    state_path.write_text(json.dumps(
        {'fingerprint': fp, 'counts': counts, 'updated_at': _now()},
        ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description='数据/证据矩阵 caretaker（只读巡检）')
    ap.add_argument('--matrix', default=str(ROOT / 'governance' / 'acceptance_matrix.json'))
    ap.add_argument('--coverage', default=str(ROOT / 'governance' / 'control_coverage.json'))
    ap.add_argument('--ledger', default=str(ROOT / 'governance' / 'evidence_ledger.json'))
    ap.add_argument('--state', default=str(DEFAULT_STATE),
                    help='快照状态文件路径（默认仓库根 .caretaker_state.json，被 gitignore）')
    ap.add_argument('--no-state', action='store_true',
                    help='不读/写快照（仅做当次结构校验，不做漂移比对）')
    ap.add_argument('--strict', action='store_true',
                    help='漂移视为失败（退出 3）；默认漂移仅告警（退出 0）')
    args = ap.parse_args()

    strict = args.strict or os.environ.get('CARETAKER_STRICT') == '1'

    matrix = _load(Path(args.matrix))
    coverage = _load(Path(args.coverage))
    ledger = _load(Path(args.ledger))

    problems = []
    check_matrix(matrix, problems)
    check_coverage(coverage, problems)
    check_ledger(ledger, problems)
    if problems:
        print(f'FAIL(caretaker): 发现 {len(problems)} 处结构不变量违反：')
        for p in problems:
            print(f'  - {p}')
        sys.exit(2)
    print('OK(caretaker): 三份矩阵结构不变量通过')

    if args.no_state:
        sys.exit(0)

    state_path = Path(args.state)
    counts = {
        'issues': len((matrix or {}).get('issues', {})),
        'assertions': sum(len(r.get('assertions', [])) for r in (matrix or {}).get('issues', {}).values()),
        'dispositions': len((coverage or {}).get('dispositions', {})),
        'evidence': len((ledger or {}).get('items', [])),
    }
    fp = fingerprint(matrix, coverage, ledger)

    if not state_path.is_file():
        _save_state(state_path, fp, counts)
        print(f'BASELINE(caretaker): 首次运行，已写基线 -> {state_path}')
        print(f'  计数: issues={counts["issues"]} assertions={counts["assertions"]} '
              f'dispositions={counts["dispositions"]} evidence={counts["evidence"]}')
        sys.exit(0)

    try:
        prev = json.loads(state_path.read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001 - 状态损坏则按「无基线」处理，重新写
        prev = None

    if prev and prev.get('fingerprint') == fp:
        print('OK(caretaker): 与上次快照一致，无漂移')
        sys.exit(0)

    print('DRIFT(caretaker): 检测到与上次快照的结构指纹变化（告警，不修改治理文件）：')
    print(f'  - 指纹: {prev.get("fingerprint", "<none>")[:12]}... -> {fp[:12]}...')
    if prev:
        pc = prev.get('counts', {})
        print(f'  上次计数: issues={pc.get("issues")} assertions={pc.get("assertions")} '
              f'evidence={pc.get("evidence")}')
    print(f'  本次计数: issues={counts["issues"]} assertions={counts["assertions"]} '
          f'evidence={counts["evidence"]}')
    print('  注：caretaker 仅告警，不修改治理文件；如需裁定请走 #6 签署流程。')
    # 刷新基线（留痕），避免在常态运行里对同一变化反复告警
    _save_state(state_path, fp, counts)
    sys.exit(3 if strict else 0)


if __name__ == '__main__':
    main()
