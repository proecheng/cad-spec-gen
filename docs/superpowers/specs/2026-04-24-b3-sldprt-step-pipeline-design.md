# B3 — sldprt→STEP 转换流水线修复 设计规格

**版本**：v0.1  
**日期**：2026-04-24  
**分支**：feat/b3-sldprt-step-pipeline

---

## 1. 背景与根因诊断

### 1.1 现象

`sw-warmup` 运行后 STEP 缓存为 0 件（2026-04-14 错误日志：全部 FAIL）。

### 1.2 Spike 结论（B3-1，2026-04-24 实测）

- 直接调用 `sw_convert_worker` 转换 GB/bearing + GB/washers 件 → exit 0，STEP 文件有效（346KB/60KB，`ISO-10303-21` 头正确）
- **排除原因 2**（OpenDoc6 因 Add-in 未激活失败）
- **排除原因 3**（SW Premium 授权层拒绝）
- **根因：SW 未运行时 COM 激活快速失败 → 熔断器**：错误日志时序显示前 3 次失败各耗时 ~645ms（非 20s 超时；645ms = subprocess 启动 ~200ms + COM 激活快速失败 ~400ms），第 4 条起 sub-ms 瞬间返回——这是熔断器开启后 `circuit_breaker_open` 路径的典型特征（`CIRCUIT_BREAKER_THRESHOLD = 3`）。COM 激活具体错误码无法从错误日志还原（日志仅记录"FAIL"，不含 worker stderr），但 2026-04-24 spike 在 SW 运行时成功排除授权/路径问题；SW 未运行是最可能的触发条件

### 1.3 额外发现

`sw_convert_worker.py` 中 `app.CloseDoc(model.GetTitle())` 在某些 SW COM 版本抛 `TypeError("'str' object is not callable")`（`GetTitle()` 返回值类型不符）。异常被 `finally` 吞掉，不影响 STEP 产出，但属于潜在静默 bug。

---

## 2. 改动范围

### 2.1 `adapters/solidworks/sw_convert_worker.py`

**改动 B-14：`FrameState = 0`**

在 `app.Visible = False` + `app.UserControl = False` 后新增：
```python
app.FrameState = 0  # swWindowMinimized，抑制 Toolbox modal 对话框
```
原因：Toolbox 零件打开时弹出"select size and configuration"模态对话框走 `ISldWorks::SendMsgToUser2` 路径，不被 preference toggle 捕获，窗口最小化是可靠抑制方式。

**改动 B-15：`Dispatch` → `DispatchEx`**

```python
# 旧（worker 顶部 import）
from win32com.client import VARIANT, Dispatch
# 新（合并替换，删除 Dispatch，加入 DispatchEx）
from win32com.client import VARIANT, DispatchEx

# 旧（调用处）
app = Dispatch("SldWorks.Application")
# 新
app = DispatchEx("SldWorks.Application")
```
原因：强制新 COM 进程实例，避免多个 worker subprocess 竞争同一 SW 会话。

**改动 CloseDoc 修复**

```python
# 旧
app.CloseDoc(model.GetTitle())
# 新
app.CloseDoc(model.GetPathName())
```
原因：`GetPathName()` 返回文件绝对路径字符串，与 SW API 文档一致，不依赖 `GetTitle()` 的返回类型变体。

`exit_code` 契约不变：0=成功 / 2=OpenDoc6 失败 / 3=SaveAs3 失败 / 4=未预期异常 / 64=参数错误。

### 2.2 `tools/sw_warmup.py`

**改动：SW 进程检测（`_check_preflight`）**

在末尾 `return True, ""` 前插入（`psutil` 在函数体内局部 import，与 `msvcrt`/`fcntl` 惯例一致，避免顶层 import 在非 SW 环境失败）：
```python
import psutil  # 局部 import
sw_running = any(
    p.name().upper() == "SLDWORKS.EXE"
    for p in psutil.process_iter(["name"])
)
if not sw_running:
    return False, (
        "SolidWorks 未运行；请先打开 SolidWorks，"
        "再运行 sw-warmup（COM 转换需要 SW 进程已就绪）"
    )
```
检测顺序：安装检测 → 版本检测 → pywin32 检测 → toolbox_dir 检测 → **SW 进程检测** → return True。

