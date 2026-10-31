#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALC-01 / DG-01 的**生产入口**：让审计生命周期与数据闸门真的跑在门禁上。

为什么要有这个文件
------------------
`executor/auditlifecycle.py`（保留策略 / 来源识别 / 恢复）和
`executor/datagate.py`（删除须批准 / 删除后不得静默重现 / 超期保留）此前
只有单元测试在调用——**测试绿不等于控制生效**。CI 里十来个检查各跑各的，
没有任何东西把"这次治理跑过了"这件事记下来，也没有任何东西在检查它们
真的都跑了。

本脚本把这条链补上：

  `--check <path>`  跑一项必需检查，把结果写进带来源声明的审计流。
                    写之前先确认既有链完好——坏了就隔离、拒绝追加。
  `--verify`        对整条流做四件事：链完整性、来源可归因、保留期、
                    本次运行的必需检查是否全部落地；另外用 DataGate 校验
                    `evidence/` 的登记、哈希与删除批准。
  `--all`           本地一把梭：生成 run_id → 依次跑全部必需检查 → verify。
  `--accept-evidence`  把当前 evidence/ 登记进台账（需 --by 与 --reason）。

失败关闭的几处，都是"宁可红"的地方
--------------------------------
  - 审计流损坏：隔离坏段后拒绝写入，不让新事件接在坏链上把问题盖住。
  - 审计流不存在：verify 判红。缺流当"没问题"是最贵的一种假绿。
  - 检查不在 required_checks 里：拒绝记录。能往流里写什么，不能由调用方说。
  - 必需检查没有落地事件：判红。不跑就算过，等于门禁可以静默缺席。

诚实边界
--------
  - 审计流是本地运行产物（ `evidence/audit/` 不入版本库）。CI 每次从空开始，
    所以"保留期"在 CI 里几乎不会触发；它在本地持续累积的流上才有约束力。
  - 哈希链只证明流没被改过，不证明写入者是谁（AUD-014-04，manual）。
  - `evidence/` 的台账是**登记制**：新增证据必须先 `--accept-evidence`。
    这条会带来摩擦，是故意的——不登记就出现的证据，本来就不该被当成证据。
