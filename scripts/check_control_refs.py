#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-REF-02：代码引用完整性——executor/ 与 scripts/ 里提到的规则/控制编号必须真实存在。

为什么要有这条检查
------------------
`check_governance_refs.py`（T-REF-01）只扫 `governance/*.json` 的结构化字段，
**不扫代码散文**。而 executor/ 与 scripts/ 的注释、文档字符串大量引用规则与控制
编号（如 `GOV-06`、`ISO-01`、`GOV-04`、`AASEGS-AGT-011`、`PKG-01`、`CHG-01`）。
其中任何一个指向注册表/控制目录里不存在的编号，就是"代码声称某条规则/控制
存在、实际没注册"的假覆盖——比没有编号更糟。T-REF-01 管治理 JSON，本脚本管代码，
两半合起来才是完整的"引用方"覆盖。

命名约定的现实（已对齐代码，改为严格模式）
------------------------------------------
注册表规则用短名 `GOV-04`、Agent 规则用限定名 `AASEGS-AGT-001`、支撑控制用
`AASEGS-SUP-003`——前缀风格本身不一致（历史成因）。续十二已把生产代码注释
全部对齐到这些规范拼写，故本检查器**不再做前缀归一化**，改为严格模式：
只接受注册表里真实存在的规范拼写，拼写分歧一律判为悬空并失败关闭（fail-closed），
防止漂移重新引入分歧。子编号 `AUD-009-03` 仍归到其基 `AUD-009`（同一断言细分，
非拼写分歧）。

防误报（误报的下场不是被修正，是被关掉）
----------------------------------------
- `T-*` 一律跳过：那是测试用例名（T-QA-01、T-REF-01…），由 T-REF-03
  （`check_rule_tests.py`）管，与本脚本关注的"规则/控制编号"无关（与 T-REF-01
  的 PREFIX_FREE 同源）。2026-11-02 更正：此处原写"由审计闭环管"——审计闭环
  判的是 §四 断言的 verdict 与证据，从不解析 `verification.tests`，那句注释
  指向了一个不存在的执行者。
- 显式 IGNORE：ISO-8601（日期格式非控制）、AUD-XXX-NN / T-XXX / T-ID（文档占位符）、
  ALC-01 / DG-01 / REM-01 / REM-02（历史编造编号，只在"讲那次事故"的散文里出现，
  治理 JSON 层已由 T-REF-01 覆盖）。
- 只查白名单前缀（GOV/AGT/ISO/CHG/PKG/RTN/PRV/RCV/RSR/EVL/DRL/ID/AUD/EXC/SUP/LFC），
  过滤 SHA-256 / PR-01 之类误中。

失败关闭：任何未解析的代码引用即非零退出。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))  # 让同目录的 check_governance_refs 可被导入
sys.path.insert(0, str(ROOT))

from check_governance_refs import build_namespaces, known  # noqa: E402

# 只查这些家族前缀，过滤 SHA-256 / PR-01 等噪音
FAMILIES = ("GOV", "AGT", "ISO", "CHG", "PKG", "RTN", "PRV", "RCV",
            "RSR", "EVL", "DRL", "ID", "AUD", "EXC", "SUP", "LFC")
TOKEN_RE = re.compile(
    r"(?:AASEGS-)?(?:" + "|".join(FAMILIES) +
    r")-[A-Z0-9]+(?:-[A-Z0-9]+)?")

# 显式忽略：非控制 / 占位符 / 历史编造编号（详情见模块 docstring）
IGNORE = {"ISO-8601", "AUD-XXX-NN", "T-XXX", "T-ID",
          "ALC-01", "DG-01", "REM-01", "REM-02"}


def resolves(token, resolvable):
    """严格模式：仅接受注册表中的规范拼写（原样解析）。

    不再做 `AASEGS-` 前缀的加/去归一化——代码注释已对齐到规范形式
    （GOV-* / AASEGS-AGT-* / AASEGS-SUP-*，见续十二），拼写分歧一律判为
    悬空，fail-closed 防漂移。子编号 AUD-009-03 -> AUD-009 仍归基
    （同一断言细分，非拼写分歧）。
    """
    if token in resolvable:
        return True
    # 子编号归基（唯一保留的归一：同一断言的细分引用）
    if "-" in token:
        base = token.rsplit("-", 1)[0]
        if base in resolvable:
            return True
    return False


def check(root=ROOT):
    """返回 findings 列表；空列表表示通过。"""
    root = Path(root)
    ns = build_namespaces(root)
    resolvable = known(ns)
    findings = []
    files = list(root.glob("executor/**/*.py")) + \
        list(root.glob("scripts/**/*.py"))
    for f in files:
        txt = f.read_text(encoding="utf-8", errors="replace")
        for m in TOKEN_RE.finditer(txt):
            tok = m.group(0)
            if tok.startswith("T-"):          # 测试用例名，豁免
                continue
            if tok in IGNORE:                 # 日期格式 / 占位符 / 历史编造
                continue
            if "XXX" in tok:                  # AUD-XXX-NN 之类文档占位
                continue
            if resolves(tok, resolvable):
                continue
            findings.append({
                "kind": "code_ref_unresolved",
                "where": f.relative_to(root).as_posix(),
                "id": tok,
                "detail": "代码引用的规则/控制编号在 rule-registry / "
                          "control-catalog 里都解析不到（严格模式：拼写分歧即悬空）",
            })
    return findings


def main(argv=None):
    root = Path(argv[0]).resolve() if argv else ROOT
    findings = check(root)
    if findings:
        print(f"FAIL(T-REF-02): {len(findings)} 处代码引用编号不存在")
        for f in findings:
            print(f"  [{f['kind']}] {f['where']} :: {f['id']} :: {f['detail']}")
        return 1
    print("PASS(T-REF-02): 代码里引用的规则/控制编号全部为注册表规范拼写"
          "（严格模式，无前缀归一化）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
