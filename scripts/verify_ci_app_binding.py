#!/usr/bin/env python3
"""T-QA-01：CI 应用绑定校验（控制 QA-01，规则 §8 可信质量基线与独立验收）。

要求 .github/workflows/*.yml 中的每个 `uses:` 都 pin 到 40 位 commit SHA。

为什么：浮动 tag（`@v4`、`@main`）指向的内容可以被上游静默替换。今天审核过的
CI，明天可能执行完全不同的代码——**旧审核随之失效**，而流水线外观毫无变化。
PR #3「篡改 CI」演练防的就是这个，但演练只证明了当时的门禁有效，不能证明
每一次改动都被检查过；本脚本把那次演练变成常态化检查。

失败关闭：发现任何未 pin 的引用即非零退出。允许例外：
  - 本地 action（`./` 开头），它跟代码一起受版本控制，无上游替换风险。
"""
import re
import sys
from pathlib import Path

BASE = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1])
SHA_RE = re.compile(r'^[0-9a-f]{40}$')
USES_RE = re.compile(r'^\s*-?\s*uses:\s*(\S+)')

wf_dir = BASE / '.github' / 'workflows'
if not wf_dir.exists():
    sys.exit(f'FAIL(T-QA-01): no workflow directory under {BASE}')

bad, checked = [], 0
for wf in sorted(wf_dir.glob('*.yml')):
    for lineno, line in enumerate(wf.read_text(encoding='utf8').splitlines(), 1):
        m = USES_RE.match(line)
        if not m:
            continue
        ref = m.group(1).split('#')[0].strip()      # 去掉行尾 "  # v4" 注释
        if ref.startswith(('./', 'docker://')):
            continue
        checked += 1
        _name, _sep, version = ref.partition('@')
        if not version or not SHA_RE.match(version):
            bad.append(f'{wf.name}:{lineno}  {ref}')

if bad:
    sys.exit('FAIL(T-QA-01): CI action not pinned to immutable commit SHA:\n  '
             + '\n  '.join(bad))
print(f'PASS(T-QA-01): {checked} CI action refs all pinned to commit SHA')
