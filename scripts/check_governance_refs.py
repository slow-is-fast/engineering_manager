#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-REF-01：治理引用完整性——编号必须真的存在。

为什么要有这条检查
------------------
2026-10-31 发现：`ALC-01` / `DG-01` / `REM-01` / `REM-02` 这四个编号被写进了
commit message、`audit_policy.json` 的 `control` 字段、`evidence_ledger.json`
的 `control` 字段、CI 步骤名 `T-ALC-01`——而它们在 rule-registry（53 条）与
control-catalog（49 条）里**都不存在**。

一个查不到、但看起来像控制的编号，比没有编号更糟：它制造"这条已经被某条
控制管住了"的错觉。而当时没有任何机器判定能发现它——`validate_controls.py`
只校验注册表与控制目录之间的双向一致性，**不扫引用方**。这条检查补的正是
引用方这一半。

做法（不扫散文，只查结构化引用）
------------------------------
用正则扫全文很容易误报（PR-01、SHA-256、日期片段都会命中），误报的下场
通常不是被人修正，而是被人把检查关掉。所以这里只校验**字段**：字段名在
REF_FIELDS 里、且字段值长得像编号时，才要求它解析得到真实对象。

编号可解析到下列任一命名空间即算通过：规则 / 控制 / 例外 / 审计问题（含
`AASEGS-` 前缀形式）/ §四 断言。

例外引用（EXC-*）、断言与审计问题号（AUD-*）、规则号（AASEGS-*）都能在
命名空间里解析，一律照查。唯一的豁免是 T-*（用例名）——它是否存在由审计
闭环判，本脚本不扫 tests/。豁免清单只有一项，且由 T-REF-10 钉死。

另外两项一致性
--------------
1. `quality_baseline.exceptions` 与 `exception_register.json` 的 id 与 expires
   必须一致。不一致就是登记缺陷——实际已发现过一次：EXC-01 在前者写
   2027-04-30、后者写 2027-01-31，而 `exception_valid` 的未过期判定依赖它，
   两个日期差三个月会影响"什么时候突然变红"。
2. 验收矩阵里每条 `exception_ref` 必须能解析到例外登记的条目。

失败关闭：任何一项不符即非零退出。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 长得像"编号"的形状：XX-99 / XXX-99 / AASEGS-AGT-007
ID_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,6}(?:-[A-Za-z0-9]+){1,3}$")
# 只校验这些字段的值
REF_FIELDS = {
    "control", "controls", "supporting_controls", "rule_ref",
    "requirement_ref", "target", "exception_ref", "addresses", "id",
    "test", "rule_id",
}
# 豁免清单。**只保留真正无法在本脚本内枚举的命名空间**——用例名（T-*）
# 是否存在由审计闭环判，本脚本不扫 tests/。
#
# 为什么这份清单要尽量短：它唯一的作用就是"放行"，而放行是这条检查唯一
# 会被打败的方式。曾经这里躺着 "G" 和 "R" 两个单字母条目，和第二重判断
# 合取后永远为假——死配置不是中性配置，它是个等着被踩的陷阱：哪天有人
# 把判断简化成"只看前缀"，REM-01 这类编造编号就整体豁免了。同理，
# AUD- / AASEGS- / EXC- 已实测可以解析（断言号、审计问题号、例外登记都在
# 命名空间里），所以它们**不需要**豁免，已从清单移除。
#
# 清单内容由 tests/test_governance_refs.py::test_T_REF_10 钉死：改动它
# 必须同时改那条用例，逼着改动者把理由写下来。
PREFIX_FREE = ("T-",)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


def _walk(node, key=None, out=None):
    """收集 (字段名, 字符串值) 对。"""
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in node.items():
            _walk(v, k, out)
    elif isinstance(node, list):
        for v in node:
            _walk(v, key, out)
    elif isinstance(node, str):
        out.append((key, node))
    return out