失败时 `exit 2`（与"未安装 SW"同码，`_print_preflight_failure` 统一格式打印）。

`psutil` 已在项目依赖中（`sw_preflight` 模块已用到），无新依赖。

**改动：`--smoke-test` 标志**

argparse 新增 `--smoke-test` 布尔标志。`run_sw_warmup` 在持锁后、进入 `_run_warmup_locked` 前检测：

```python
if args.smoke_test:
    return _run_smoke_test(args)
```

`_run_smoke_test(args)` 独立函数流程（在持锁内调用，preflight 在此函数内独立调一次，不依赖外层）：
1. 调 `_check_preflight()`（含 SW 进程检测），失败则直接返回 exit 2
2. 从 Toolbox index 取第一个 GB/bearing 件作为已知好件
3. 转换到 `tempfile.mkdtemp()` 临时目录
4. 打印结果 + 删除临时文件：
   - 成功 → `[sw-warmup] smoke-test PASS — STEP 文件 {size}KB` → exit 0
   - 失败 → `[sw-warmup] smoke-test FAIL — {session.last_convert_diagnostics['stderr_tail']}` → exit 2

---

## 3. 不在本次范围内

- **B-16 ShowConfiguration2**：需要 BOM 零件尺寸反查 Toolbox configuration 名，依赖 resolver 层改动，留 Track B 后续
- **超时参数调整**：SW 进程检测已解决根因，20s timeout 对 SW 已运行场景足够，不改
- **`--smoke-test` 纳入 CI**：本机 smoke only，不加 CI（需要真机 SW）

---

## 4. 测试策略

| 测试 | 文件 | 覆盖点 |
|------|------|--------|
| `test_sw_convert_worker_close_doc` | `tests/test_sw_convert_worker.py` | mock `model.GetPathName()` 返回字符串，验证 `CloseDoc` 入参正确；同时更新 `_patch_com` helper 将 `Dispatch` mock 改为 `DispatchEx` |
| `test_sw_preflight_sw_not_running` | `tests/test_sw_warmup.py` | mock `psutil.process_iter` 返回空 → preflight 返回 False + 含"SolidWorks 未运行"文案 |
| `test_sw_preflight_sw_running` | `tests/test_sw_warmup.py` | mock `psutil.process_iter` 返回含 `SLDWORKS.EXE` 进程 → preflight 通过 |
| `test_smoke_test_pass` | `tests/test_sw_warmup.py` | mock `get_session().convert_sldprt_to_step` 返回 True → exit 0 + PASS 文案 |
| `test_smoke_test_fail` | `tests/test_sw_warmup.py` | mock 返回 False → exit 2 + FAIL 文案 |
| 本机手工验收 | — | `sw-warmup --smoke-test`（SW 已开）→ exit 0 + STEP >1KB |

所有单元测试加 `@pytest.mark.requires_windows`（`psutil.process_iter` + `SLDWORKS.EXE` 在 Linux CI 无意义）。

---

## 5. 验收标准

1. `sw-warmup --smoke-test` 在 SW 已开本机 → exit 0，打印 `smoke-test PASS`
2. SW 未开时运行 `sw-warmup`（任何 flag 组合，`--dry-run` 也在内）→ exit 2，打印含"SolidWorks 未运行"的提示
3. `sw_convert_worker` 单件转换无 `CloseDoc TypeError` 警告
4. 全套单元测试通过（Linux + Windows CI）

---

## 6. 实施任务表

| Task | 内容 | 估时 |
|------|------|------|
| B3-0 | 新建分支 `feat/b3-sldprt-step-pipeline` | 5min |
| B3-1 | worker：DispatchEx + FrameState=0 + CloseDoc fix + 单元测试 | 30min |
| B3-2 | warmup：SW 进程检测 preflight + 单元测试 | 20min |
| B3-3 | warmup：`--smoke-test` 标志 + `_run_smoke_test` + 单元测试 | 30min |
| B3-4 | 本机手工验收：`sw-warmup --smoke-test` exit 0 | 10min |
| B3-5 | PR + CI 通过 + merge + v2.16.0 | 15min |
