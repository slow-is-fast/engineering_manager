#!/usr/bin/env python3
"""T-QA-02：验收测试防删除校验（控制 QA-02，规则 §8 可信质量基线与独立验收）。

统计 tests/ 下真实的验收用例数（`def test_*` 与 negative_static 的 `T_XXX_`），
与 `governance/quality_baseline.json` 里经批准的下限比对，低于即失败关闭。

为什么：PR #2「删除验收测试」演练证明了门禁当时能拦住，但演练是一次性的。
常态化之后，任何一次"顺手删掉几个用例"的提交都会被同一把尺子量到。

诚实边界：只数**数量**，不判断删掉的那条是不是恰好该删。数量下限是防退化的
粗粒度闸门，不替代对具体用例的评审——判断"该不该删"仍是人做的事。
"""
import json
import re
import sys
from pathlib import Path

BASE = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1])

bp = BASE / 'governance' / 'quality_baseline.json'
if not bp.exists():
    sys.exit('FAIL(T-QA-02): missing governance/quality_baseline.json')
baseline = json.loads(bp.read_text(encoding='utf8'))
floor = ((baseline.get('test_thresholds') or {}).get('min_test_count'))
if not isinstance(floor, int):
    sys.exit('FAIL(T-QA-02): baseline declares no integer min_test_count')

count = 0
detail = []
for f in sorted((BASE / 'tests').glob('test_*.py')):
    names = re.findall(r'^\s*def (test_[A-Za-z0-9_]+)\(',
                       f.read_text(encoding='utf8'), re.M)
    count += len(names)
    detail.append(f'{f.name}: {len(names)}')

ns = BASE / 'tests' / 'negative_static.py'
if ns.exists():
    names = re.findall(r'^def (T_[A-Za-z0-9_]+)\(',
                       ns.read_text(encoding='utf8'), re.M)
    count += len(names)
    detail.append(f'negative_static.py: {len(names)}')

if count < floor:
    sys.exit(f'FAIL(T-QA-02): acceptance test count dropped: {count} < floor {floor}\n  '
             + '\n  '.join(detail))
print(f'PASS(T-QA-02): {count} acceptance cases >= floor {floor}')
