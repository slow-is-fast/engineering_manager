#!/usr/bin/env python3
"""导出 Owner 签署工作清单（governance/owner_worklist.md）。

## 为什么要"生成"而不是"手写"

22 条 manual/excepted 断言散在 `acceptance_matrix.json` 里，每条都有
`human_gate`（人工闸类型）与 `text`（要求）。手写一份清单必然与矩阵漂移——
而这份清单的全部价值就在于"Owner 照着做能闭合"，一旦某条已经签过、清单
还显示未签，它就从工具变成了陷阱。

所以：**从矩阵生成，带数据指纹，支持 `--check` 比对**。矩阵变了清单没重生成
→ 红。这跟 T-QA-04b 是同一个思路：让"文档声称"与"机器事实"不能各说各话。

## 分类是人工判断的固化，不是自动推导

`NEEDS_ENV` 是一张写死的表：这些 human_gate 需要真实环境/真实系统才能做，
其余只需文档、审阅与 Owner 判断。把它写成显式映射而不是关键词猜测，是为了
让"为什么这条排在这一类"可被审阅——猜出来的分类不可审计。

## 用法
  python scripts/export_owner_worklist.py            # 生成/覆盖 owner_worklist.md
  python scripts/export_owner_worklist.py --check    # 比对，不一致则非零退出
  python scripts/export_owner_worklist.py --out PATH # 输出到别处（调试用）
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 需要真实环境/真实系统/真机配置的 human_gate（其余 manual 只凭文档与判断即可）。
# 分类取**保守**：看起来"也许能做"但实际要外部资源的，一律归到需资源那侧——
# 乐观分类会让人做到一半卡住，比根本不开始更伤人。
NEEDS_ENV = {
    'isolated_env_integration_test',
    'memory_integration_test',
    'real_side_effect_e2e',
    'recovery_drill',
    'breaker_drill',
    'repo_gate_integration',
    'pilot_repo_inspection',      # 需要真实试点仓库（分支保护 + SHA 绑定）
    'signed_evidence_package',    # 需要受控真实仓库 + 独立 Reviewer
    'tool_config_verification',   # 需要 Claude Code / Codex 真机配置
}

# 每条"需资源"条目到底缺什么——照这个去准备，不用回来问
RESOURCE_HINT = {
    'isolated_env_integration_test': '隔离环境（容器/VM）',
    'memory_integration_test': '记忆后端（检索/缓存）',
    'real_side_effect_e2e': '真实副作用系统 + 远端结果证据',
    'recovery_drill': '可制造故障并恢复的环境',
    'breaker_drill': '隔离环境',
    'repo_gate_integration': '真实仓库（分支保护 + 审批门禁）',
    'pilot_repo_inspection': '真实试点仓库（分支保护 + SHA 绑定）',
    'signed_evidence_package': '受控真实仓库 + 独立 Reviewer/Owner',
    'tool_config_verification': 'Claude Code / Codex 真机配置',
}


def _load(path):
    if not path.is_file():
        sys.exit(f'FAIL(worklist): 缺少输入 {path}')
    raw = path.read_bytes()
    return json.loads(raw.decode('utf-8')), hashlib.sha256(raw).hexdigest()[:12]


def _clip(s, n):
    s = str(s or '').replace('|', '\\|').replace('\n', ' ').strip()
    return s if len(s) <= n else s[:n - 1] + '…'


def collect(matrix, baseline):
    rows = []
    for iid, rec in sorted((matrix.get('issues') or {}).items()):
        for a in rec.get('assertions') or []:
            kind = a.get('kind')
            if kind not in ('manual', 'excepted'):
                continue
            gate = a.get('human_gate') or a.get('exception_ref') or '(none)'
            if kind == 'excepted':
                bucket = 'excepted'
            elif gate in NEEDS_ENV:
                bucket = 'needs_env'
            else:
                bucket = 'evidence_only'
            rows.append({
                'issue': iid,
                'id': a.get('id'),
                'kind': kind,
                'gate': gate,
                'bucket': bucket,
                'text': a.get('text') or '',
                'close': rec.get('close_condition') or '',
                'severity': rec.get('severity') or '',
                'exception_ref': a.get('exception_ref') or '',
                'signed': bool(a.get('signoff')),
                'signoff': a.get('signoff') or None,
            })
    exps = {e.get('id'): e.get('expires')
            for e in (baseline.get('exceptions') or []) if isinstance(e, dict)}
    return rows, exps


def _table(rows, with_gate=True, with_resource=False):
    head = '| # | 断言 | 所属 Issue | 严重度 | 人工闸 | 要求（矩阵原文） | Issue 闭合条件 |'
    sep = '|---|---|---|---|---|---|---|'
    if with_resource:
        head += ' 所需资源 |'
        sep += '---|'
    out = [head, sep]
    for i, r in enumerate(rows, 1):
        line = (f"| {i} | `{r['id']}` | {r['issue']} | {r['severity']} | "
                f"{'`' + r['gate'] + '`' if with_gate else '—'} | "
                f"{_clip(r['text'], 70)} | {_clip(r['close'], 60)} |")
        if with_resource:
            line += f" {RESOURCE_HINT.get(r['gate'], '（未登记，见矩阵原文）')} |"
        out.append(line)
    return out


def render(rows, exps, fp_matrix, fp_exceptions):
    signed = [r for r in rows if r['signed']]
    unsigned = [r for r in rows if not r['signed']]
    by = {k: [r for r in unsigned if r['bucket'] == k]
          for k in ('evidence_only', 'needs_env', 'excepted')}

    L = []
    A = L.append
    A('# Owner 签署工作清单')
    A('')
    A('> **自动生成，勿手改。** 重新生成：`python scripts/export_owner_worklist.py`')
    A(f'> 数据指纹：`acceptance_matrix.json` = `{fp_matrix}` ／ '
      f'`exceptions`（id+expires）= `{fp_exceptions}`')
    A('> 矩阵变动后本文件必须重新生成；`--check` 会比对指纹并红。')
    A('>')
    A('> **铁律**：Agent 不得代签。每条签署须由独立主体执行（reviewer ≠ 执行者），')
    A('> `verdict=approved`、`--basis` ≥10 字、证据在 `evidence/` 且已登记（`gov_run --accept-evidence`）。')
    A('')
    A('## 概览')
    A('')
    A('| 分类 | 条数 | 说明 |')
    A('|---|---|---|')
    A(f'| 总计（manual + excepted） | {len(rows)} | 已签 {len(signed)} ／ 未签 {len(unsigned)} |')
    A(f'| 一、仅需文档与判断 | {len(by["evidence_only"])} | 不需要真实环境资源，可立即推进 |')
    A(f'| 二、需要真实环境/系统 | {len(by["needs_env"])} | 受 EXC-02 现实约束（Owner 已确认不提供真环境） |')
    A(f'| 三、例外内（excepted） | {len(by["excepted"])} | 属于已知做不到，**仍计入未满足** |')
    A('')
    if signed:
        A('### 已签署')
        A('')
        A('（字段来自 `apply_signoffs.build_signoff_field`：`by` 是复核者，`applied_by` 是执行翻转的人。）')
        A('')
        for r in signed:
            s = r['signoff'] or {}
            # 真实字段名是 `by`（apply_signoffs 的历史命名），不是 reviewer；
            # 兼容 reviewer 只是为了让旧数据/手工构造的记录也能显示。
            who = s.get('by') or s.get('reviewer') or '?'
            A(f"- `{r['id']}` · {who}（{s.get('role') or '?'}）· "
              f"{s.get('date') or '?'} · applied_by={s.get('applied_by') or '?'} · "
              f"sig={_clip(s.get('signature') or '', 12)}")
        A('')

    A('## 一、可先做：仅需文档/审阅与 Owner 判断')
    A('')
    A('这些条目不需要真环境，是当前**唯一能真正推进闭环**的部分。建议按 Issue 编号顺序做：')
    A('每完成一条就签一条，签完整批由人审后 commit。')
    A('')
    L += _table(by['evidence_only'])
    A('')

    A('## 二、需要真实环境/真实系统（受 EXC-02 约束）')
    A('')
    A('Owner 已明确不提供真环境（`owner_designations.md` #4 续二）。这些条目在')
    A(f'`{exps.get("EXC-02", "2027-04-30")}` 到期前必须三选一：延期 / 补环境验证 / 永久 excepted。')
    A('**在此之前不得签 approved**——签了就是伪造验证。')
    A('')
    L += _table(by['needs_env'], with_resource=True)
    A('')

    A('## 三、例外内（excepted）')
    A('')
    A('已知做不到且已登记风险，不等于已完成：**仍计入未满足**，相关 Issue 不得 `machine_complete`。')
    A('')
    L += _table(by['excepted'])
    A('')

    A('## 签署命令模板')
    A('')
    A('```bash')
    A('# 0) 证据先落盘并登记（hash 当场存证）')
    A('python scripts/gov_run.py --accept-evidence --by <执行者> --reason "<为什么>"')
    A('')
    A('# 1) 记录独立复核签署（reviewer 必须是独立主体，Agent 不得代签）')
    A('python scripts/record_signoff.py \\')
    A('  --assertion-id <断言 id，如 AUD-001-03> \\')
    A('  --reviewer <独立主体> \\')
    A('  --role independent-reviewer \\')
    A('  --verdict approved \\')
    A('  --evidence evidence/<证据文件> \\')
    A('  --basis "<≥10 字的复核说明>"')
    A('')
    A('# 2) 投影 diff 给 Owner 确认，再落盘')
    A('python scripts/apply_signoffs.py --dry-run')
    A('python scripts/apply_signoffs.py --apply --by <执行者>')
    A('')
    A('# 3) 重生成本清单（矩阵已变），然后由人审并 commit')
    A('python scripts/export_owner_worklist.py')
    A('```')
    A('')
    A('## 例外到期')
    A('')
    A('| 例外 | 到期 | 当前状态 |')
    A('|---|---|---|')
    for eid, exp in sorted(exps.items()):
        A(f'| {eid} | {exp} | 有效（`T-EXP-01` 到期即红，不可默认沿用） |')
    A('')
    A('---')
    A('')
    A('> 本清单只做**投影**：不关闭任何断言、不产生任何签署、不改动矩阵。')
    A('> 所有状态以 `acceptance_matrix.json` 为准；清单与矩阵不一致时，以矩阵为准。')
    return '\n'.join(L) + '\n'


def main():
    ap = argparse.ArgumentParser(description='导出 Owner 签署工作清单')
    ap.add_argument('--check', action='store_true', help='比对现有文件，不一致则非零退出')
    ap.add_argument('--out', default=None)
    ap.add_argument('--root', default=str(ROOT), help='仓库根（默认本脚本上级；测试用）')
    args = ap.parse_args()

    root = Path(args.root).resolve()
    matrix, fp_m = _load(root / 'governance' / 'acceptance_matrix.json')
    baseline, _ = _load(root / 'governance' / 'quality_baseline.json')
    rows, exps = collect(matrix, baseline)
    # 只对"清单真正展示的内容"取指纹：矩阵全文 + 例外的 id/expires。
    # 不用整个 baseline 文件指纹——reviewed_at / min_test_count 每轮都变，
    # 会把"基线例行刷新"变成"清单无谓重生成"，那是噪音不是保护。
    exc_raw = json.dumps(sorted(exps.items()), ensure_ascii=False)
    fp_e = hashlib.sha256(exc_raw.encode('utf-8')).hexdigest()[:12]
    text = render(rows, exps, fp_m, fp_e)

    out = Path(args.out) if args.out else root / 'governance' / 'owner_worklist.md'
    if args.check:
        if not out.is_file():
            print(f'FAIL(worklist): {out} 不存在——请运行 python scripts/export_owner_worklist.py')
            sys.exit(1)
        current = out.read_text(encoding='utf-8')
        if current != text:
            print('FAIL(worklist): 清单与矩阵不一致（矩阵已变或文件被手改）——'
                  '请重新生成 python scripts/export_owner_worklist.py')
            sys.exit(1)
        print(f'PASS(worklist): 清单与矩阵一致（matrix={fp_m}, exceptions={fp_e}, '
              f'{len(rows)} 条）')
        return

    out.write_text(text, encoding='utf-8')
    unsigned = sum(1 for r in rows if not r['signed'])
    print(f'WROTE(worklist): {out} — {len(rows)} 条（未签 {unsigned}），'
          f'matrix={fp_m}, exceptions={fp_e}')


if __name__ == '__main__':
    main()
