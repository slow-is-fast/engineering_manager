#!/usr/bin/env python3
"""把 `governance/signoffs.jsonl` 里的有效独立签署，翻译成验收矩阵断言上的
`signoff` 字段，从而闭合 EXC-01 人工项（executor/closure.py 已在 manual 分支消费该字段）。

设计要点（与治理铁律一致）：
- 本工具**不替任何人签署**、不伪造关闭。它只是把 `record_signoff.py` 已落证的人类
  决定从 jsonl 台账"搬运"到矩阵结构里——人类签名才是授权，本工具只是搬运工。
- 失败关闭：任一签署条目不合法 → **整批原子中止**，不写任何字段、不改任何文件。
- 校验复用 `record_signoff` 的硬约束：签署人==执行主体→拒（防自签）；role 不在三集合
  →拒；verdict 非 approved→拒；断言不存在→拒；证据文件缺失→拒；证据内容被改
  （哈希与存证不符）→拒。
- 默认 dry-run：只报告"哪些断言会被标记 closed、哪些条目非法（含原因）"，不触碰文件。
- `--apply` 才改写矩阵，且必须带 `--by`（谁执行了本次 apply，记入审计）。改写后由
  人类提交；本工具不自动 commit。
- **#6 自动翻绑定（opt-in）**：若设置环境变量 `GOV_REVIEW_AGENT`，则 `--by` 必须
  等于该 review-agent 身份，且其不得等于作者身份 `GOV_AUTHOR_IDENTITY`（落实
  `owner_designations.md` #6 的「执行者=review-agent 且 ≠ author」与防自批守卫）。
  未设置时维持原行为，向后兼容。

用法：
  python scripts/apply_signoffs.py                # dry-run，基于默认路径
  python scripts/apply_signoffs.py --apply --by <执行人>
  python scripts/apply_signoffs.py --signoffs <p> --matrix <p> --apply --by <执行人>
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 复用 record_signoff 的约束与哈希校验（导入安全：main 受 __main__ 保护）
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from record_signoff import INDEPENDENT_ROLES, _ev_hash  # noqa: E402

DEFAULT_SIGNOFFS = Path(__file__).resolve().parents[1] / 'governance' / 'signoffs.jsonl'
DEFAULT_MATRIX = Path(__file__).resolve().parents[1] / 'governance' / 'acceptance_matrix.json'


def load_signoffs(path: Path):
    if not path.is_file():
        return []
    out = []
    for ln in path.read_text(encoding='utf-8').splitlines():
        ln = ln.strip()
        if not ln:
            continue
        out.append(json.loads(ln))
    return out


def load_matrix(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _find_assertion(matrix, assertion_id):
    for iid, rec in (matrix.get('issues') or {}).items():
        for a in (rec.get('assertions') or []):
            if a.get('id') == assertion_id:
                return iid, a
    return None, None


def check_review_agent_binding(by):
    """#6 自动翻逻辑：把「翻断言」的执行者绑定到指定的独立 review-agent。
    仅当 GOV_REVIEW_AGENT 环境变量被设置时启用（opt-in），未设置则维持
    原有行为，避免破坏既有调用与测试。返回 (ok, reason)。
    """
    review_agent = os.environ.get('GOV_REVIEW_AGENT')
    if not review_agent:
        return True, 'opt_in_disabled'
    if by != review_agent:
        return False, 'executor_not_review_agent'
    author = os.environ.get('GOV_AUTHOR_IDENTITY')
    if author and by == author:
        return False, 'review_agent_is_author'
    return True, 'ok'


def validate_entry(entry, acting, matrix):
    """返回 (is_valid, reason)。任何不合法都导致整批中止。"""
    assertion_id = entry.get('assertion_id') or ''
    reviewer = entry.get('reviewer') or ''
    role = entry.get('role') or ''
    verdict = entry.get('verdict') or ''
    refs = entry.get('evidence_refs') or []
    stored_hash = entry.get('evidence_hash') or ''

    if reviewer == acting:
        return False, 'self_sign'
    if role not in INDEPENDENT_ROLES:
        return False, 'bad_role'
    if verdict != 'approved':
        return False, 'not_approved'
    iid, a = _find_assertion(matrix, assertion_id)
    if a is None:
        return False, 'unknown_assertion'
    if a.get('kind') != 'manual':
        return False, 'not_manual'
    if not refs:
        return False, 'no_evidence'
    for r in refs:
        if not Path(r).is_file():
            return False, f'evidence_missing:{r}'
    # 防"签完再改证据"：重新算哈希比对存证
    if _ev_hash(refs) != stored_hash:
        return False, 'evidence_hash_mismatch'
    return True, 'ok'


def build_signoff_field(entry, by):
    reviewed_at = entry.get('reviewed_at') or ''
    ts = datetime.now(timezone(timedelta(hours=8))).isoformat()
    return {
        'by': entry.get('reviewer'),
        'role': entry.get('role'),
        'ref': (entry.get('evidence_refs') or ['.'])[0],
        'date': reviewed_at[:10],
        'signature': entry.get('signature'),
        'applied_by': by,
        'applied_at': ts,
        # #6 审计增强：把翻转绑定到独立 review-agent 身份，并记录翻转时间。
        'review_agent': os.environ.get('GOV_REVIEW_AGENT') or by,
        'flipped_at': ts,
    }


def plan(matrix, entries, acting):
    """返回 (will_close[(assertion_id, iid)], invalid[(entry, reason)])。"""
    will_close, invalid = [], []
    for e in entries:
        ok, reason = validate_entry(e, acting, matrix)
        if ok:
            iid, _ = _find_assertion(matrix, e['assertion_id'])
            will_close.append((e['assertion_id'], iid, e.get('reviewer'), e.get('role')))
        else:
            invalid.append((e, reason))
    return will_close, invalid


def dry_run(matrix, entries, acting, by=None):
    if by:
        ok, reason = check_review_agent_binding(by)
        if not ok:
            print(f'ABORT(apply_signoffs): review-agent 绑定校验失败：{reason}')
            return 2
    will_close, invalid = plan(matrix, entries, acting)
    print(f'DRY-RUN: {len(entries)} 条签署条目，{len(will_close)} 条可闭合，'
          f'{len(invalid)} 条非法')
    for aid, iid, rev, role in will_close:
        print(f'  WOULD CLOSE  {aid} (issue {iid}) <- {rev}/{role}')
    for e, reason in invalid:
        aid = e.get('assertion_id', '?')
        print(f'  SKIP(invalid) {aid}: {reason}')
    if invalid:
        print('  存在非法条目：--apply 将原子中止（不写任何字段）。')
    return 0 if not invalid else 2


def apply(matrix_path, matrix, entries, acting, by):
    ok, reason = check_review_agent_binding(by)
    if not ok:
        print(f'ABORT(apply_signoffs): review-agent 绑定校验失败：{reason}')
        return 2
    will_close, invalid = plan(matrix, entries, acting)
    if invalid:
        print(f'ABORT(apply_signoffs): {len(invalid)} 条非法签署，整批中止，未改动文件：')
        for e, reason in invalid:
            print(f'  INVALID {e.get("assertion_id","?")}: {reason}')
        return 2
    if not will_close:
        print('NOTHING TO APPLY: 没有可闭合的有效签署。')
        return 0
    for aid, iid, rev, role in will_close:
        _, a = _find_assertion(matrix, aid)
        a['signoff'] = build_signoff_field(next(e for e in entries
                                                if e['assertion_id'] == aid), by)
        print(f'  CLOSED {aid} (issue {iid}) <- {rev}/{role}')
    matrix_path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2),
                           encoding='utf-8')
    print(f'APPLIED: {len(will_close)} 条断言已标记 closed -> {matrix_path}')
    print('下一步：人工 review 改动后提交（本工具不自动 commit）。')
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description='把有效独立签署翻译为矩阵断言 signoff 字段')
    ap.add_argument('--signoffs', default=str(DEFAULT_SIGNOFFS),
                    help='signoffs.jsonl 路径')
    ap.add_argument('--matrix', default=str(DEFAULT_MATRIX),
                    help='acceptance_matrix.json 路径')
    ap.add_argument('--apply', action='store_true', help='真正改写矩阵（默认 dry-run）')
    ap.add_argument('--by', default=None, help='执行本次 apply 的人/主体（审计用，apply 时必填）')
    ap.add_argument('--acting', default=os.environ.get('GOV_ACTING_IDENTITY', 'slow-is-fast'),
                    help='执行主体身份（用于防自签比对，默认读 GOV_ACTING_IDENTITY）')
    args = ap.parse_args()

    signoffs_path = Path(args.signoffs)
    matrix_path = Path(args.matrix)
    if not matrix_path.is_file():
        sys.exit(f'FAIL(apply_signoffs): 矩阵不存在 {matrix_path}')
    entries = load_signoffs(signoffs_path)
    if not entries:
        print(f'NO SIGNINGS: {signoffs_path} 无条目（signoffs.jsonl 当前为空）。')
        sys.exit(0)
    matrix = load_matrix(matrix_path)

    if args.apply:
        if not args.by:
            sys.exit('FAIL(apply_signoffs): --apply 必须带 --by（谁执行了本次 apply）')
        sys.exit(apply(matrix_path, matrix, entries, args.acting, args.by))
    else:
        sys.exit(dry_run(matrix, entries, args.acting, by=args.by))


if __name__ == '__main__':
    main()
