# -*- coding: utf-8 -*-
"""T-REF-02（scripts/check_control_refs.py）的测试用例。

防的是这一类事故：executor/ 或 scripts/ 的注释里写了 `AGT-999`、
`AASEGS-GOV-99` 这类在 rule-registry / control-catalog 里查不到的编号，
看起来像规则引用、实际是悬空——和 T-REF-01（治理 JSON 层）同源，
只是本脚本扫的是代码散文这一半。
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

import scripts.check_control_refs as cr  # noqa: E402


def _write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)
                    if not isinstance(obj, str) else obj, encoding="utf8")


def _mkroot(tmp, *, rules=("GOV-04", "GOV-12", "GOV-19", "AASEGS-AGT-001",
                           "AASEGS-AGT-005", "AASEGS-AGT-011"),
           controls=("ISO-01", "RTN-01", "PKG-01", "CHG-01", "ID-01")):
    root = Path(tmp)
    _write(root / "rule-registry.json",
           {"version": "1.1.1", "rules": [{"rule_id": r} for r in rules]})
    # control-catalog 虽是 .yaml 扩展名，内容实为 JSON（与真实仓库一致）
    _write(root / "control-catalog.yaml",
           {"version": "1.1.1",
            "controls": [{"id": c} for c in controls]})
    _write(root / "governance" / "exception_register.json",
           {"exceptions": []})
    _write(root / "governance" / "quality_baseline.json",
           {"exceptions": []})
    _write(root / "governance" / "acceptance_matrix.json",
           {"issues": {}})
    return root


class ControlRefsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aasegs-crefs-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _code(self, name, content):
        p = Path(self.tmp) / "executor" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf8")

    def test_T_REF_02_clean_code_has_no_findings(self):
        root = _mkroot(self.tmp)
        self._code("a.py", "# GOV-04 / GOV-12 / AASEGS-AGT-001 / ISO-01 refs\n")
        self.assertEqual(cr.check(root), [])

    def test_T_REF_02_invented_agent_rule_is_caught(self):
        """复现 AGT-999 那类：代码写短名、注册表无对应。"""
        root = _mkroot(self.tmp)
        self._code("b.py", "# AGT-999 does not exist in registry\n")
        f = cr.check(root)
        self.assertEqual([x["id"] for x in f], ["AGT-999"], f)
        self.assertEqual(f[0]["kind"], "code_ref_unresolved")

    def test_T_REF_02_qualified_form_rejected(self):
        """AASEGS-GOV-04 不再是规范拼写，严格模式下应判为悬空。"""
        root = _mkroot(self.tmp)
        self._code("c.py", "# AASEGS-GOV-04 is not canonical\n")
        f = cr.check(root)
        self.assertEqual([x["id"] for x in f], ["AASEGS-GOV-04"], f)
        self.assertEqual(f[0]["kind"], "code_ref_unresolved")

    def test_T_REF_02_short_agent_rule_rejected(self):
        """AGT-001 短名不再是规范拼写，严格模式下应判为悬空。"""
        root = _mkroot(self.tmp)
        self._code("d.py", "# AGT-001 binds to submitter\n")
        f = cr.check(root)
        self.assertEqual([x["id"] for x in f], ["AGT-001"], f)
        self.assertEqual(f[0]["kind"], "code_ref_unresolved")

    def test_T_REF_02_T_prefix_exempt(self):
        """测试用例名 T-QA-01 / T-REF-01 不得误报。"""
        root = _mkroot(self.tmp)
        self._code("e.py", "# see T-QA-01 and T-REF-01 for the gate\n")
        self.assertEqual(cr.check(root), [])

    def test_T_REF_02_iso8601_and_placeholders_ignored(self):
        root = _mkroot(self.tmp)
        self._code("f.py",
                   "# ISO-8601 timestamp; AUD-XXX-NN example; ALC-01 was a bug\n")
        self.assertEqual(cr.check(root), [])

    def test_T_REF_02_subid_strips_to_base(self):
        """AUD-009-03 应归到 AUD-009（断言命名空间）。"""
        root = _mkroot(self.tmp)
        _write(Path(root) / "governance" / "acceptance_matrix.json",
               {"issues": {"AUD-009": {"assertions": [{"id": "AUD-009-03"}]}}})
        self._code("g.py", "# covered by AUD-009-03 assertion\n")
        self.assertEqual(cr.check(root), [])

    def test_T_REF_02_real_repo_is_clean(self):
        """对本仓库自检——这条会随代码注释变化，属于"活的"守卫。"""
        self.assertEqual(cr.check(ROOT), [], cr.check(ROOT))

    def test_T_REF_02_main_returns_nonzero_on_findings(self):
        root = _mkroot(self.tmp)
        self._code("h.py", "# AGT-777 missing\n")
        self.assertEqual(cr.main([str(root)]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