"""
import argparse
import calendar
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from executor.audit import AuditLog  # noqa: E402
from executor.auditlifecycle import (  # noqa: E402
    ProvenanceRegistry, RetentionPolicy, recover)
from executor.datagate import DataGate, DataGateRejected  # noqa: E402

POLICY_REL = 'governance/audit_policy.json'
BASELINE_REL = 'governance/quality_baseline.json'
LEDGER_REL = 'governance/evidence_ledger.json'

_STAMP = re.compile(r'_(\d{8})T(\d{6})Z\.[A-Za-z0-9]+$')

SOURCE_RUN = 'gov-run'
SOURCE_VERIFY = 'gov-verify'
SOURCE_EVIDENCE = 'gov-evidence'

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_TRAIL_UNUSABLE = 2
EXIT_PROVENANCE = 3
EXIT_RETENTION = 4
EXIT_INCOMPLETE = 5
EXIT_EVIDENCE = 6
EXIT_REFUSED = 7


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def policy_of(root):
    return load_json(Path(root) / POLICY_REL)


def baseline_of(root):
    return load_json(Path(root) / BASELINE_REL)


def trail_of(root, policy):
    return Path(root) / policy['trail_path']


def build_registry(policy):
    reg = ProvenanceRegistry()
    for s in policy['sources']:
        reg.declare(s['name'], writer=s.get('writer'),
                    event_types=s.get('event_types'))
    return reg


def build_retention(policy):
    rp = RetentionPolicy()
    for event_type, days in policy['retention'].items():
        rp.declare(event_type, days)
    return rp


def quarantine(root, policy, res):
    """把坏段原样落盘。**静默丢弃被篡改的段落，等于替篡改者擦掉痕迹。**"""
    qdir = Path(root) / policy['quarantine_dir']
    qdir.mkdir(parents=True, exist_ok=True)
    q = qdir / f'trail.broken.{int(time.time() * 1000)}.jsonl'
    q.write_text('\n'.join(res['dropped']) + '\n', encoding='utf8')
    return q


def normalize_bytes(data):
    return data.replace(b'\r\n', b'\n')


def _check_chain(root, policy, log, trail):
    """返回 (ok, 消息)。链坏了必须隔离并拒绝继续写。"""
    if not trail.exists():
        return True, None
    res = recover(log)
    if res['complete']:
        return True, None
    q = quarantine(root, policy, res)
    return False, (f'审计流损坏（{res["reason"]}），{len(res["dropped"])} 行'
                   f'已原样隔离到 {q.as_posix()}；拒绝在其后追加')


def run_check(name, *, root=ROOT, run_id=None, runner=None):
    """跑一项必需检查并把结果写进审计流。

    返回 (exit_code, messages)。检查失败仍会写事件——失败也要留痕。
    """
    root = Path(root)
    policy = policy_of(root)
    baseline = baseline_of(root)
    allowed = baseline['required_checks']

    if name not in allowed:
        return EXIT_REFUSED, [
            f'拒绝：{name} 不在 {BASELINE_REL} 的 required_checks 里。'
            f'能让调用方随意指定"写什么进审计流"，这条流就不值钱了。']

    trail = trail_of(root, policy)
    log = AuditLog(trail)
    ok, msg = _check_chain(root, policy, log, trail)
    if not ok:
        return EXIT_TRAIL_UNUSABLE, [msg]

    runner = runner or subprocess.run
    started = time.time()
    # 用 PYTHONPATH 而不是 cwd 兜底：`python tests/test_x.py` 会把 tests/ 放进
    # sys.path，而不是仓库根，`import executor` 直接 ModuleNotFoundError。
    # 也不能一律改写成 `-m unittest tests.test_x`——`tests/negative_static.py`
    # 不是 unittest 模块，那样会"跑 0 个用例、退出 0"，变成一条安静的假绿。
    env = dict(os.environ)
    env['PYTHONPATH'] = (str(root) + os.pathsep + env['PYTHONPATH']
                         if env.get('PYTHONPATH') else str(root))
    # 门禁强度由**治理配置**决定，不由 CI 决定：CI 若能自己传 `--enforce` /
    # `--expect-deny`，它就可以悄悄用弱模式跑一遍、照样记账成 ok——那种
    # "检查跑了、也确实绿了、但不是那个档位"的假绿最难发现。参数只从
    # audit_policy.check_args 读，调用方无权指定。
    # 一项检查可能是**多次调用**（比如 check_admission_gate 先出报告、
    # 再用 --require-level G1 判下限）。整串调用序列也是治理配置的一部分：
    # 少跑一次、或漏掉收紧的那一次，都等于把门禁调软。
    invocations = policy.get('check_args', {}).get(name) or [[]]
    code = EXIT_OK
    exit_code = 0
    tail = []
    for extra in invocations:
        proc = runner([sys.executable, str(root / name), *extra],
                      cwd=str(root), env=env, capture_output=True, text=True)
        exit_code = proc.returncode
        if proc.returncode != 0:
            code = EXIT_CHECK_FAILED
            tail = [(proc.stdout or '')[-1200:], (proc.stderr or '')[-600:]]
            break

    elapsed = round(time.time() - started, 3)
    verdict = 'ok' if code == EXIT_OK else 'failed'
    log.append_from(SOURCE_RUN, 'gov.check.completed', run_id=run_id,
                    check=name, args=invocations, verdict=verdict,
                    exit_code=exit_code, invocations=len(invocations),
                    duration_s=elapsed)

    lines = [f'{name}: {verdict} ({len(invocations)} 次调用, {elapsed}s)']
    if code != EXIT_OK:
        joined = ''.join(t for t in tail if t).strip()
        if joined:
            lines.append(joined)
    return code, lines


def evidence_digest(path):
    return hashlib.sha256(normalize_bytes(path.read_bytes())).hexdigest()


def evidence_files(root):
    """evidence/ 下受管的文件。audit/ 是运行产物，不登记。"""
    base = Path(root) / 'evidence'
    if not base.is_dir():
        return {}
    out = {}
    for p in sorted(base.glob('*')):
        if not p.is_file() or p.suffix not in ('.md', '.json'):
            continue
        out[p.relative_to(root).as_posix()] = p
    return out


def verify_evidence(root, policy, ledger_path=None, now=None):
    """用 DataGate 校验证据目录：登记、哈希、删除批准、超期。"""
    root = Path(root)
    ledger_path = Path(ledger_path or (root / LEDGER_REL))
    if not ledger_path.exists():
        return EXIT_EVIDENCE, [f'证据台账不存在：{ledger_path.as_posix()}；'
                               f'没有台账就无法判断"少了一个文件"']

    ledger = load_json(ledger_path)
    rp = RetentionPolicy()
    for category, days in policy['evidence_retention'].items():
        rp.declare(category, days)
    gate = DataGate(root / policy['gate_audit_path'], retention=rp)

    items = {}
    for it in ledger['items']:
        if it['id'] in items:
            return EXIT_EVIDENCE, [f'证据台账有重复 id：{it["id"]}']
        items[it['id']] = it
    if len(items) != len(ledger['items']):
        return EXIT_EVIDENCE, ['证据台账条数与去重后不一致']
    for iid, it in sorted(items.items()):
        gate.put(iid, it['sha256'], it['category'],
                 created_at=it['created_at'])

    approved = {}
    msgs = []
    code = EXIT_OK
    for d in ledger.get('deletions', []):
        try:
            gate.delete(d['id'], d.get('approval') or {})
        except DataGateRejected as exc:
            code = code or EXIT_EVIDENCE
            msgs.append(f'删除登记不成立：{d.get("id")} -> {exc}')
            continue
        approved[d['id']] = d
        # 删除后读取必须是墓碑且不带内容——路径与 get 出口一致
        got = gate.get(d['id'])
        if got.get('state') != 'TOMBSTONE' or 'content' in got:
            code = code or EXIT_EVIDENCE
            msgs.append(f'删除后仍能从出口读到内容：{d["id"]}')

    on_disk = {rel: evidence_digest(p) for rel, p in evidence_files(root).items()}

    for rel, digest in on_disk.items():
        if rel in approved:
            code = code or EXIT_EVIDENCE
            msgs.append(f'已批准删除的证据又出现在磁盘上（删除后再现）：{rel}')
            continue
        if rel not in items:
            code = code or EXIT_EVIDENCE
            msgs.append(f'未登记的证据文件：{rel}'
                        f'（新增证据须先 --accept-evidence 登记）')
            continue
        if items[rel]['sha256'] != digest:
            code = code or EXIT_EVIDENCE
            msgs.append(f'证据内容与台账哈希不符（被改动）：{rel}')

    for iid in items:
        if iid in approved:
            continue
        if iid not in on_disk:
            code = code or EXIT_EVIDENCE
            msgs.append(f'台账登记但文件不见了（未经批准的删除）：{iid}')

    for x in gate.sweep_retention(now=now):
        code = code or EXIT_EVIDENCE
        msgs.append(f'证据超期未处置 [{x["verdict"]}] {x["category"]} '
                    f'age={x.get("age_days")} limit={x.get("limit_days")}')
    return code, msgs


def verify(*, root=ROOT, run_id=None, ledger_path=None, now=None):
    """对整条审计流 + 证据目录做验收。返回 (exit_code, messages)。"""
    root = Path(root)
    policy = policy_of(root)
    baseline = baseline_of(root)
    trail = trail_of(root, policy)
    log = AuditLog(trail)

    if not trail.exists():
        return EXIT_TRAIL_UNUSABLE, [
            f'审计流不存在：{trail.as_posix()}。本次运行没有任何检查写入——'
            f'缺流当"没问题"是最贵的一种假绿。']
    if not run_id:
        return EXIT_INCOMPLETE, [
            '未提供 run_id，无法判定"本次运行的必需检查是否都跑了"。'
            'CI 请设 GOV_RUN_ID；本地请用 --all。']

    res = recover(log)
    if not res['complete']:
        q = quarantine(root, policy, res)
        return EXIT_TRAIL_UNUSABLE, [
            f'审计流损坏（{res["reason"]}），{len(res["dropped"])} 行已原样'
            f'隔离到 {q.as_posix()}']

    ok, errors = log.verify()
    if not ok:
        return EXIT_TRAIL_UNUSABLE, ['哈希链校验失败：' + '；'.join(errors[:5])]

    events = log.read()
    msgs = []
    codes = []

    finding = build_registry(policy).check(events)
    if not finding['ok']:
        codes.append(EXIT_PROVENANCE)
        for f in finding['findings'][:6]:
            msgs.append(f'来源可疑 [{f["kind"]}] seq={f["seq"]} '
                        f'{f.get("detail", "")}')

    for x in build_retention(policy).expired(events, now=now):
        codes.append(EXIT_RETENTION)
        msgs.append(f'超期未处置 [{x["verdict"]}] seq={x["event"].get("seq")} '
                    f'{x["category"]}')

    required = baseline['required_checks']
    landed = {e.get('check') for e in events
              if e.get('event_type') == 'gov.check.completed'
              and e.get('run_id') == run_id
              and e.get('verdict') == 'ok'}
    missing = [n for n in required if n not in landed]
    if missing:
        codes.append(EXIT_INCOMPLETE)
        msgs.append(f'本次运行（{run_id}）有 {len(missing)} 项必需检查没有'
                    f'成功落地：{missing}')

    ev_code, ev_msgs = verify_evidence(root, policy,
                                       ledger_path=ledger_path, now=now)
    if ev_code:
        codes.append(ev_code)
        msgs.extend(ev_msgs)

    if codes:
        log.append_from(SOURCE_VERIFY, 'gov.trail.finding', run_id=run_id,
                        checks_failed=len(codes), findings=len(msgs))
        return codes[0], msgs

    log.append_from(SOURCE_VERIFY, 'gov.trail.verified', run_id=run_id,
                    events=len(events), checks=len(required))
    return EXIT_OK, [f'审计流与证据目录通过：{len(events)} 条事件、'
                     f'{len(required)} 项必需检查全部落地']


def accept_evidence(*, root=ROOT, ledger_path=None, by=None, reason=None,
                    now=None):
    """把当前 evidence/ 登记进台账。必须说明谁批的、为什么。"""
    root = Path(root)
    if not by or not reason:
        return EXIT_REFUSED, ['--accept-evidence 需要 --by 与 --reason：'
                              '无署名的登记等于没人负责']
    policy = policy_of(root)
    ledger_path = Path(ledger_path or (root / LEDGER_REL))
    previous = load_json(ledger_path) if ledger_path.exists() else {
        'items': [], 'deletions': []}
    deleted = {d['id'] for d in previous.get('deletions', [])}

    tested_cat = policy['evidence_retention'].get('test-artifact')
    items = []
    rejected = []
    for rel, p in evidence_files(root).items():
        if rel in deleted:
            rejected.append(rel)
            continue
        name = p.name
        category = ('test-artifact'
                    if name.startswith('static_negative_') and tested_cat
                    else 'evidence')
        items.append({
            'id': rel,
            'sha256': evidence_digest(p),
            'category': category,
            'created_at': _mtime(p, now),
        })
    if rejected:
        return EXIT_REFUSED, [
            f'已批准删除的证据不得通过重新登记复活（那是 resurrect，'
            f'需要显式批准且批准人不得是当初的删除批准人）：{rejected}']

    ledger = {
        'version': '1.0',
        'control': 'DG-01',
        'purpose': ('证据登记台账。新增证据必须显式登记；登记后内容改动、'
                    '未经批准消失、批准删除后重新出现，都会被 gov_run --verify 判红。'),
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'generated_by': by,
        'reason': reason,
        'items': items,
        'deletions': previous.get('deletions', []),
    }
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2)
                           + '\n', encoding='utf8')

    log = AuditLog(Path(root) / policy['trail_path'])
    log.append_from(SOURCE_EVIDENCE, 'gov.evidence.registered', by=by,
                    reason=reason, items=len(items))
    return EXIT_OK, [f'已登记 {len(items)} 个证据文件（by={by}）']


def _mtime(path, now=None):
    """证据的产生时刻。

    优先用文件名里的 `_YYYYMMDDTHHMMSSZ` 戳——`cp`/`checkout` 会把 mtime
    刷成"刚刚"，那样任何证据看上去都永远新鲜，保留期就永远不触发。

    用 `timegm` 而不是 `mktime`：文件名带 `Z` 是 UTC，`mktime` 按本地时区解释
    会在东八区把年龄算少 8 小时——小，但这是那种"攒够一年就翻车"的小。
    """
    m = _STAMP.search(path.name)
    if m:
        try:
            return calendar.timegm(
                time.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S'))
        except ValueError:
            pass
    return path.stat().st_mtime


def detect_run_id(explicit=None):
    return explicit or os.environ.get('GOV_RUN_ID')


def main(argv=None):
    ap = argparse.ArgumentParser(description='治理运行入口（ALC-01 / DG-01）')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--check', metavar='PATH', help='跑一项必需检查并记账')
    g.add_argument('--verify', action='store_true', help='验收整条审计流')
    g.add_argument('--all', action='store_true', help='本地一把梭：跑全部必需检查后验收')
    g.add_argument('--accept-evidence', action='store_true',
                   help='登记 evidence/ 下的证据文件')
    ap.add_argument('--run-id', default=None)
    ap.add_argument('--root', default=None)
    ap.add_argument('--by', default=None)
    ap.add_argument('--reason', default=None)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else ROOT
    run_id = detect_run_id(args.run_id)

    if args.check:
        code, msgs = run_check(args.check, root=root, run_id=run_id)
    elif args.verify:
        code, msgs = verify(root=root, run_id=run_id)
    elif args.accept_evidence:
        code, msgs = accept_evidence(root=root, by=args.by, reason=args.reason)
    else:
        if not run_id:
            run_id = f'local-{time.strftime("%Y%m%dT%H%M%S")}'
        code = EXIT_OK
        for name in baseline_of(root)['required_checks']:
            c, m = run_check(name, root=root, run_id=run_id)
            print('\n'.join(m))
            if c != EXIT_OK:
                code = c
                break
        if code == EXIT_OK:
            code, msgs = verify(root=root, run_id=run_id)
        else:
            msgs = [f'检查未全部通过，跳过验收（run_id={run_id}）']

    for line in msgs:
        print(line)
    return code


if __name__ == '__main__':
    sys.exit(main())
