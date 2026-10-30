#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_admission_gate.py —— GATE-01 准入门槛判定的 CI 入口。

用法：
  python scripts/check_admission_gate.py                      # 报告模式：打印判定结果，恒退出 0
  python scripts/check_admission_gate.py --require-level G1   # 等级下限模式：低于 G1 非零退出
  python scripts/check_admission_gate.py --require-risk R0    # 风险准入模式：R0 不放行非零退出

语义（与文档声明相反，这里是**机器判定**）：
  - 报告模式的"DENY"不是脚本失败，而是门槛的**正确结论**——当前账本不满足
    更高等级是事实，把它如实打印出来正是 GATE-01 的证据；
  - CI 采用「等级下限」而非「必须达标 G2」：下限是 Owner 实际达到并批准的
    最低等级（当前 G1）。回退到 G1 之下（输入损坏、事实源冲突、证据全过期）
    会让 CI 变红——这是防退化，而不是伪装达标；
  - GateInputError（输入缺失/自相矛盾）恒非零退出：失败关闭。
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from executor.gate import AdmissionGate, GateInputError, AdmissionDenied, LEVELS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-level", choices=LEVELS,
                    help="低于该等级时非零退出（防退化下限）")
    ap.add_argument("--require-risk", default=None,
                    help="要求该风险等级放行，否则非零退出")
    ap.add_argument("--case-review-ref", default=None,
                    help="R2/R3 逐案评审的证据引用")
    ap.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = ap.parse_args()

    try:
        g = AdmissionGate(BASE).load()
        asmt = g.evaluate()
    except GateInputError as exc:
        print(f"FAIL-CLOSED (GateInputError): {exc}", file=sys.stderr)
        return 2

    case_review = None
    if args.case_review_ref:
        case_review = {"approval_ref": args.case_review_ref,
                       "approver": "slow-is-fast", "principal_type": "human"}

    print_risks = [args.require_risk] if args.require_risk else ["R0", "R1", "R2", "R3"]

    admissions = {}
    for rk in print_risks:
        try:
            admissions[rk] = g.admit(rk, case_review=case_review)
        except AdmissionDenied as exc:
            admissions[rk] = {"decision": "DENY", "reason": str(exc)}

    if args.json:
        print(json.dumps({"assessment": asmt, "admissions": admissions},
                         ensure_ascii=False, indent=2, default=str))
        return 0

    print(f"=== GATE-01 准入判定（{asmt['evaluated_at']}）===")
    print(f"成熟度等级: {asmt['level']}   阻断项: {len(asmt['blockers'])}   "
          f"豁免: {len(asmt['waivers'])}")
    for r in asmt["levels"]:
        mark = "PASS" if r["satisfied"] else "BLOCKED"
        print(f"  [{mark}] {r['level']} {r['title'] or ''}  "
              f"({len(r['blockers'])} blockers)")
    if asmt["waivers"]:
        for w in asmt["waivers"]:
            print(f"  豁免: {w['control']} 的 {w['requirement']} 要求 <- {w['by']}")
    if asmt["blockers"]:
        from collections import Counter
        cnt = Counter(b["reason"] for b in asmt["blockers"])
        print(f"  阻断原因分布: {dict(cnt)}")
        for b in asmt["blockers"][:10]:
            print(f"    - {b['type']}/{b['id']}: {b['reason']}")
        if len(asmt["blockers"]) > 10:
            print(f"    ... 共 {len(asmt['blockers'])} 项")
    for rk, d in admissions.items():
        print(f"风险 {rk}: {d['decision']}  (需 {d.get('required_level')}, "
              f"实际 {d.get('actual_level')})")

    if args.require_level:
        got, want = LEVELS.index(asmt["level"]), LEVELS.index(args.require_level)
        if got < want:
            print(f"\nFAIL: level {asmt['level']} < required {args.require_level}",
                  file=sys.stderr)
            return 1
    if args.require_risk:
        d = admissions[args.require_risk]
        if d["decision"] != "ALLOW":
            print(f"\nFAIL: risk {args.require_risk} not admitted", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
