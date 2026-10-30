#!/usr/bin/env python3
"""T-VD-01：执行器 SHA pin 校验（控制 VD-01 / 规则 GOV-14）。

校验 governance/executor_pin.json 与控制面仓库 slow-is-fast/aasegs-gov-plane
的实际内容一致：
  1. commit_sha 必须在该仓库真实存在；
  2. 该 commit 的 tree_sha 必须与 pin 记录一致；
  3. 下载该 commit 的 tarball，按内容哈希方案重算 executor/ 哈希，必须与
     content_hash_sha256 一致；
  4. **本地 vendor 副本**（本仓库 `executor/`）按同一方案重算，也必须与 pin
     一致——数据面的用例跑的是这份副本，不是控制面那个 commit。

第 4 项是 2026-10-31 补上的。此前没有任何检查把"pin 指向的 commit"与
"我们实际 import 并测试的代码"绑在一起：有人本地改 `executor/gate.py`
放宽一条规则，数据面自己的用例照样全绿，pin 照样显示"我们用的是 X"。
那正是本规范一直在防的"文档声明替代机器判定"。

坑（实测）：Windows `core.autocrlf=true` 下工作区文件带 CRLF，而 tarball
里是 LF——不做换行规范化会产生**假失败**（实测 25 个文件里 2 个因此不一致，
规范化后逐字节相同）。这与 T-QA-04 那次"浅克隆导致假绿"是同一类陷阱的
镜像：一个是该红没红，一个是没红却红。

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


def content_hash(tar_bytes: bytes, source_path: str) -> tuple:
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
    return h.hexdigest(), dict(members)


def local_vendored_hash(root: Path, source_path: str):
    """本仓库 vendor 副本的内容哈希 + 逐文件差异（用于给可操作的报错）。

    换行统一规范化为 LF：见模块文档里的 autocrlf 坑。
    """
    base = root / source_path
    if not base.is_dir():
        sys.exit(f'FAIL(T-VD-01): 本地 vendor 目录不存在: {base}')
    members = []
    for f in sorted(base.rglob('*')):
        if not f.is_file() or '__pycache__' in f.parts:
            continue
        members.append((f.relative_to(root).as_posix(),
                        f.read_bytes().replace(b'\r\n', b'\n')))
    if not members:
        sys.exit(f'FAIL(T-VD-01): 本地 vendor 目录为空: {base}')
    h = hashlib.sha256()
    for rel, data in sorted(members):
        h.update(rel.encode() + b'\n' + data)
    return h.hexdigest(), dict(members)


def main() -> None:
    pin = json.loads(PIN.read_text(encoding='utf8'))
    repo, sha, tree = pin['source_repo'], pin['commit_sha'], pin['tree_sha']

    meta = json.loads(gh(f'repos/{repo}/commits/{sha}'))
    actual_tree = meta['commit']['tree']['sha']
    if actual_tree != tree:
        sys.exit(f'FAIL(T-VD-01): tree SHA mismatch: pin={tree} actual={actual_tree}')

    tar_bytes = gh(f'repos/{repo}/tarball/{sha}')
    actual_hash, remote_files = content_hash(tar_bytes, pin['source_path'])
    if actual_hash != pin['content_hash_sha256']:
        sys.exit(f'FAIL(T-VD-01): content hash mismatch: '
                 f'pin={pin["content_hash_sha256"]} actual={actual_hash}')

    # ---- 4. 本地 vendor 副本必须与同一个 pin 一致 ----
    root = PIN.parents[1]
    local_hash, local_files = local_vendored_hash(root, pin['source_path'])
    if local_hash != pin['content_hash_sha256']:
        only_remote = sorted(set(remote_files) - set(local_files))
        only_local = sorted(set(local_files) - set(remote_files))
        changed = sorted(r for r in set(remote_files) & set(local_files)
                         if remote_files[r] != local_files[r]
                         .replace(b'\r\n', b'\n'))
        detail = []
        if only_remote:
            detail.append(f'pin 里有、本地没有: {only_remote}')
        if only_local:
            detail.append(f'本地多出的文件: {only_local}')
        if changed:
            detail.append(f'内容不一致: {changed}')
        sys.exit('FAIL(T-VD-01): 本地 vendor 副本与 pin 不一致 '
                 f'(pin={pin["content_hash_sha256"][:12]} '
                 f'local={local_hash[:12]})；' + '；'.join(detail))

    print(f'PASS(T-VD-01): executor pin verified: {repo}@{sha[:12]} '
          f'tree={tree[:12]} content={actual_hash[:12]}')
    print(f'PASS(T-VD-01): 本地 vendor 副本一致（{len(local_files)} 个文件，'
          f'换行已规范化为 LF）')


if __name__ == '__main__':
    main()
