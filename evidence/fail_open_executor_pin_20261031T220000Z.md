# 放行路径体检证据：verify_executor_pin.py（T-VD-01）

- 日期：2026-10-31
- 控制：VD-01 / 规则 GOV-14
- 检查脚本：`scripts/verify_executor_pin.py`
- 守卫用例：`tests/test_executor_pin.py`（4 条）
- 变异体检结果：**3 处 fail-open 变异，0 逃逸**
- 关联：整体复核报告 §8 第 3 条"其余 9 项仍建议择机补"中，本检查是**唯一真缺口**（其余 8 项经核验已有负向守卫，见报告修订）

## 背景

`verify_executor_pin.py` 校验 `governance/executor_pin.json` 与控制面仓库
`slow-is-fast/aasegs-gov-plane` 实际内容一致，做 4 项失败关闭校验：

1. commit 的 `tree_sha` 必须与 pin 一致；
2. 下载 tarball 重算的 `content_hash_sha256` 必须与 pin 一致；
3. **本地 vendor 副本**（本仓库 `executor/`，数据面实际 import 的代码）的
   content hash 也必须与 pin 一致；
4. 任一不符即 `sys.exit` 非零（失败关闭）。

第 3 项是 2026-10-31 补上的防篡改锁：此前没有任何检查把"pin 指向的 commit"
与"我们实际跑的代码"绑在一起——有人本地放宽 `executor/` 里一条规则，
数据面用例照样全绿，pin 照样显示"我们用的是 X"。

**体检前缺口**：`tests/test_executor_negative.py` 测的是 `executor.*` 运行期
失败关闭逻辑，**完全不导入/测试 `verify_executor_pin.py` 这个校验脚本本身**。
因此上述 4 处失败关闭比对若被去掉（fail-open），无任何现存测试会抓到。
这正是本规范一直在防的"文档声明替代机器判定"。

## 方法

守卫用例用 `monkeypatch` 替换模块级 `gh()`（不发真实网络请求），由测试构造
回放的 commit/tarball 与本地 vendor 副本，覆盖三处失败关闭点各自"应拦截"
的场景：

- `test_happy_path_passes`：原始 pin + 一致本地副本 → 检查通过（含本地 vendor 一致性）
- `test_tree_mismatch_rejected`：pin 的 `tree_sha` 故意写错 → 必须非零退出（M1）
- `test_content_hash_mismatch_rejected`：回放的 tarball 内容被篡改 → 必须非零退出（M2）
- `test_local_vendor_mismatch_rejected`：本地 `executor/` 副本被篡改 → 必须非零退出（M3）

变异体检对 `scripts/verify_executor_pin.py` 注入 3 处 fail-open 变异（把对应
失败关闭比对改为 `if False:`），逐一运行守卫用例，确认每条变异都被对应
用例抓住（变异后目标用例 FAIL = 守卫抵抗住 fail-open）；若目标用例仍 PASS
则记为逃逸（放行路径没被看住，危险）。

## 变异注入与结果

| 变异 | 注入点（原行 → `if False:`） | 目标守卫用例 | 结果 |
|------|------------------------------|--------------|------|
| M1_tree | `if actual_tree != tree:` | test_tree_mismatch_rejected | CAUGHT |
| M2_content | `if actual_hash != pin['content_hash_sha256']:` | test_content_hash_mismatch_rejected | CAUGHT |
| M3_local | `if local_hash != pin['content_hash_sha256']:` | test_local_vendor_mismatch_rejected | CAUGHT |

**ESCAPED: []（0 逃逸）**。变异注入与还原用内存备份 + `try/finally` 还原，
并核对工作区 `git diff` 干净；harness 跑完即删，不进提交。

## 结论

`verify_executor_pin.py` 的 3 处失败关闭比对均被守卫用例覆盖，放行路径体检
通过。本检查从"无本地守卫"变为"有 3 条负向守卫 + 变异 0 逃逸"，整体复核
报告 §8 第 3 条所述"其余 9 项"中 8 项本已有守卫、仅本项为唯一真缺口的状态
已闭环。
