#!/usr/bin/env python3
"""T-QA-02：验收测试防删除校验（控制 QA-02，规则 §8 可信质量基线与独立验收）。

统计 tests/ 下真实的验收用例数，与 governance/quality_baseline.json 里经批准的
下限比对，低于即失败关闭。

为什么：PR #2「删除验收测试」演练证明了门禁当时能拦住，但演练是一次性的。
常态化之后，任何一次"顺手删掉几个用例"的提交都会被同一把尺子量到。

2026-10-30 冷读复核后改用 ast 解析计数。原版用正则有四个问题：
  - `async def test_x(` 不计（漏数，方向是放过）
  - 三引号字符串里写满 `def test_pad():` 可以刷数（注水，让下限形同虚设）
  - `def test_helper_data()` 这类辅助函数被当用例（虚高）
  - `tests/sub/**` 子目录不计（漏数）
现在按语法树统计模块级与类内的 FunctionDef/AsyncFunctionDef。

诚实边界：只数**数量**，不判断删掉的那条是不是恰好该删。数量下限是防退化的
粗粒度闸门，不替代对具体用例的评审——判断"该不该删"仍是人做的事。
"""
import ast
import json
import sys
from pathlib import Path

BASE = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1])


def count_cases(source):
    """模块级 + 类内的 def test_* / def T_*_，含 async def。"""
    n = 0
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return n                      # 语法坏了会被 unittest 自身报红，这里不计
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if name.startswith('test_') or name.startswith('T_'):
                n += 1
    return n


bp = BASE / 'governance' / 'quality_baseline.json'
if not bp.exists():
    sys.exit('FAIL(T-QA-02): missing governance/quality_baseline.json')
baseline = json.loads(bp.read_text(encoding='utf8'))

floor = (baseline.get('test_thresholds') or {}).get('min_test_count')
# bool 是 int 的子类：isinstance(True, int) 为真，会把 True 当成下限 1 放行。
# 0 / 负数 / 非整数同样必须先挡掉，否则"下限"根本不是下限。
if isinstance(floor, bool) or not isinstance(floor, int) or floor <= 0:
    sys.exit(f'FAIL(T-QA-02): min_test_count must be a positive integer, '
             f'got {floor!r}')

tests_dir = BASE / 'tests'
if not tests_dir.exists():
    sys.exit('FAIL(T-QA-02): no tests/ directory — nothing to count, which is '
             'never a pass')

count, detail = 0, []
for f in sorted(tests_dir.rglob('*.py')):
    if '__pycache__' in f.parts:
        continue
    n = count_cases(f.read_text(encoding='utf8', errors='replace'))
    if n:
        count += n
        detail.append(f'{f.relative_to(BASE)}: {n}')

if count < floor:
    sys.exit(f'FAIL(T-QA-02): acceptance test count dropped: {count} < floor '
             f'{floor}\n  ' + '\n  '.join(detail))
print(f'PASS(T-QA-02): {count} acceptance cases >= floor {floor}')
