#!/usr/bin/env python3
"""T-VD-01：执行器 SHA pin 校验（控制 VD-01 / 规则 GOV-14）。

校验 governance/executor_pin.json 与控制面仓库 slow-is-fast/aasegs-gov-plane
的实际内容一致：
  1. commit_sha 必须在该仓库真实存在；
  2. 该 commit 的 tree_sha 必须与 pin 记录一致；
  3. 下载该 commit 的 tarball，按内容哈希方案重算 executor/ 哈希，必须与
     content_hash_sha256 一致。

任何一项不符即非零退出（失败关闭）。需要已认证的 `gh` CLI（CI 中由
GITHUB_TOKEN 提供）。
"""
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

PIN = Path(__file__).resolve().parents[1] / 'governance' / 'executor_pin.json'


def gh(*args: str) -> bytes:
    r = subprocess.run(['gh', 'api', *args], capture_output=True)
    if r.returncode != 0:
        sys.exit(f'FAIL(T-VD-01): gh api {" ".join(args)} -> {r.stderr.decode()[:300]}')
    return r.stdout


def content_hash(tar_bytes: bytes, source_path: str) -> str:
    h = hashlib.sha256()
    with tarfile.open(fileobj=BytesIO(tar_bytes), mode='r:gz') as tf:
        members = []
        for m in tf.getmembers():
            if not m.isfile():
                continue
            # tarball 顶层目录形如 <repo>-<sha>/，剥离后得到 executor/xxx
            rel = m.name.split('/', 1)[1] if '/' in m.name else m.name
            if rel.startswith(source_path):
                members.append((rel, tf.extractfile(m).read()))
    if not members:
        sys.exit(f'FAIL(T-VD-01): tarball 中未找到 {source_path}')
    for rel, data in sorted(members):
        h.update(rel.encode() + b'\n' + data)
    return h.hexdigest()


def main() -> None:
    pin = json.loads(PIN.read_text(encoding='utf8'))
    repo, sha, tree = pin['source_repo'], pin['commit_sha'], pin['tree_sha']

    meta = json.loads(gh(f'repos/{repo}/commits/{sha}'))
    actual_tree = meta['commit']['tree']['sha']
    if actual_tree != tree:
        sys.exit(f'FAIL(T-VD-01): tree SHA mismatch: pin={tree} actual={actual_tree}')

    tar_bytes = gh(f'repos/{repo}/tarball/{sha}')
    actual_hash = content_hash(tar_bytes, pin['source_path'])
    if actual_hash != pin['content_hash_sha256']:
        sys.exit(f'FAIL(T-VD-01): content hash mismatch: '
                 f'pin={pin["content_hash_sha256"]} actual={actual_hash}')

    print(f'PASS(T-VD-01): executor pin verified: {repo}@{sha[:12]} '
          f'tree={tree[:12]} content={actual_hash[:12]}')


if __name__ == '__main__':
    main()
