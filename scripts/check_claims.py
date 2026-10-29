#!/usr/bin/env python3
"""CLM-01：声明诚实性 lint（规则 AASEGS-AGT-005「不得声称完美即时撤销」）。

扫描规范文档与证据文件，检出**无证据支撑的绝对化能力声明**：
  即时撤销 / 立即失效 / 完美撤销 / 完全撤销 / 零延迟 / 永不失效 /
  绝对可靠 / 万无一失，以及在撤销语境下的 `100%`。

判定规则（避免误报）：
- `100%` 只在**撤销/失效语境**（撤销|失效|revoke|revocation）下才纳入检查；
  覆盖率目标一类表述（"追踪覆盖率 100%"）不属于能力声明，不判违规。
- 跳过存档类文档（`*ChatGPT会话存档*`）——它是原始会话转录，不是规范性文本。
- 跳过 HTML/JSX 片段行（含 `<box` / `height=` / `width=`），避免把排版代码当声明。
- 同一行或紧邻行出现证据标记（`evidence:`、`实测`、`latency=`、`P95`、URL、
  `run `、`commit ` 等）视为有依据，放行。

失败关闭：检出违规即非零退出。用法：
  python scripts/check_claims.py [目录]     # 默认仓库根目录
"""
import re
import sys
from pathlib import Path

BASE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]

ABSOLUTE_CLAIMS = (
    r'即时撤销', r'立即失效', r'完美撤销', r'完全撤销', r'零延迟',
    r'永不失效', r'绝对可靠', r'万无一失',
)
REVOCATION_CTX = re.compile(r'撤销|失效|revoke|revocation', re.I)
ABSOLUTE_RE = re.compile('|'.join(ABSOLUTE_CLAIMS))
PCT_RE = re.compile(r'100\s*%')
CODE_LINE = re.compile(r'<box|height=|width=|`\$\{')
ARCHIVE = '会话存档'

EVIDENCE_MARKERS = (
    'evidence:', 'evidence_ref', '实测', 'latency=', 'P95', 'p95',
    'http://', 'https://', 'run ', 'commit ', 'SHA', '有传播延迟',
)
# 明确否定/免责的表述不是"宣扬完美"，正相反——AGT-005 管的是吹嘘，不是提醒
NEGATION_MARKERS = ('不代表', '不等于', '并非', '不能证明', '不构成', '不可假定',
                    '不宣称', '不做绝对')


def hits(line: str) -> bool:
    # 免责/否定句（"这不代表控制有效率为 100%"）不判违规：
    # AGT-005 管的是吹嘘完美，不是提醒别人别当真
    if any(n in line for n in NEGATION_MARKERS):
        return False
    if ABSOLUTE_RE.search(line):
        return True
    # 100% 仅在撤销语境下计入
    return bool(PCT_RE.search(line) and REVOCATION_CTX.search(line))


def backed_by_evidence(line: str, neighbor: str) -> bool:
    blob = (line + ' ' + neighbor).lower()
    return any(m.lower() in blob for m in EVIDENCE_MARKERS)


def main() -> None:
    targets = ([f for f in sorted(BASE.glob('*.md')) if ARCHIVE not in f.name]
               + sorted((BASE / 'evidence').glob('*.md')))
    violations = []
    for f in targets:
        lines = f.read_text(encoding='utf8').splitlines()
        for i, line in enumerate(lines):
            if CODE_LINE.search(line) or not hits(line):
                continue
            neighbor = (lines[i - 1] if i > 0 else '') + ' ' + \
                       (lines[i + 1] if i + 1 < len(lines) else '')
            if backed_by_evidence(line, neighbor):
                continue
            violations.append((f.relative_to(BASE), i + 1, line.strip()[:80]))

    if violations:
        print('FAIL(CLM-01): 无证据支撑的绝对化声明（AGT-005）：')
        for path, ln, text in violations:
            print(f'  {path}:{ln}: {text}')
        sys.exit(1)

    print(f'PASS(CLM-01): no unbacked absolute claims in {len(targets)} docs '
          f'(archive skipped)')


if __name__ == '__main__':
    main()
