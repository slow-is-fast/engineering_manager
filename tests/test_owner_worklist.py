# -*- coding: utf-8 -*-
"""Owner 工作清单生成器：投影正确 + 防漂移（--check）。

清单的全部价值在于"Owner 照着做能闭合"，一旦矩阵变了清单没变，
它就从工具变成陷阱。所以这里钉住：分类、计数、已签投影、--check 比对。
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'export_owner_worklist.py'


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')


def _repo(tmp, signed=False):
    issue_a = {'severity': 'P0', 'criteria': 'x', 'close_condition': '抽样记录齐备',
               'assertions': [{'id': 'AUD-001-03', 'kind': 'manual',
                               'human_gate': 'sampling_review', 'text': '人工抽样复核记录'}]}
    if signed:
        # 与 apply_signoffs.build_signoff_field 的真实输出保持一致：
        # 复核者字段名是 `by`，不是 reviewer（端到端测试抓出的偏差）。
        issue_a['assertions'][0]['signoff'] = {
            'by': 'alice', 'role': 'independent-reviewer',
            'ref': 'evidence/x.md', 'date': '2026-11-01',
            'signature': 'abc123def456', 'applied_by': 'builder',
            'applied_at': '2026-11-01T10:00:00+08:00'}
    issue_b = {'severity': 'P0', 'criteria': 'y', 'close_condition': '隔离环境测试通过',
               'assertions': [{'id': 'AUD-004-05', 'kind': 'manual',
                               'human_gate': 'isolated_env_integration_test',
                               'text': '隔离环境集成测试'}]}
    issue_c = {'severity': 'P1', 'criteria': 'z', 'close_condition': '—',
               'assertions': [{'id': 'AUD-013-03', 'kind': 'excepted',
                               'exception_ref': 'EXC-01', 'text': '第二主体不可达'}]}
    issue_t = {'severity': 'P0', 'criteria': 'w', 'close_condition': '自动',
               'assertions': [{'id': 'AUD-002-01', 'kind': 'test', 'text': '非 manual'}]}
    _write(tmp / 'governance' / 'acceptance_matrix.json',
           {'issues': {'AUD-001': issue_a, 'AUD-002': issue_t,
                       'AUD-004': issue_b, 'AUD-013': issue_c}})
    _write(tmp / 'governance' / 'quality_baseline.json',
           {'exceptions': [{'id': 'EXC-01', 'expires': '2027-01-31'},
                           {'id': 'EXC-02', 'expires': '2027-04-30'}]})


def _run(root, extra=None):
    return subprocess.run([sys.executable, str(SCRIPT), '--root', str(root),
                           *(extra or [])], capture_output=True, text=True)


def out(r):
    return r.stdout + r.stderr


class OwnerWorklistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        _repo(self.tmp)

    def test_generates_with_correct_buckets(self):
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 0, out(r))
        text = (self.tmp / 'governance' / 'owner_worklist.md').read_text(encoding='utf-8')
        # manual + excepted 共 3 条（test 类不进入清单）
        self.assertIn('总计（manual + excepted） | 3', text)
        self.assertIn('仅需文档与判断 | 1', text)
        self.assertIn('需要外部资源 | 1', text)
        self.assertIn('例外内（excepted） | 1', text)
        self.assertIn('AUD-001-03', text)
        self.assertIn('AUD-004-05', text)
        self.assertNotIn('AUD-002-01', text)   # test 类不该出现在人工清单里
        self.assertIn('隔离环境（容器/VM）', text)  # 所需资源列

    def test_role_and_deployment_gates_need_resources(self):
        """角色建制 / 责任人指派 / 后端部署 不属于"仅需文档"，必须归到需资源那侧。

        2026-11-02 修的分类错误：`security_owner_approval`、`data_matrix_approval`、
        `audit_backend_review` 三条此前被算进"可立即推进"，清单因此写着 11 条；
        照做会卡在"这个角色/这个人还不存在"。脚本注释自己写着"分类取保守，
        看起来也许能做但实际要外部资源的一律归到需资源那侧"——这次是没执行。
        """
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        gates = (('AUD-003-03', 'schema_review'),                # 纯评审
                 ('AUD-015-04', 'security_owner_approval'),      # 角色建制
                 ('AUD-016-04', 'data_matrix_approval'),         # 责任人指派
                 ('AUD-014-04', 'audit_backend_review'))         # 后端已部署
        issues = {aid[:7]: {'severity': 'P0', 'criteria': 'x', 'close_condition': 'y',
                            'assertions': [{'id': aid, 'kind': 'manual',
                                            'human_gate': gate, 'text': 't'}]}
                  for aid, gate in gates}
        _write(tmp / 'governance' / 'acceptance_matrix.json', {'issues': issues})
        _write(tmp / 'governance' / 'quality_baseline.json', {'exceptions': []})
        r = _run(tmp)
        self.assertEqual(r.returncode, 0, out(r))
        text = (tmp / 'governance' / 'owner_worklist.md').read_text(encoding='utf-8')
        self.assertIn('仅需文档与判断 | 1', text)
        self.assertIn('需要外部资源 | 3', text)

    def test_gate_invocation_pins_check_flag(self):
        """被门禁调用的双模式脚本，参数必须是校验模式，不是生成模式。

        同源评审 2026-11-02 构造出的回归路径（review_handoff.md §5 第 2 条、
        §10 第 2 条）：把 audit_policy.check_args 里 export_owner_worklist.py
        的 [["--check"]] 改成 [[]]，接线校验（T-QA-04b 的 D 段）照样绿——
        它只核对键存在与形状合法，**从不看参数值**；而 [[]] 会跑成生成模式：
        每轮改写投影文件、exit 0、什么也没查，T-OWN-01 名存实亡。
        这条测试钉住这一处的值。通用修法（脚本自声明被门禁调用时的必需参数）
        仍敞着，已留给正式评审讨论。
        """
        policy = json.loads((ROOT / 'governance' / 'audit_policy.json')
                            .read_text(encoding='utf-8'))
        self.assertEqual(
            policy['check_args']['scripts/export_owner_worklist.py'],
            [['--check']])

    def test_check_passes_when_in_sync(self):
        _run(self.tmp)
        r = _run(self.tmp, ['--check'])
        self.assertEqual(r.returncode, 0, out(r))
        self.assertIn('PASS(worklist)', r.stdout)

    def test_check_fails_when_file_missing(self):
        r = _run(self.tmp, ['--check'])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('不存在', out(r))

    def test_check_fails_after_manual_edit(self):
        # 手改清单 = 漂移，必须红
        _run(self.tmp)
        p = self.tmp / 'governance' / 'owner_worklist.md'
        p.write_text(p.read_text(encoding='utf-8') + '\n手改一行\n', encoding='utf-8')
        r = _run(self.tmp, ['--check'])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('不一致', out(r))

    def test_check_fails_after_matrix_changes(self):
        _run(self.tmp)
        m = json.loads((self.tmp / 'governance' / 'acceptance_matrix.json')
                       .read_text(encoding='utf-8'))
        m['issues']['AUD-001']['assertions'][0]['text'] = '改了要求但没重生成清单'
        _write(self.tmp / 'governance' / 'acceptance_matrix.json', m)
        r = _run(self.tmp, ['--check'])
        self.assertNotEqual(r.returncode, 0)

    def test_signed_assertion_shows_in_signed_section(self):
        tmp2 = Path(tempfile.mkdtemp())
        _repo(tmp2, signed=True)
        r = _run(tmp2)
        self.assertEqual(r.returncode, 0, out(r))
        text = (tmp2 / 'governance' / 'owner_worklist.md').read_text(encoding='utf-8')
        self.assertIn('### 已签署', text)
        self.assertIn('alice', text)
        self.assertIn('已签 1 ／ 未签 2', text)

    def test_check_is_newline_insensitive(self):
        """autocrlf 坑（2026-11-02 CI 实测）：矩阵/清单磁盘字节是 CRLF、仓库是
        LF 时，按原始字节算的指纹只在生成它的那台机器上成立——本地 --check 绿、
        CI 必红。指纹必须先规范化 CRLF→LF（与 verify_executor_pin 同一修法）。
        """
        _run(self.tmp)                                   # 生成清单
        m = self.tmp / 'governance' / 'acceptance_matrix.json'
        w = self.tmp / 'governance' / 'owner_worklist.md'
        # 模拟 Windows 文本模式写盘：两个文件全部转成 CRLF
        for f in (m, w):
            f.write_bytes(f.read_bytes().replace(b'\n', b'\r\n'))
        r = _run(self.tmp, ['--check'])
        self.assertEqual(r.returncode, 0, out(r))
        # 再模拟 git 入库后 CI 检出：全部转回 LF，同样必须绿
        for f in (m, w):
            f.write_bytes(f.read_bytes().replace(b'\r\n', b'\n'))
        r = _run(self.tmp, ['--check'])
        self.assertEqual(r.returncode, 0, out(r))

    def test_real_repo_selfcheck(self):
        # 真实清单必须与真实矩阵一致（矩阵变动后忘重生成即红）
        r = _run(ROOT, ['--check'])
        self.assertEqual(r.returncode, 0, out(r))


if __name__ == '__main__':
    unittest.main(verbosity=2)
