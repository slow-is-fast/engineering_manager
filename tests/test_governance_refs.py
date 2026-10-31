# -*- coding: utf-8 -*-
"""T-REF-01（scripts/check_governance_refs.py）的负向用例。

要防的是这一类事故：`ALC-01` / `DG-01` / `REM-01` / `REM-02` 被写进了
commit message、`audit_policy.json` 的 `control` 字段、CI 步骤名，
而它们在注册表与目录里都不存在。看起来像控制编号、实际查不到——
比没有编号更糟，因为它制造"这条已经被某条控制管住了"的错觉。

T-REF-01 只校验**结构化字段**，不扫散文，所以误报很低（误报的下场通常
不是被人修正，而是被人把检查关掉）。
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.check_governance_refs as refs  # noqa: E402


def _write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)
                    if not isinstance(obj, str) else obj, encoding="utf8")


def _mkroot(tmp, *, controls=("C1",), rules=("RULE-01",),
            exceptions=("EXC-01",), expires="2027-01-31", baseline=None,
            acceptance=None):
    root = Path(tmp)
    _write(root / "rule-registry.json",
           {"version": "1.1.1", "rules": [{"rule_id": r, "statement": "x"}
                                          for r in rules]})
    _write(root / "control-catalog.yaml",
           {"version": "1.1.1", "controls": [
               {"id": c, "requirement_ref": c, "addresses": ["AUD-101"],
                "test": "T-" + c, "status": "tested"} for c in controls]})
    _write(root / "governance" / "exception_register.json",
           {"exceptions": [{"id": e, "status": "ACTIVE",
                            "approver": "human", "approver_type": "human",
                            "expires": expires,
                            "waives": {"controls": list(controls),
                                       "requirement": ["tested"]},
                            "compensating_controls": ["x"],
                            "revocation": "y"} for e in exceptions]})
    if baseline is None:
        baseline = {"exceptions": [{"id": e, "expires": expires}
                                   for e in exceptions]}
    _write(root / "governance" / "quality_baseline.json", baseline)
    if acceptance is not None:
        _write(root / "governance" / "acceptance_matrix.json", acceptance)
    return root


class GovernanceRefsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aasegs-refs-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_T_REF_01_clean_repo_has_no_findings(self):
        root = _mkroot(self.tmp)
        self.assertEqual(refs.check(root), [])

    def test_T_REF_02_invented_control_id_is_caught(self):
        """复现 ALC-01 / DG-01 那类问题：字段里写了个查不到的编号。"""
        root = _mkroot(self.tmp)
        _write(root / "governance" / "audit_policy.json",
               {"control": "ALC-01", "purpose": "x"})
        f = refs.check(root)
        self.assertEqual([x["kind"] for x in f], ["unresolved_id"], f)
        self.assertEqual(f[0]["id"], "ALC-01")
        self.assertEqual(f[0]["field"], "control")

    def test_T_REF_03_known_control_id_passes(self):
        """正向对照：真实存在的控制编号不该被误报。"""
        root = _mkroot(self.tmp, controls=("EVD-01",))
        _write(root / "governance" / "audit_policy.json",
               {"assertion": "AUD-014-03",
                "supporting_controls": ["EVD-01", "EVD-02"]})
        # EVD-02 不在目录里 → 仍应报出来；EVD-01 不该
        f = refs.check(root)
        self.assertEqual([x["id"] for x in f], ["EVD-02"], f)

    def test_T_REF_04_other_namespaces_resolve_without_exemption(self):
        """跨命名空间编号不误报——前提是它们**真的存在**。

        这条原来是"豁免名单不误报"；豁免收窄到只剩 T-* 之后，其余一律照查，
        所以夹具必须真把这些编号注册进去。新写法比旧的强：它证明的是"能解析"，
        而不是"被放行"——被放行的东西随时可能本来就是编造的。
        """
        acc = {"issues": {"AUD-015": {"assertions": [
            {"id": "AUD-015-03", "kind": "test"}]}}}
        root = _mkroot(self.tmp, controls=("EVD-01",),
                       rules=("AASEGS-SUP-006",), acceptance=acc)
        _write(root / "governance" / "x.json",
               {"test": "T-GOV-01", "target": "AUD-015-03",
                "rule_ref": "AASEGS-SUP-006", "exception_ref": "EXC-01",
                "addresses": ["AASEGS-AUD-015"]})
        self.assertEqual(refs.check(root), [], refs.check(root))

    def test_T_REF_05_exception_expiry_mismatch_is_caught(self):
        """实际已发生过一次：登记写 2027-01-31、基线写 2027-04-30。"""
        root = _mkroot(self.tmp, expires="2027-01-31",
                       baseline={"exceptions": [
                           {"id": "EXC-01", "expires": "2027-04-30"}]})
        f = refs.check(root)
        self.assertEqual([x["kind"] for x in f], ["exception_expiry_mismatch"])
        self.assertIn("2027-01-31", f[0]["detail"])
        self.assertIn("2027-04-30", f[0]["detail"])

    def test_T_REF_06_exception_set_mismatch_is_caught(self):
        root = _mkroot(self.tmp, exceptions=("EXC-01", "EXC-02"),
                       baseline={"exceptions": [
                           {"id": "EXC-01", "expires": "2027-01-31"}]})
        f = refs.check(root)
        self.assertEqual([x["kind"] for x in f], ["exception_set_mismatch"])
        self.assertEqual(f[0]["id"], "EXC-02")

    def test_T_REF_07_dangling_exception_ref_is_caught(self):
        acc = {"issues": {"AUD-101": {"assertions": [
            {"id": "AUD-101-01", "kind": "excepted",
             "exception_ref": "EXC-GHOST"}]}}}
        root = _mkroot(self.tmp, acceptance=acc)
        f = refs.check(root)
        self.assertEqual([x["kind"] for x in f], ["exception_ref_unresolved"])
        self.assertEqual(f[0]["id"], "AUD-101-01")

    def test_T_REF_08_real_repo_is_clean(self):
        """对本仓库自检——这条会随仓库内容变化，属于"活的"守卫。"""
        self.assertEqual(refs.check(ROOT), [], refs.check(ROOT))

    def test_T_REF_10_exemption_list_is_pinned(self):
        """豁免清单钉死。

        放行是这条检查唯一会被打败的方式：往清单里加一项，就能让一类编造
        编号整体消失，而且不留痕迹。所以改清单必须同时改这条用例——逼着
        改动者把理由写下来，而不是顺手加一个前缀让 CI 变绿。
        """
        self.assertEqual(refs.PREFIX_FREE, ("T-",))
        for p in refs.PREFIX_FREE:
            self.assertTrue(p.endswith("-") and len(p) >= 2,
                            f"豁免项必须是完整前缀，不接受单字母：{p!r}")

    def test_T_REF_11_invented_aasegs_prefixed_id_is_caught(self):
        """收紧的直接收益：AASEGS- 前缀不再豁免。

        REM-01 / REM-02 当年就是这么混过去的——写在 commit message 和
        CI 步骤名里，看着像规则号，注册表里查不到。
        """
        root = _mkroot(self.tmp)
        _write(root / "governance" / "x.json",
               {"rule_ref": "AASEGS-REM-01", "target": "AUD-999-99"})
        f = refs.check(root)
        self.assertEqual(sorted(x["id"] for x in f),
                         ["AASEGS-REM-01", "AUD-999-99"], f)

    def test_T_REF_09_main_returns_nonzero_on_findings(self):
        root = _mkroot(self.tmp)
        _write(root / "governance" / "audit_policy.json",
               {"control": "DG-01", "purpose": "x"})
        self.assertEqual(refs.main([str(root)]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
