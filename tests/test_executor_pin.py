# -*- coding: utf-8 -*-
"""T-VD-PIN：executor SHA pin 校验（scripts/verify_executor_pin.py）的失败关闭路径守卫。

verify_executor_pin.py 做 4 项失败关闭校验（控制 VD-01 / 规则 GOV-14）：
  1. commit 的 tree SHA 必须与 pin 一致；
  2. tarball 重算的 content hash 必须与 pin 一致；
  3. 本地 vendor 副本（本仓库 executor/）的 content hash 必须与 pin 一致；
  4. 任一不符即非零退出（失败关闭）。
第 4 项是 2026-10-31 补上的防篡改锁：此前无任何检查把"pin 指向的 commit"
与"数据面实际 import 的代码"绑在一起。

本文件用 monkeypatch 替换 `gh`（不发网络请求）覆盖 tree / 远程内容 / 本地副本
三处失败关闭点，确认每处被篡改时检查都会非零退出。放行路径变异体检见
evidence/fail_open_executor_pin_20261031T220000Z.md。
"""
import io
import json
import gzip
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_executor_pin as vpin  # noqa: E402

REPO = 'slow-is-fast/aasegs-gov-plane'
REPO_NAME = REPO.split('/')[-1]
SHA = 'abc123def456abc123def456abc123def456abc1'
TREE = 'tree0000000000000000000000000000000000000001'


def _write_bytes(p: Path, text: str) -> None:
    # 显式 LF，避免 Windows core.autocrlf 把工作区刷成 CRLF 干扰哈希
    p.write_bytes(text.encode('utf-8'))


def _make_executor_dir(base: Path, *, modified=False):
    ed = base / 'executor'
    ed.mkdir(parents=True, exist_ok=True)
    _write_bytes(ed / 'f1.py', 'def a():\n    return 1\n' + ('# tampered\n' if modified else ''))
    _write_bytes(ed / 'f2.py', 'def b():\n    return 2\n')
    return ed


def _tarball_bytes(root: Path, source_path: str = 'executor') -> bytes:
    """按 verify_executor_pin.content_hash 期望的命名重建 gz tarball。"""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb') as gz:
        with tarfile.open(fileobj=gz, mode='w') as tf:
            for f in sorted((root / source_path).rglob('*')):
                if not f.is_file() or '__pycache__' in f.parts:
                    continue
                rel = f.relative_to(root).as_posix()  # 'executor/f1.py'
                data = f.read_bytes()
                ti = tarfile.TarInfo(name=f'{REPO_NAME}-{SHA}/{rel}')
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


class ExecutorPinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='aasegs-pin-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ed = _make_executor_dir(self.tmp)  # 原始本地副本
        # 真实 content hash（来自原始本地副本）
        self.h_orig, _ = vpin.local_vendored_hash(self.tmp, 'executor')
        self.pin_path = self.tmp / 'governance' / 'executor_pin.json'
        self.pin_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_pin(self, *, wrong_tree=False, content_hash=None):
        pin = {
            'source_repo': REPO,
            'commit_sha': SHA,
            'tree_sha': ('WRONG' * 10) if wrong_tree else TREE,
            'source_path': 'executor',
            'content_hash_sha256': content_hash or self.h_orig,
        }
        self.pin_path.write_text(json.dumps(pin), encoding='utf-8')

    def _make_gh(self, blob: bytes):
        def fake_gh(*args):
            a = ' '.join(args)
            if 'commits/' in a:
                return json.dumps({'commit': {'tree': {'sha': TREE}}}).encode()
            if 'tarball/' in a:
                return blob
            raise AssertionError(f'unexpected gh call: {a}')
        return fake_gh

    def _run(self, *, wrong_tree=False, tamper_tarball=False, tamper_local=False):
        # tarball 必须在篡改本地副本之前构建，才能分别隔离各失败关闭点
        if tamper_tarball:
            mod = Path(tempfile.mkdtemp(prefix='aasegs-pin-mod-'))
            _make_executor_dir(mod, modified=True)
            blob = _tarball_bytes(mod, 'executor')
            shutil.rmtree(mod, True)
        else:
            blob = _tarball_bytes(self.tmp, 'executor')
        self._write_pin(wrong_tree=wrong_tree)
        if tamper_local:
            _write_bytes(self.ed / 'f1.py', 'def a():\n    return 999\n')
        vpin.PIN = self.pin_path
        vpin.gh = self._make_gh(blob)
        try:
            vpin.main()
            return 0
        except SystemExit as e:
            return e.code if isinstance(e.code, int) else 1

    def test_happy_path_passes(self):
        rc = self._run()
        self.assertEqual(rc, 0, '原始 pin + 一致本地副本应当通过（含本地 vendor 一致性）')

    def test_tree_mismatch_rejected(self):
        rc = self._run(wrong_tree=True)
        self.assertNotEqual(rc, 0, 'tree SHA 不符应当被拦截（M1 失败关闭点）')

    def test_content_hash_mismatch_rejected(self):
        rc = self._run(tamper_tarball=True)
        self.assertNotEqual(rc, 0, '远程 content hash 不符应当被拦截（M2 失败关闭点）')

    def test_local_vendor_mismatch_rejected(self):
        rc = self._run(tamper_local=True)
        self.assertNotEqual(rc, 0, '本地 vendor 副本被篡改应当被拦截（M3 失败关闭点）')


if __name__ == '__main__':
    unittest.main()
