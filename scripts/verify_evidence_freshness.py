#!/usr/bin/env python3
"""RVF-01 / T-RVF-01：证据新鲜度与持续复验。

治理证据会过期：分支保护可能被回退、CI 可能被改、pin 可能被换、控制可能退化。
因此每条 `tested`/`enforced` 控制都必须带 `evidence_at`（验证发生日），
并按风险等级设定有效期（TTL）：

  P0 → 30 天   P1 → 90 天   P2 → 180 天   未标风险 → 90 天

模式：
  默认          仅报告（列出临近过期/已过期/无时间戳）
  --enforce     存在"已过期"或"无时间戳"即非零退出（失败关闭）
  --degrade     把过期控制的 `state.degraded` 置 true 并写回目录
                （AUD-022 要求的"证据过期会降级"；维护动作，非 CI 步骤）

用法：
  python scripts/verify_evidence_freshness.py [目录] [--enforce|--degrade]
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

TTL_DAYS = {'P0': 30, 'P1': 90, 'P2': 180}
DEFAULT_TTL = 90
WARN_RATIO = 0.8  # 超过 TTL 的 80% 即提示临近过期


def load(path: Path):
    return json.loads((path / 'control-catalog.yaml').read_text(encoding='utf8'))


def parse(d: str):
    return date.fromisoformat(d)


def evaluate(catalog, today=None):
    today = today or date.today()
    stale, due, unknown, fresh = [], [], [], []
    for c in catalog['controls']:
        if c['status'] not in ('tested', 'enforced'):
            continue
        stamp = c.get('evidence_at')
        if not stamp:
            unknown.append((c['id'], 'no evidence_at'))
            continue
        ttl = TTL_DAYS.get(c.get('risk_level'), DEFAULT_TTL)
        age = (today - parse(stamp)).days
        if age > ttl:
            stale.append((c['id'], c.get('risk_level'), c.get('evidence_at'), age, ttl))
        elif age >= ttl * WARN_RATIO:
            due.append((c['id'], c.get('risk_level'), age, ttl))
        else:
            fresh.append((c['id'], age, ttl))
    return stale, due, unknown, fresh


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    base = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[1]
    catalog = load(base)
    today = date.today()
    stale, due, unknown, fresh = evaluate(catalog, today)

    print(f'RVF-01 证据新鲜度（{today.isoformat()}）：'
          f'fresh {len(fresh)} / due {len(due)} / stale {len(stale)} / unknown {len(unknown)}')
    for cid, risk, stamp, age, ttl in stale:
        print(f'  STALE   {cid} ({risk}) evidence_at={stamp} age={age}d > ttl={ttl}d')
    for cid, risk, age, ttl in due:
        print(f'  DUE     {cid} ({risk}) age={age}d / ttl={ttl}d')
    for cid, why in unknown:
        print(f'  UNKNOWN {cid}: {why}')

    if '--degrade' in sys.argv:
        for c in catalog['controls']:
            if c['id'] in {s[0] for s in stale} | {u[0] for u in unknown}:
                c['state']['degraded'] = True
                c['state']['tested'] = False
        (base / 'control-catalog.yaml').write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf8')
        print('DEGRADED: 过期/无时间戳的控制已置 state.degraded=true, tested=false')

    if '--enforce' in sys.argv and (stale or unknown):
        sys.exit(f'FAIL(RVF-01): {len(stale)} stale + {len(unknown)} unknown evidence; '
                 '证据已过期，须重新验证并更新 evidence_at')
    if '--enforce' not in sys.argv and stale:
        print('NOTE: 存在过期证据（非 enforce 模式，仅报告）')


if __name__ == '__main__':
    main()