def build_namespaces(root):
    """返回可解析的编号集合。"""
    rules = set()
    reg = root / "rule-registry.json"
    if reg.exists():
        for r in load_json(reg).get("rules") or []:
            if r.get("rule_id"):
                rules.add(r["rule_id"])
    controls = set()
    cat = root / "control-catalog.yaml"
    if cat.exists():
        for c in load_json(cat).get("controls") or []:
            if c.get("id"):
                controls.add(c["id"])
    exceptions = set()
    exreg = root / "governance" / "exception_register.json"
    if exreg.exists():
        for e in load_json(exreg).get("exceptions") or []:
            if e.get("id"):
                exceptions.add(e["id"])
    issues, assertions = set(), set()
    mtx = root / "governance" / "acceptance_matrix.json"
    if mtx.exists():
        m = load_json(mtx)
        for iid, rec in (m.get("issues") or {}).items():
            issues.add(iid)
            issues.add("AASEGS-" + iid)
            for a in rec.get("assertions") or []:
                if a.get("id"):
                    assertions.add(a["id"])
    return {"rules": rules, "controls": controls, "exceptions": exceptions,
            "issues": issues, "assertions": assertions}


def known(ns):
    s = set()
    for v in ns.values():
        s |= v
    return s


def looks_like_id(value):
    return bool(value) and bool(ID_SHAPE.match(value)) and "-" in value


def check(root=ROOT):
    """返回 findings 列表；空列表表示通过。"""
    root = Path(root)
    findings = []
    ns = build_namespaces(root)
    resolvable = known(ns)

    for path in sorted((root / "governance").glob("*.json")):
        try:
            data = load_json(path)
        except json.JSONDecodeError as exc:
            findings.append({"kind": "unparseable", "where": path.name,
                             "detail": str(exc)})
            continue
        for key, value in _walk(data):
            if key not in REF_FIELDS:
                continue
            if key == "exception_ref":
                # 交给下面那段专门的 exception_ref 一致性检查，这里不再重复报。
                # 同一件事报两遍不是更严格，是噪音——噪音的下场和误报一样。
                continue
            if not looks_like_id(value):
                continue
            if value in resolvable:
                continue
            if value.startswith(PREFIX_FREE):
                continue
            findings.append({"kind": "unresolved_id", "where": path.name,
                             "field": key, "id": value,
                             "detail": "编号在规则/控制/例外/问题/断言里都找不到"})

    # 例外登记与基线里的例外必须一致
    exreg = root / "governance" / "exception_register.json"
    base = root / "governance" / "quality_baseline.json"
    if exreg.exists() and base.exists():
        reg = {e["id"]: e for e in
               (load_json(exreg).get("exceptions") or []) if e.get("id")}
        bl = load_json(base)
        bl_ex = {e["id"]: e for e in (bl.get("exceptions") or [])
                 if isinstance(e, dict) and e.get("id")}
        for eid in sorted(set(reg) | set(bl_ex)):
            if eid not in reg or eid not in bl_ex:
                findings.append({"kind": "exception_set_mismatch",
                                 "where": "quality_baseline.json",
                                 "id": eid,
                                 "detail": "基线里的例外与例外登记的条目集合不一致"})
                continue
            a, b = reg[eid].get("expires"), bl_ex[eid].get("expires")
            if a != b:
                findings.append({"kind": "exception_expiry_mismatch",
                                 "where": "quality_baseline.json", "id": eid,
                                 "detail": f"到期日不一致：例外登记 {a} / "
                                           f"基线 {b}（以例外登记为准）"})

    # 验收矩阵里的 exception_ref 必须解析得到
    mtx = root / "governance" / "acceptance_matrix.json"
    if mtx.exists():
        m = load_json(mtx)
        for iid, rec in (m.get("issues") or {}).items():
            for a in rec.get("assertions") or []:
                ref = a.get("exception_ref")
                if ref and ref not in ns["exceptions"]:
                    findings.append({"kind": "exception_ref_unresolved",
                                     "where": "acceptance_matrix.json",
                                     "id": a.get("id"), "detail":
                                     f"exception_ref={ref} 不在例外登记里"})
    return findings


def main(argv=None):
    root = Path(argv[0]).resolve() if argv else ROOT
    findings = check(root)
    if findings:
        print(f"FAIL(T-REF-01): {len(findings)} 处治理引用不成立")
        for f in findings:
            print(f"  [{f['kind']}] {f.get('where')}"
                  f"{' 字段 ' + f['field'] if f.get('field') else ''}"
                  f" {f.get('id', '')} :: {f['detail']}")
        return 1
    print("PASS(T-REF-01): 治理引用全部可解析；例外登记与基线一致")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
