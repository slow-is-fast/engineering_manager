#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_audit_closure.py —— 审计问题闭合评估的 CI / 运维入口（AUD-001～022）。

用法：
  python scripts/check_audit_closure.py              # 报告：逐问题列出 machine_ready 与建议状态
  python scripts/check_audit_closure.py --enforce     # 防虚假关闭：有 violations 即非零退出
  python scripts/check_audit_closure.py --write       # 落盘 governance/audit_closure_status.json

语义：
  - 报告里 `READY_FOR_REVIEW` 只表示**控制级证据齐备**，表示可以进入验收评审，
    **不表示问题已关闭**；`CLOSED` 必须由独立复核给出（当前受 EXC-01 约束）。
  - `--enforce` 拦截的是"声明 CLOSED / ACCEPTED_RISK 但控制级证据不成立"——
    这正是本流程要防的记账不实。
  - 输入缺失/事实源冲突 → 失败关闭（退出码 2）。
"""
import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from executor.closure import ClosureEvaluator, ClosureIntegrityError  # noqa: E402
from executor.gate import GateInputError  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enforce", action="store_true",
                    help="发现记账不实（虚假关闭）即非零退出")
    ap.add_argument("--write", action="store_true",
                    help="写 governance/audit_closure_status.json")
    ap.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = ap.parse_args()

    try:
        ev = ClosureEvaluator(BASE).load()
        res = ev.evaluate()
    except GateInputError as exc:
        print(f"FAIL-CLOSED (GateInputError): {exc}", file=sys.stderr)
        return 2

    if args.write:
        out = BASE / "governance" / "audit_closure_status.json"
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2,
                                  default=str), encoding="utf-8")
        print(f"written: {out.relative_to(BASE)}")

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    else:
        s = res["summary"]
        print(f"=== 审计问题闭合评估（{s['evaluated_at']}）===")
        print(f"问题 {s['total']} 项 | 控制级证据齐备 {s['machine_ready']} | "
              f"可进入评审 {s['ready_for_review']} | 已声明关闭 {s['claimed_closed']} | "
              f"违规 {s['violations']}")
        ready = [v for v in res["issues"].values() if v["suggested"] == "READY_FOR_REVIEW"]
        if ready:
            print("可进入评审（仅控制级证据齐备，不等于验收通过）：")
            print("  " + ", ".join(v["issue"] for v in ready))
        blocked = [v for v in res["issues"].values()
                   if v["suggested"] in ("OPEN", "IN_PROGRESS")]
        if blocked:
            print("仍受阻：")
            for v in blocked:
                reasons = ", ".join(f"{b['control']}:{b['reason']}"
                                    for b in v["blockers"]) or "—"
                print(f"  {v['issue']} ({v['severity']}) {v['suggested']} ← {reasons}")
        if res["violations"]:
            print("违规（记账不实）：")
            for v in res["violations"]:
                print(f"  {v['issue']}: {v['reason']}")

    if args.enforce:
        try:
            ev.assert_no_unbacked_closure()
        except ClosureIntegrityError as exc:
            print(f"\nFAIL: unbacked closure detected: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
