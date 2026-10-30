# -*- coding: utf-8 -*-
"""T-QA-01 / T-QA-02 / T-QA-04 的负向用例。

2026-10-30 冷读复核后大幅扩充。原版只有 6 条"样板级"用例，把三条控制从 drill
升成了 automated，却**完全没覆盖**审查者实测出来的绕过路径——等于给了
"有负向用例"的覆盖错觉。本轮把每条已知绕过路径都固化成用例。

命名约定：test_t_qa_0X_<场景>_rejected / _accepted。拒绝类用例都配正向对照，
证明拒绝不是"永远拒绝"。
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent    # tests/ 的上级才是仓库根
SCRIPTS = ROOT / 'scripts'

PINNED = 'actions/checkout@' + 'a' * 40
DIGEST = 'docker://alpine@sha256:' + 'b' * 64


def run_script(name, cwd):
    r = subprocess.run([sys.executable, str(SCRIPTS / name), str(cwd)],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf8')


class CiAppBindingTests(unittest.TestCase):
    """T-QA-01：CI 应用必须绑定不可变引用。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='aasegs-qa01-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _wf(self, body, name='ci.yml'):
        write(self.tmp / '.github' / 'workflows' / name,
              'jobs:\n  j:\n    steps:\n' + body)

    def check(self):
        return run_script('verify_ci_app_binding.py', self.tmp)

    # ---- 基本 ----
    def test_t_qa_01_unpinned_action_rejected(self):
        self._wf('      - uses: actions/checkout@v4\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '浮动 tag 竟然通过了')
        self.assertIn('T-QA-01', out)
        self.assertIn('actions/checkout@v4', out)

    def test_t_qa_01_pinned_action_accepted(self):
        """正向对照：证明上面的拒绝不是"永远拒绝"。"""
        self._wf(f'      - uses: {PINNED}\n      - uses: {DIGEST}\n')
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn('PASS(T-QA-01)', out)

    # ---- 冷读 F3：只扫 *.yml 时改名 .yaml 即失明 ----
    def test_t_qa_01_yaml_extension_rejected(self):
        self._wf('      - uses: actions/checkout@v4\n', name='ci.yaml')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '改名 .yaml 竟然通过了')
        self.assertIn('ci.yaml', out)

    # ---- 冷读 F3b：什么都没扫到不等于通过 ----
    def test_t_qa_01_zero_refs_fails_closed(self):
        self._wf('      - run: echo hi\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '扫到 0 条引用竟然通过')
        self.assertIn('scanned 0', out)

    # ---- 冷读 F6：行正则覆盖不到的 YAML 写法 ----
    def test_t_qa_01_inline_flow_mapping_rejected(self):
        self._wf('      - {uses: actions/checkout@v4}\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '流映射内联 dict 竟然通过了')

    def test_t_qa_01_quoted_key_rejected(self):
        self._wf("      - 'uses': actions/checkout@v4\n")
        rc, out = self.check()
        self.assertNotEqual(rc, 0, "引号 key 竟然通过了")

    # ---- 冷读 F4：docker:// 豁免被滥用 ----
    def test_t_qa_01_docker_without_digest_rejected(self):
        self._wf('      - uses: docker://alpine:latest\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, 'docker 浮动 tag 竟然通过了')

    def test_t_qa_01_docker_with_digest_accepted(self):
        self._wf(f'      - uses: {DIGEST}\n')
        rc, out = self.check()
        self.assertEqual(rc, 0, out)

    # ---- 冷读 F5：composite action 里藏 upstream 调用 ----
    def test_t_qa_01_composite_action_internals_rejected(self):
        """composite action 的定义里藏着 upstream 调用（放在 .github/actions/ 下）。"""
        self._wf('      - uses: ./.github/actions/helper\n')
        write(self.tmp / '.github' / 'actions' / 'helper' / 'action.yml',
              'runs:\n  using: composite\n  steps:\n'
              '      - uses: actions/checkout@v4\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, 'composite 内部的浮动 tag 竟然通过了')
        self.assertIn('actions/checkout@v4', out)

    def test_t_qa_01_composite_action_outside_actions_dir_rejected(self):
        """放在仓库内任意路径的 composite action 也要被跟踪到。

        只预扫 .github/actions/** 会漏掉这里——这条用例专门锁住"跟踪引用"
        这段逻辑，避免它被误当成冗余而删掉。
        """
        self._wf('      - uses: ./local-actions/helper\n')
        write(self.tmp / 'local-actions' / 'helper' / 'action.yml',
              'runs:\n  using: composite\n  steps:\n'
              '      - uses: actions/checkout@v4\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '仓库内任意路径的 composite 竟然通过了')
        self.assertIn('actions/checkout@v4', out)

    def test_t_qa_01_dangling_local_action_rejected(self):
        """本地 action 路径不存在 = 断链，等价于放行任意内容。"""
        self._wf('      - uses: ./.github/actions/ghost\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '指向不存在的本地 action 竟然通过')
        self.assertIn('does not exist', out)


class TestFloorTests(unittest.TestCase):
    """T-QA-02：验收用例数不得低于基线。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='aasegs-qa02-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _baseline(self, floor):
        write(self.tmp / 'governance' / 'quality_baseline.json',
              json.dumps({'test_thresholds': {'min_test_count': floor}}))

    def check(self):
        return run_script('verify_test_floor.py', self.tmp)

    def test_t_qa_02_test_count_drop_rejected(self):
        self._baseline(110)
        write(self.tmp / 'tests' / 'test_x.py', 'def test_only_one():\n    pass\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '删掉大量用例竟然通过')
        self.assertIn('dropped', out)

    def test_t_qa_02_missing_baseline_fails_closed(self):
        rc, out = self.check()
        self.assertNotEqual(rc, 0)
        self.assertIn('missing', out)

    # ---- 冷读 F8：bool 是 int 子类，True 会被当下限 1 放行 ----
    def test_t_qa_02_bool_floor_rejected(self):
        self._baseline(True)
        write(self.tmp / 'tests' / 'test_x.py', 'def test_a():\n    pass\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, 'min_test_count=True 竟然通过')
        self.assertIn('positive integer', out)

    def test_t_qa_02_zero_and_negative_floor_rejected(self):
        for bad in (0, -5):
            with self.subTest(floor=bad):
                self._baseline(bad)
                write(self.tmp / 'tests' / 'test_x.py', 'def test_a():\n    pass\n')
                rc, out = self.check()
                self.assertNotEqual(rc, 0, f'下限 {bad} 竟然通过')

    # ---- 冷读 F9：正则计数既漏数又能注水 ----
    def test_t_qa_02_async_def_is_counted(self):
        """async def test_* 也要计入，否则删掉异步用例不会被发现。"""
        self._baseline(2)
        write(self.tmp / 'tests' / 'test_x.py',
              'async def test_async_one():\n    pass\n\n'
              'def test_sync_one():\n    pass\n')
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn('2 acceptance cases', out)

    def test_t_qa_02_docstring_injection_not_counted(self):
        """三引号里写满 def test_xxx 不该刷数。"""
        self._baseline(2)
        write(self.tmp / 'tests' / 'test_x.py',
              'def test_real_one():\n    pass\n\n'
              'DOC = """\ndef test_pad_one():\n    pass\ndef test_pad_two():\n'
              '    pass\n"""\n')
        rc, out = self.check()
        # 计数必须是 1：三引号里的两个 def 不应被算成用例
        self.assertIn('count dropped: 1 <', out)
        self.assertNotEqual(rc, 0, '字符串里注水竟然把数量刷上去了')

    def test_t_qa_02_subdirectory_cases_are_counted(self):
        self._baseline(2)
        write(self.tmp / 'tests' / 'sub' / 'test_y.py',
              'def test_a():\n    pass\ndef test_b():\n    pass\n')
        rc, out = self.check()
        self.assertEqual(rc, 0, out)


class QualityBaselineTests(unittest.TestCase):
    """T-QA-04：质量基线完整、不漂移、收紧要审批。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='aasegs-qa04-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # 基线漂移判定依赖提交历史，所以每个用例都在独立的空仓库里跑
        subprocess.run(['git', '-C', str(self.tmp), 'init', '-q'],
                       capture_output=True, check=True)

    def git(self, *args):
        r = subprocess.run(
            ['git', '-C', str(self.tmp), '-c', 'user.email=qa@example.com',
             '-c', 'user.name=qa', '-c', 'commit.gpgsign=false', *args],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def check(self):
        return run_script('verify_quality_baseline.py', self.tmp)

    def baseline(self, **over):
        b = {
            'required_checks': ['scripts/verify_test_floor.py'],
            'trusted_ci_sources': ['github-actions'],
            'executor_pin_version': {'pinned_commit': 'c' * 40,
                                     'pinned_tree': 'f' * 40},
            'test_thresholds': {'min_test_count': 10},
            'applies_to_sha': 'x', 'exceptions': [],
            'change_approval': {'rule': 'r'},
            'reviewed_by': 'owner', 'reviewed_at': '2026-10-30T00:00:00+08:00',
        }
        b.update(over)
        return b

    def commit_baseline(self, pin=None, **over):
        write(self.tmp / 'governance' / 'quality_baseline.json',
              json.dumps(self.baseline(**over)))
        write(self.tmp / 'scripts' / 'verify_test_floor.py', '# stub\n')
        # executor_pin.json 本身也是治理文件：单独提交会先触发漂移判定，
        # 测不到交叉一致性。必须和基线同批提交。
        if pin is not None:
            write(self.tmp / 'governance' / 'executor_pin.json',
                  json.dumps(pin))
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline + governance')

    def commit_change(self, baseline=None, gov=None, msg='change'):
        if baseline is not None:
            write(self.tmp / 'governance' / 'quality_baseline.json',
                  json.dumps(baseline))
        if gov is not None:
            write(self.tmp / 'scripts' / 'verify_test_floor.py', gov)
        self.git('add', '.')
        self.git('commit', '-qm', msg)

    # ---- 要素完整性 ----
    def test_t_qa_04_incomplete_baseline_rejected(self):
        write(self.tmp / 'governance' / 'quality_baseline.json',
              json.dumps({'required_checks': ['a']}))
        rc, out = self.check()
        self.assertNotEqual(rc, 0)
        self.assertIn('incomplete', out)

    def test_t_qa_04_empty_required_checks_rejected(self):
        """冷读 F7：没有例外是好事，没有必需检查等于没有基线。"""
        write(self.tmp / 'governance' / 'quality_baseline.json',
              json.dumps(self.baseline(required_checks=[])))
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '必需检查为空竟然通过')
        self.assertIn('empty', out)

    def test_t_qa_04_unparseable_reviewed_at_rejected(self):
        write(self.tmp / 'governance' / 'quality_baseline.json',
              json.dumps(self.baseline(reviewed_at='昨天')))
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '不可解析的时间戳竟然通过')

    def test_t_qa_04_required_checks_must_point_to_real_file(self):
        write(self.tmp / 'governance' / 'quality_baseline.json',
              json.dumps(self.baseline(required_checks=['scripts/ghost.py'])))
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '指向不存在文件的必需检查竟然通过')

    # ---- 漂移 ----
    def test_t_qa_04_baseline_drift_rejected(self):
        self.commit_baseline()
        rc, out = self.check()
        self.assertEqual(rc, 0, out)          # 同批提交 → 通过
        self.commit_change(gov='# v2\n', msg='change governance only')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '治理变了基线没动，竟然通过')
        self.assertIn('drift', out)

    # ---- 冷读 F1：浅克隆下恒绿，最致命的一条 ----
    def test_t_qa_04_shallow_repo_fails_closed(self):
        self.commit_baseline()
        # 写 .git/shallow 即宣告浅仓库，等价于 CI 里 depth=1 的 checkout
        write(self.tmp / '.git' / 'shallow', self.git('rev-parse', 'HEAD') + '\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '浅克隆下竟然通过——这正是冷读写死的恒绿')
        self.assertIn('shallow', out)

    # ---- 冷读 F10：未提交改动对原版完全不可见 ----
    def test_t_qa_04_uncommitted_change_fails_closed(self):
        self.commit_baseline()
        write(self.tmp / 'scripts' / 'verify_test_floor.py', '# dirty\n')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '治理范围有未提交改动竟然通过')
        self.assertIn('uncommitted', out)

    # ---- 冷读 F2：放宽必须带审批，否则"改数字"一次性绕过 ----
    def test_t_qa_04_lowered_floor_without_approval_rejected(self):
        self.commit_baseline(test_thresholds={'min_test_count': 110})
        self.commit_change(
            baseline=self.baseline(test_thresholds={'min_test_count': 1}),
            gov='# v2\n', msg='silently lower the floor')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '无审批下调阈值竟然通过')
        self.assertIn('lowered', out)

    def test_t_qa_04_lowered_floor_with_approval_accepted(self):
        """正向对照：有审批记录的下调是治理决定，应当放行。"""
        self.commit_baseline(test_thresholds={'min_test_count': 110})
        approval = {'type': 'threshold_lower', 'from': 110, 'to': 1,
                    'approver': 'security_owner',
                    'reason': '迁移测试框架，旧计数口径不适用'}
        self.commit_change(
            baseline=self.baseline(test_thresholds={'min_test_count': 1},
                                   change_approvals=[approval]),
            gov='# v2\n', msg='lower floor with approval')
        rc, out = self.check()
        self.assertEqual(rc, 0, out)

    def test_t_qa_04_removed_required_check_without_approval_rejected(self):
        """只移除**部分**必需检查：清空会先被"不得为空"拦下，测不到这条规则。"""
        two = ['scripts/verify_test_floor.py', 'scripts/verify_ci_app_binding.py']
        self.commit_baseline(required_checks=two)
        write(self.tmp / 'scripts' / 'verify_ci_app_binding.py', '# stub\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'add second required check')
        self.commit_change(
            baseline=self.baseline(required_checks=two[:1]),
            gov='# v2\n', msg='silently drop one required check')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '无审批移除必需检查竟然通过')
        self.assertIn('removed', out)

    # ---- 交叉一致性：基线里的 pin 版本必须等于 executor_pin.json ----
    def test_t_qa_04_pin_version_mismatch_rejected(self):
        """两处都声明"我们用的执行器版本"，各说各话也不许过。

        2026-10-31 补：此前 executor_pin_version 只是必填字段，没人比对它与
        governance/executor_pin.json——bump 了 pin 忘了改基线，两边就永久分叉。
        """
        self.commit_baseline(pin={'commit_sha': 'd' * 40,
                                  'tree_sha': 'f' * 40})
        rc, out = self.check()
        self.assertNotEqual(rc, 0, 'pin 版本与基线不一致竟然通过')
        self.assertIn('executor_pin_version', out)

    def test_t_qa_04_pin_tree_mismatch_rejected(self):
        """tree 变了、commit 没变，同样要红。

        补这条是因为变异检验抓到一个逃逸：把 tree_sha 从比对字段里删掉，
        此前没有任何用例会发现——commit 对得上就能蒙混过关。
        """
        self.commit_baseline(pin={'commit_sha': 'c' * 40,
                                  'tree_sha': 'f' * 40})
        rc, out = self.check()
        self.assertEqual(rc, 0, out)            # 先确认起点是绿的
        # 同一次提交里改两个文件，避免漂移判定抢先
        write(self.tmp / 'governance' / 'executor_pin.json',
              json.dumps({'commit_sha': 'c' * 40, 'tree_sha': 'a' * 40}))
        # 基线必须真的产生内容变化：内容不变的话 git 不会为它记新提交，
        # `git log -1 -- baseline` 仍指向旧提交，漂移判定会抢在交叉检查前面
        write(self.tmp / 'governance' / 'quality_baseline.json',
              json.dumps(self.baseline(reviewed_at='2026-10-31T00:00:00+08:00')))
        self.git('add', '.')
        self.git('commit', '-qm', 'bump pin tree, forget baseline tree')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, 'tree 不一致竟然通过')
        self.assertIn('pinned_tree', out)

    def test_t_qa_04_pin_version_match_accepted(self):
        """正向对照：同步更新就应当通过，别做成永远拒绝的假门禁。"""
        self.commit_baseline(pin={'commit_sha': 'c' * 40,
                                  'tree_sha': 'f' * 40})
        rc, out = self.check()
        self.assertEqual(rc, 0, out)

    def test_t_qa_04_widened_exception_without_approval_rejected(self):
        self.commit_baseline()
        self.commit_change(
            baseline=self.baseline(exceptions=[{'id': 'EXC-99',
                                                'scope': 'everything'}]),
            gov='# v2\n', msg='widen exceptions')
        rc, out = self.check()
        self.assertNotEqual(rc, 0, '无审批扩大例外竟然通过')
        self.assertIn('widened', out)


if __name__ == '__main__':
    unittest.main()
