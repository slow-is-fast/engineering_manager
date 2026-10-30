#!/usr/bin/env python3
"""T-QA-04：质量基线与漂移校验（控制 BASE-01，规则 §8 可信质量基线与独立验收）。

两件事：

1. **要素齐备**：`governance/quality_baseline.json` 必须声明七项——必需检查、
   可信 CI 来源、执行器/配置版本、测试阈值、适用 SHA、例外、变更审批规则，
   外加审查人与审查时间。缺一项就不是受保护基线，只是个配置文件。

2. **漂移检测**：基线必须与被保护对象**同批审查**。判定方式：
   - 取基线文件最后一次被修改的提交 B；
   - 取治理范围（governance/ rule-registry.json control-catalog.yaml scripts/
     tests/ .github/）最后一次被修改的提交 G；
   - 若 B 严格早于 G，说明治理已经变了、基线却没跟着重审 → 失败。

为什么用提交先后而不是比对 SHA 内容：要求基线记录当前 HEAD 会导致"每改一行
代码都要重批基线"这种无法执行的规则，进而被人绕过。改成"治理变了基线必须一起
动"，既保留了"旧审核不得复用"的语义，又只在该审的时候审。

诚实边界：只检查基线与治理文件的提交先后，**不审查变更内容是否合理**——
"这次下调阈值有没有正当理由"仍需要人读 change_approval 里的记录来判断。
"""
import json
import subprocess
import sys
from pathlib import Path

BASE = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1])

REQUIRED = ('required_checks', 'trusted_ci_sources', 'executor_pin_version',
            'test_thresholds', 'applies_to_sha', 'exceptions', 'change_approval')
GOV_PATHS = ('governance/', 'rule-registry.json', 'control-catalog.yaml',
             'scripts/', 'tests/', '.github/')

bp = BASE / 'governance' / 'quality_baseline.json'
if not bp.exists():
    sys.exit('FAIL(T-QA-04): missing governance/quality_baseline.json')
b = json.loads(bp.read_text(encoding='utf8'))

# **缺键才算缺**：空列表/空对象是合法声明（"没有例外"是好事，不是没写）。
# 用 falsy 判断会把"声明为空"误判成"未声明"，逼人往基线里塞占位内容。
missing = [k for k in REQUIRED if k not in b]
missing += [k for k in ('reviewed_by', 'reviewed_at') if not (b.get(k) or '').strip()]
if missing:
    sys.exit(f'FAIL(T-QA-04): baseline incomplete: missing={missing}')


def git(*args):
    r = subprocess.run(['git', '-C', str(BASE), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


rc, inside = git('rev-parse', '--is-inside-work-tree')
if rc != 0 or inside != 'true':
    sys.exit('FAIL(T-QA-04): not a git work tree — cannot judge baseline drift '
             '(fail closed: an unverifiable baseline is not a protected baseline)')

rc, b_commit = git('log', '-1', '--format=%H', '--', 'governance/quality_baseline.json')
if rc != 0 or not b_commit:
    sys.exit('FAIL(T-QA-04): baseline file has no commit history (unreviewed)')

rc, g_commit = git('log', '-1', '--format=%H', '--', *GOV_PATHS)
if rc != 0 or not g_commit:
    sys.exit('FAIL(T-QA-04): cannot resolve last governance commit')

if b_commit == g_commit:
    print(f'PASS(T-QA-04): baseline reviewed together with governance @{b_commit[:12]}')
    sys.exit(0)

rc, _ = git('merge-base', '--is-ancestor', b_commit, g_commit)
if rc == 0:
    sys.exit(f'FAIL(T-QA-04): baseline drifted — governance changed in {g_commit[:12]} '
             f'but baseline last reviewed in {b_commit[:12]}. '
             f'Update quality_baseline.json (reviewed_by/at, applies_to_sha) in the '
             f'same commit.')
print(f'PASS(T-QA-04): baseline {b_commit[:12]} is newer than governance {g_commit[:12]}')
