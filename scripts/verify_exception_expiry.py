#!/usr/bin/env python3
"""T-EXP-01：例外到期检查（控制 BASE-01 / 规则 §8 可信质量基线）。

## 为什么需要这条

`quality_baseline.json` 的 `exceptions` 是「暂时做不到，所以先记下来」的
诚实登记——EXC-01（第二人类主体不可达）与 EXC-02（独立账号/主机不可达）。
它们都带 `expires`，语义是「到这天必须有结论」。

但在此之前**没有任何机器盯着这个日期**。到期之后会发生什么？什么都不会：
基线照样绿、CI 照样过、`excepted` 断言照样躺在矩阵里。也就是说，一个带
到期日的例外，实际上等价于**永久例外**——只是它自己不知道。

这正是本规范一直防的那类东西：字段存在、语义清楚、无人执行。同一个
`expires` 字段，`verify_quality_baseline` 只要求它是合法日期，从不比较今天。

## 判定

  - `expires` 缺失 / 不可解析 / 早于登记日            -> 失败关闭（红）
  - 已过期（today > expires）                          -> 红（例外效力已尽，
    必须由 Owner 三选一：延期例外 / 补齐能力 / 永久 excepted，并留下审批记录）
  - 剩余 <= --warn-days（默认 90 天）                   -> 告警，**不阻断**
    （提前量是提醒，不是事实判定；把提醒做成红会让"到期前三个月全部开发停摆"）
  - 剩余 >  90 天                                       -> 绿

`exceptions` 为空或缺失 -> 绿并明确打印「无例外」：没有例外是好事，不是缺配置。

用法：python scripts/verify_exception_expiry.py [--warn-days N] [repo_root]
退出码：0 通过（含仅告警）；2 失败关闭。
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

DEFAULT_WARN_DAYS = 90


def _args(argv):
    warn_days, root = DEFAULT_WARN_DAYS, None
    it = iter(argv)
    for a in it:
        if a == '--warn-days':
            warn_days = int(next(it))
        elif a.startswith('--warn-days='):
            warn_days = int(a.split('=', 1)[1])
        else:
            root = a
    return warn_days, (Path(root).resolve() if root
                       else Path(__file__).resolve().parents[1])


def fail(msg):
    print(f'FAIL(T-EXP-01): {msg}')
    sys.exit(2)


def main():
    warn_days, base = _args(sys.argv[1:])
    bp = base / 'governance' / 'quality_baseline.json'
    if not bp.is_file():
        fail(f'missing {bp}')
    try:
        baseline = json.loads(bp.read_text(encoding='utf8'))
    except json.JSONDecodeError as exc:
        fail(f'quality_baseline.json is not valid JSON: {exc}')

    exceptions = baseline.get('exceptions') or []
    if not exceptions:
        print('PASS(T-EXP-01): 基线未登记任何例外（无到期风险）')
        return
    if not isinstance(exceptions, list):
        fail('exceptions 必须是数组')

    today = date.today()
    expired, soon, seen = [], [], set()
    for e in exceptions:
        if not isinstance(e, dict):
            fail(f'exceptions 含非对象条目: {e!r}')
        eid = e.get('id')
        if not eid:
            fail('exceptions 含无 id 条目')
        if eid in seen:
            fail(f'例外 id 重复: {eid}')
        seen.add(eid)

        raw = str(e.get('expires') or '').strip()
        if not raw:
            fail(f'{eid} 缺 expires —— 例外必须有终点')
        try:
            exp = datetime.strptime(raw, '%Y-%m-%d').date()
        except ValueError:
            fail(f'{eid}.expires 不是 YYYY-MM-DD: {raw!r}')

        days_left = (exp - today).days
        if days_left < 0:
            expired.append((eid, raw, -days_left))
        elif days_left <= warn_days:
            soon.append((eid, raw, days_left))

    for eid, raw, over in expired:
        print(f'  - {eid} 已于 {raw} 过期（超期 {over} 天）')
    if expired:
        fail(f'{len(expired)} 个例外已过期。过期例外的效力已经用尽——必须由 Owner '
             f'三选一并留痕：延期（追加 change_approvals）/ 补齐缺失能力 / 永久 '
             f'转 excepted。不可默认沿用。')

    for eid, raw, left in soon:
        print(f'WARN(T-EXP-01): {eid} 将于 {raw} 到期（剩余 {left} 天）——'
              f'提前量提醒，不阻断；请在到期前给出结论')
    n = len(exceptions)
    tail = '' if not soon else f'，其中 {len(soon)} 个进入 {warn_days} 天告警窗'
    print(f'PASS(T-EXP-01): {n} 个例外全部未过期{tail}（今天 {today.isoformat()}）')


if __name__ == '__main__':
    main()
