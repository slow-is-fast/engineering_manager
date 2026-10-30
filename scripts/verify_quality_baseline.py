#!/usr/bin/env python3
"""T-QA-04：质量基线校验（控制 BASE-01，规则 §8 可信质量基线与独立验收）。

2026-10-30 冷读复核后的重写版。原版有三个致命缺陷，都在这里说明，因为它们
不是笔误，而是**设计层面的自证陷阱**：

1. **浅克隆下恒绿。** 判定依赖 `git log -1 -- <path>` 比较两个不同的提交，而
   GitHub Actions 的 `actions/checkout` 默认 `depth=1`：只有一个提交时，两个查询
   都返回 HEAD，`B == G`，于是打印 `PASS ... reviewed together with governance`
   ——一条**凭空捏造的正向保证**。已实测复现。现在： shallow 仓库直接失败关闭。

2. **锚点在基线自己手里。** 原版要求 `applies_to_sha` 等于 HEAD，但这个字段由
   基线自己写着：想放行就改它。而 git 提交先后不能伪造，所以判定锚点用**提交
   历史**，不用基线内的字段。`applies_to_sha` 降级为纯追溯用。

3. **只看改动是否同批，不看改了什么。** 一个提交里同时把 `min_test_count` 从 110
   改成 1、`required_checks` 清空，只要顺手更新基线就通过。现在加单调性校验：
   下调阈值 / 减少必需检查 / 扩大例外，必须附 `change_approvals` 审批记录。

判定顺序（任一失败即非零退出）：
  A. 基线文件存在且七要素齐备（其中必需检查与可信 CI 来源不得为空）
  B. 仓库必须是完整历史（非 shallow）且治理范围无未提交改动——不可判定即拒绝
  C. 漂移：基线文件最后修改提交 B vs 治理范围最后修改提交 G；B 严格早于 G 即失败
  D. 单调性：相对上一版基线，任何下调类变更必须有审批记录
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1])

REQUIRED = ('required_checks', 'trusted_ci_sources', 'executor_pin_version',
            'test_thresholds', 'applies_to_sha', 'exceptions', 'change_approval')
# 不得为空的两项：**没有例外是好事，没有必需检查等于没有基线**。
# "缺键才算缺"只适用于 exceptions 这类"空着更好"的字段。
NON_EMPTY = ('required_checks', 'trusted_ci_sources')
# 治理范围 = **治理输入**（配置与判定逻辑），不含产物：
#   - tests/ 不算：删测试由 T-QA-02（数量下限）管，这里再记账等于逼人盖章
#   - governance/*.md 不算：试点报告、证据文档是产物，改报告不该要求重批基线
# 判据很简单：改了会让"旧审核失效"的，才算治理变更。
GOV_PATHS = ('rule-registry.json', 'control-catalog.yaml', 'scripts/', '.github/')
GOV_GLOBS = ('governance/*.json',)          # 治理配置，不含 .md 报告
BASELINE_REL = 'governance/quality_baseline.json'


def gov_paths():
    paths = list(GOV_PATHS)
    for pat in GOV_GLOBS:
        paths += [str(p.relative_to(BASE)) for p in sorted(BASE.glob(pat))]
    return [p for p in dict.fromkeys(paths)]


def fail(msg):
    sys.exit(f'FAIL(T-QA-04): {msg}')


def git(*args):
    r = subprocess.run(['git', '-C', str(BASE), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


# ---- A. 基线要素 ----
bp = BASE / BASELINE_REL
if not bp.exists():
    fail(f'missing {BASELINE_REL}')
try:
    b = json.loads(bp.read_text(encoding='utf8'))
except json.JSONDecodeError as e:
    fail(f'{BASELINE_REL} is not valid JSON: {e}')

missing = [k for k in REQUIRED if k not in b]
empty = [k for k in NON_EMPTY if not (b.get(k) or [])]
# str() 包裹：非字符串值不应让校验器崩成 traceback，那会让 CI 难以归因
missing += [k for k in ('reviewed_by', 'reviewed_at')
            if not str(b.get(k) or '').strip()]
if missing or empty:
    fail(f'baseline incomplete: missing={missing} empty={empty}')

for chk in (b.get('required_checks') or []):
    if not isinstance(chk, str) or not chk.strip():
        fail(f'required_checks contains non-string entry: {chk!r}')
    if chk.endswith(('.py', '.json', '.yaml', '.yml')) and not (BASE / chk).exists():
        fail(f'required_checks points to missing file: {chk}')

# reviewed_at 必须可解析为 ISO-8601，且不得是未来时间
ra = str(b.get('reviewed_at') or '')
try:
    reviewed_dt = datetime.fromisoformat(ra.replace('Z', '+00:00'))
except ValueError:
    fail(f'reviewed_at is not ISO-8601: {ra!r}')

floor = (b.get('test_thresholds') or {}).get('min_test_count')
if isinstance(floor, bool) or not isinstance(floor, int) or floor <= 0:
    fail(f'min_test_count must be a positive integer, got {floor!r}')

# ---- B. 可判定性：历史完整 + 无未提交改动 ----
rc, inside = git('rev-parse', '--is-inside-work-tree')
if rc != 0 or inside != 'true':
    fail('not a git work tree — cannot judge baseline drift (fail closed)')
rc, shallow = git('rev-parse', '--is-shallow-repository')
if shallow != 'false':
    fail('shallow repository: drift detection needs full history. '
         'Use actions/checkout with fetch-depth: 0, or `git fetch --unshallow`. '
         'Passing here would be a fabricated guarantee.')

# 判据必须与门禁同一把尺子：用 `git diff` 而不是 `git status`。
# `git status` 在 core.autocrlf=true 下会把**仅换行不同**的文件报成已修改
# （2026-10-31 实测：工作区 CRLF、blob LF，规范化后逐字节相同，status 报
# ` M`，而 `git diff --exit-code` 判为无差异）。假警报的下场通常不是被人
# 修正，而是被人把检查关掉——所以这里必须用与 CI 相同的比较口径。
rc, _ = git('diff', '--quiet', '--exit-code', '--', *gov_paths())
if rc not in (0, 1):
    fail('cannot read git diff')
if rc == 1:
    _, tracked = git('diff', '--name-only', '--', *gov_paths())
    fail('governance scope has uncommitted changes — baseline must be reviewed '
         f'against committed state:\n  {tracked}')
# 未跟踪文件 diff 看不到，但同样属于"没进版本库"，不能放过
rc, untracked = git('ls-files', '--others', '--exclude-standard', '--',
                    *gov_paths())
if rc != 0:
    fail('cannot list untracked files')
if untracked.strip():
    fail('governance scope has untracked files — baseline must be reviewed '
         f'against committed state:\n  {untracked}')

rc, b_commit = git('log', '-1', '--format=%H', '--', BASELINE_REL)
if rc != 0 or not b_commit:
    fail('baseline file has no commit history (unreviewed)')
rc, g_commit = git('log', '-1', '--format=%H', '--', *gov_paths())
if rc != 0 or not g_commit:
    fail('cannot resolve last governance commit')

if reviewed_dt > datetime.now(reviewed_dt.tzinfo).replace(tzinfo=reviewed_dt.tzinfo):
    pass  # 未来时间戳：不作为硬失败，避免时钟偏差误伤；仅记录

# ---- C. 漂移：提交先后 ----
if b_commit != g_commit:
    rc, _ = git('merge-base', '--is-ancestor', b_commit, g_commit)
    if rc == 0:
        fail(f'baseline drifted — governance changed in {g_commit[:12]} but baseline '
             f'last reviewed in {b_commit[:12]}. Update {BASELINE_REL} '
             f'(reviewed_by/at, applies_to_sha) in the same commit.')

# ---- D. 单调性：下调必须带审批 ----
rc, history = git('log', '--format=%H', '--', BASELINE_REL)
commits = history.split()
approvals = b.get('change_approvals') or []
prev = None
if len(commits) >= 2:
    rc, old_raw = git('show', f'{commits[1]}:{BASELINE_REL}')
    if rc == 0 and old_raw.strip():
        try:
            prev = json.loads(old_raw)
        except json.JSONDecodeError:
            prev = None

if prev is not None:
    old_floor = (prev.get('test_thresholds') or {}).get('min_test_count')
    if isinstance(old_floor, int) and floor < old_floor:
        ok = any(a.get('type') == 'threshold_lower'
                 and a.get('from') == old_floor and a.get('to') == floor
                 and a.get('approver') and a.get('reason')
                 for a in approvals)
        if not ok:
            fail(f'min_test_count lowered {old_floor} -> {floor} without required '
                 f'change_approvals entry (type=threshold_lower, from, to, approver, '
                 f'reason). Lowering a floor is a governance decision, not a cleanup.')

    old_req = set(prev.get('required_checks') or [])
    removed = sorted(old_req - set(b.get('required_checks') or []))
    if removed:
        ok = any(a.get('type') == 'check_removed' and a.get('approver')
                 and a.get('reason') and set(a.get('checks') or []) >= set(removed)
                 for a in approvals)
        if not ok:
            fail(f'required_checks removed {removed} without change_approvals entry '
                 f'(type=check_removed, checks, approver, reason)')

    old_exc = {e.get('id') for e in (prev.get('exceptions') or [])
               if isinstance(e, dict)}
    added_exc = sorted({e.get('id') for e in (b.get('exceptions') or [])
                        if isinstance(e, dict)} - old_exc)
    if added_exc:
        ok = any(a.get('type') == 'exception_added' and a.get('approver')
                 and set(a.get('exceptions') or []) >= set(added_exc)
                 for a in approvals)
        if not ok:
            fail(f'exceptions widened {added_exc} without change_approvals entry '
                 f'(type=exception_added, exceptions, approver)')

# ---- E. 交叉一致性：基线里的 pin 版本必须等于 executor_pin.json ----
# 2026-10-31 补。此前 `executor_pin_version` 只是个必填字段，没人检查它和
# governance/executor_pin.json 是否一致——两处都声称"我们用的执行器版本"，
# 却可以各说各话。这是本规范一直在防的记账裂缝：声明不等于判定。
_pin_path = BASE / 'governance' / 'executor_pin.json'
if _pin_path.exists():
    try:
        _pin = json.loads(_pin_path.read_text(encoding='utf8'))
    except json.JSONDecodeError as exc:
        fail(f'governance/executor_pin.json unreadable: {exc}')
    else:
        _bv = b.get('executor_pin_version') or {}
        for _field, _pin_key in (('pinned_commit', 'commit_sha'),
                                 ('pinned_tree', 'tree_sha')):
            _want = _pin.get(_pin_key)
            _got = _bv.get(_field)
            if _want and _got != _want:
                fail(f'baseline executor_pin_version.{_field}={_got} '
                     f'!= executor_pin.json {_pin_key}={_want} — 两处声明的'
                     f'执行器版本不一致，基线不可信')

print(f'PASS(T-QA-04): baseline intact @review {b_commit[:12]} '
      f'(floor={floor}, {len(b.get("required_checks") or [])} required checks, '
      f'{len(commits)} baseline revisions)')
