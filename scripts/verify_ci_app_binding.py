#!/usr/bin/env python3
"""T-QA-01：CI 应用绑定校验（控制 QA-01，规则 §8 可信质量基线与独立验收）。

要求所有 GitHub Actions 的 `uses:` 引用绑定到**不可变**标识：
  - `owner/repo@<40 位十六进制 commit SHA>`        ✅
  - `owner/repo@<浮动 tag 或分支>`                  ❌
  - `docker://image@sha256:<64 位十六进制 digest>`   ✅
  - `docker://image:<浮动 tag>`                     ❌

为什么：浮动 tag 指向的内容可以被上游静默替换。今天审核过的 CI，明天可能执行
完全不同的代码——**而流水线外观毫无变化**。PR #3「篡改 CI」演练证明了门禁当时
有效；本脚本把那次演练变成常态化检查。

2026-10-30 冷读复核修正的四处漏洞（原版"看起来在检查"的部分）：
  - 只扫 `*.yml`：GitHub 同等接受 `.yaml`，改名即失明 → 现两种后缀都扫
  - 什么都没扫到也打印 PASS → 现改为失败关闭（扫到 0 条绝不是通过）
  - `docker://` 无条件豁免：它与浮动 tag 是同一类上游替换风险 → 现要求 digest pin
  - 本地 composite action（`./`）豁免且不扫定义文件 → 现 `.github/actions/**`
    一并纳入扫描，调用点也必须是可追溯的相对路径
"""
import re
import sys
from pathlib import Path

BASE = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1])

SHA_RE = re.compile(r'^[0-9a-fA-F]{40}$')          # 大小写都接受
DIGEST_RE = re.compile(r'^sha256:[0-9a-fA-F]{64}$')


def workflow_files():
    """工作流定义 + 本地 composite action 的定义文件。

    后者是原版的盲区：调用点写 `- uses: ./.github/actions/x` 被豁免，
    而真正的 upstream 调用藏在 x/action.yml 里没人扫。
    """
    files = []
    for pat in ('*.yml', '*.yaml'):
        files += sorted((BASE / '.github' / 'workflows').glob(pat))
    actions = BASE / '.github' / 'actions'
    if actions.exists():
        for pat in ('action.yml', 'action.yaml'):
            files += sorted(actions.rglob(pat))
    return files


def collect_refs():
    """返回 (refs, degraded)。

    refs 为 [(path, lineno, ref)]；优先用 PyYAML 做结构化解析（覆盖流映射、
    引号 key、锚点别名），不可用时降级为行正则——**但降级必须可见**，
    绝不能静默放宽标准。
    """
    try:
        import yaml                      # noqa: PLC0415  可选依赖
    except ImportError:
        yaml = None

    refs, degraded = [], (yaml is None)
    queue = list(workflow_files())
    seen = set()
    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        text = path.read_text(encoding='utf8', errors='replace')
        parsed = None
        if yaml is not None:
            try:
                parsed = yaml.safe_load(text)
            except Exception:            # YAML 语法坏了也是个问题，交给正则兜底并标记
                degraded = True
        cur = _refs_from_yaml(path, parsed) if parsed is not None \
            else _refs_from_text(path, text)
        refs.extend(cur)
        # 跟踪本地 composite action：定义里同样藏着 upstream 调用，且可放在
        # 仓库内任意路径，只预扫 .github/actions/ 会漏。
        for _p, _ln, ref in cur:
            clean = ref.split('#')[0].strip()
            if not clean.startswith('./'):
                continue
            target = BASE / clean
            for cand in (target / 'action.yml', target / 'action.yaml'):
                if cand.exists():
                    queue.append(cand)
    return refs, degraded


def _refs_from_yaml(path, node, out=None):
    """递归取所有 `uses` 的值（无论块式/流式/引号/锚点已解析）。"""
    if out is None:
        out = []
    if isinstance(node, dict):
        for key, val in node.items():
            if str(key).strip() == 'uses' and isinstance(val, str):
                out.append((path, 0, val.strip()))
            _refs_from_yaml(path, val, out)
    elif isinstance(node, list):
        for item in node:
            _refs_from_yaml(path, item, out)
    return out


def _refs_from_text(path, text):
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if 'uses' not in line:
            continue
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        m = re.search(r'uses\s*:\s*(.+?)(?:\s+#.*)?$', line)
        if not m:
            continue
        ref = m.group(1).strip().rstrip('}').strip().strip('\'"').strip()
        if not ref or ref[0] in '[&*|>' or ref.endswith(('|', '>')):
            continue
        out.append((path, lineno, ref))
    return out


def check_ref(ref, base):
    """返回 None 表示合规，否则返回拒绝理由。"""
    ref = ref.split('#')[0].strip()
    if not ref:
        return 'empty ref'
    if ref.startswith('./'):
        # 本地 action：路径必须在仓库内真实存在，否则是个断链（等价于放行任意内容）
        target = base / ref
        if not target.exists():
            return f'local action path does not exist: {ref}'
        return None
    if ref.startswith('docker://'):
        rest = ref[len('docker://'):]
        image, at, digest = rest.partition('@')
        if at and DIGEST_RE.match(digest):
            return None
        return f'docker image without sha256 digest pin: {ref}'
    repo, at, version = ref.partition('@')
    if not repo or not at:
        return f'no immutable pin (floating ref): {ref}'
    if not SHA_RE.match(version):
        return f'version is not a 40-char commit SHA: {ref}'
    return None


refs, degraded = collect_refs()

if not refs:
    sys.exit('FAIL(T-QA-01): scanned 0 `uses:` refs — the check saw nothing, '
             'which is never a pass. Expected refs in .github/workflows/*.y(a)ml '
             'and composite actions under .github/actions/**')

bad = []
for path, lineno, ref in refs:
    reason = check_ref(ref, BASE)
    if reason:
        loc = str(path.relative_to(BASE)) + (f':{lineno}' if lineno else '')
        bad.append(f'{loc}  {ref}  — {reason}')

if bad:
    msg = 'FAIL(T-QA-01): CI action not bound to an immutable ref:\n  ' + \
          '\n  '.join(bad)
    if degraded:
        msg += '\n  (DEGRADED regex mode — install PyYAML for full coverage)'
    sys.exit(msg)

files = len({p for p, _, _ in refs})
print(f'PASS(T-QA-01): {len(refs)} refs across {files} files all bound to '
      f'immutable refs' + (' (DEGRADED regex mode)' if degraded else ''))
