# -*- coding: utf-8 -*-
"""T-AUD-CLS：审计闭合评估的失败关闭路径（AUD-001～022 收口）。

check_audit_closure.py 的 `--enforce` 只调 `executor.closure.ClosureEvaluator
.assert_no_unbacked_closure()`：发现「声明 CLOSED / ACCEPTED_RISK 但控制级证据
不成立」即抛 `ClosureIntegrityError`。这正是要防的「把文档改完就当问题关闭」。

此前这条路径**没有任何用例守护**——`assert_no_unbacked_closure` 若被弱化
（变成永远通过），CI 的 `--enforce` 会安静地放过虚假关闭。本文件补上守卫：
负向证明「未落实就被声明关闭」会被拦；正向证明「开放中的问题」不构成违规
（拒绝不是永远拒绝）。
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from executor.closure import ClosureEvaluator, ClosureIntegrityError

TMP_PREFIX = "aasegs-closure-"


def _audit_md(status):
    """最小可解析的审计清单：§四 给严重程度，§二·A 给状态。"""
    return (
        "# 审计问题清单\n\n"
        "## 二·A 状态登记\n"
        "| 问题 | 严重程度 | 状态 |\n"
        f"| AUD-001 | P0 | {status} |\n\n"
        "## 四、逐项问题登记\n"
        "### AASEGS-AUD-001\n严重程度：P0\n"
    )


def _catalog(tested, evidence_at):
    return {
        "version": "1.1.1",
        "controls": [{
            "id": "X-01",
            "requirement_ref": "X-01",
            "owner": "o", "enforcer": "e",
            "evidence": "ev", "failure": "f", "test": "T-X-01",
            "status": "tested",
            "integration_evidence_uri": "https://example.invalid/1",
            "risk_level": "P0", "source_ref": "s",
            "addresses": ["AASEGS-AUD-001"],
            "state": {"documented": True, "configured": True,
                      "tested": tested, "verified": False,
                      "degraded": False, "excepted": False},
            "evidence_at": evidence_at,
        }],
    }


def make_base(tmp: Path, *, status, tested=True, evidence_at="2026-10-31"):
    (tmp / "AASEGS_Audit_Issues_Full.md").write_text(
        _audit_md(status), encoding="utf8")
    (tmp / "control-catalog.yaml").write_text(
        json.dumps(_catalog(tested, evidence_at)), encoding="utf8")
    return tmp


class AuditClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix=TMP_PREFIX))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_unbacked_closure_rejected(self):
        """控制未 tested 却声明 CLOSED → 必须判违规（unbacked_closure）。"""
        make_base(self.tmp, status="CLOSED", tested=False)
        ev = ClosureEvaluator(str(self.tmp)).load()
        with self.assertRaises(ClosureIntegrityError) as cm:
            ev.assert_no_unbacked_closure()
        self.assertIn("unbacked_closure", str(cm.exception))

    def test_stale_evidence_blocks_closure(self):
        """控制声称 tested 但证据过期 → 仍不算 machine_ready → 必须判违规。

        这条专门钉住「证据新鲜度」在闭合判定里的权重：把 evidence_at 拨旧，
        即使 state.tested=True 也应被拦（否则老化证据可被当成持续有效）。
        """
        make_base(self.tmp, status="CLOSED", tested=True,
                  evidence_at="2020-01-01")
        ev = ClosureEvaluator(str(self.tmp)).load()
        with self.assertRaises(ClosureIntegrityError) as cm:
            ev.assert_no_unbacked_closure()
        self.assertIn("unbacked_closure", str(cm.exception))

    def test_open_issue_not_closure_violation(self):
        """正向对照：仍在 OPEN / IN_PROGRESS 的问题不构成闭合违规（拒绝不是永远拒绝）。"""
        make_base(self.tmp, status="IN_PROGRESS", tested=True)
        ev = ClosureEvaluator(str(self.tmp)).load()
        res = ev.assert_no_unbacked_closure()   # 不应抛
        self.assertEqual(res["violations"], [],
                         f'开放中的问题被误判为闭合违规: {res["violations"]}')


if __name__ == "__main__":
    unittest.main()
