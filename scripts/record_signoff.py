#!/usr/bin/env python3
"""记录一条独立复核签署（AUD 验收断言层 manual 断言的关闭前置）。

本工具是 EXC-01（第二人类主体不可达）的落地脚手架：把
"谁 / 何时 / 基于什么证据 / 以什么独立角色 / 给什么结论"结构化落证到
`governance/signoffs.jsonl`（append-only）。

关键防自签控制：签署人身份不得等于本项目"执行主体身份"
（`GOV_ACTING_IDENTITY`，即跑测试 / Agent 那一方），且必须声明独立角色——
直接把 EXC-01 禁止的"自己审自己"做成技术不可行。

本工具**不替任何人签署**；它只记录人类复核者主动提交的内容。未签署前，
对应 manual 断言仍按 `acceptance_matrix.json` 标记为 manual（未被关闭）。
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

DEFAULT_STORE = Path(__file__).resolve().parents[1] / 'governance' / 'signoffs.jsonl'
INDEPENDENT_ROLES = {'independent-reviewer', 'owner', 'security-owner'}
VALID_VERDICTS = {'approved', 'rejected', 'needs-work'}


def _canon(entry: dict) -> str:
    return json.dumps(entry, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def _ev_hash(refs) -> str:
    h = hashlib.sha256()
    for r in sorted(refs):
        p = Path(r)
        blob = p.read_bytes() if p.exists() else b'<missing>'
        h.update(r.encode('utf-8') + b'\0' + blob)
    return h.hexdigest()


def record(args, store=DEFAULT_STORE) -> int:
    acting = os.environ.get('GOV_ACTING_IDENTITY', 'slow-is-fast')

    reviewer = (args.reviewer or '').strip()
    if not reviewer:
        sys.exit('FAIL(SIGNOFF): reviewer 不能为空')
    if reviewer == acting:
        sys.exit(f'FAIL(SIGNOFF): 签署人 {reviewer!r} 等于执行主体 '
                 f'{acting!r}，禁止自签（EXC-01 要求独立第二主体）')

    role = args.role
    if role not in INDEPENDENT_ROLES:
        sys.exit(f'FAIL(SIGNOFF): role {role!r} 不在允许集合 '
                 f'{sorted(INDEPENDENT_ROLES)}')

    assertion_id = (args.assertion_id or '').strip()
    if not assertion_id:
        sys.exit('FAIL(SIGNOFF): assertion_id 不能为空')

    if args.verdict not in VALID_VERDICTS:
        sys.exit(f'FAIL(SIGNOFF): verdict {args.verdict!r} 非法，'
                 f'须为 {sorted(VALID_VERDICTS)}')

    refs = [r.strip() for r in (args.evidence or '').split(',') if r.strip()]
    if not refs:
        sys.exit('FAIL(SIGNOFF): 至少一条 evidence_ref 必填')

    basis = (args.basis or '').strip()
    if len(basis) < 10:
        sys.exit('FAIL(SIGNOFF): basis 需至少 10 字，说明看了什么、为何给此结论')

    now = datetime.now(timezone(timedelta(hours=8))).isoformat()
    entry = {
        'assertion_id': assertion_id,
        'reviewer': reviewer,
        'role': role,
        'reviewed_at': now,
        'evidence_refs': refs,
        'evidence_hash': _ev_hash(refs),
        'verdict': args.verdict,
        'basis': basis,
    }
    entry['signature'] = hashlib.sha256(_canon(entry).encode('utf-8')).hexdigest()[:16]

    store = Path(store)
    store.parent.mkdir(parents=True, exist_ok=True)
    with store.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    print(f'PASS(SIGNOFF): recorded {assertion_id} by {reviewer} '
          f'({role}) -> {store}')
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description='记录一条独立复核签署')
    ap.add_argument('--assertion-id', required=True)
    ap.add_argument('--reviewer', required=True)
    ap.add_argument('--role', required=True,
                    help='独立角色: independent-reviewer | owner | security-owner')
    ap.add_argument('--verdict', required=True,
                    help='approved | rejected | needs-work')
    ap.add_argument('--evidence', required=True, help='逗号分隔的证据路径')
    ap.add_argument('--basis', required=True, help='人类可读的复核说明（>=10 字）')
    ap.add_argument('--store', default=str(DEFAULT_STORE))
    args = ap.parse_args()
    sys.exit(record(args, Path(args.store)))


if __name__ == '__main__':
    main()
