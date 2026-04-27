# sw_config_broker §11 技术债清理 — M-2 + M-4 设计 spec

- **rev**: 5（user feedback "测试越详尽越好" — 测试覆盖大扩 + CI gate）
- **rev 4 → rev 5 修订记录**（user 反思 "前 4 轮 review 修复反复不收敛 → 测试覆盖不够 anchor 实施"，2026-04-27）：
  - **核心决策**：扩测试矩阵从 31 → ~66，覆盖率从隐式 → CI 强制 ≥95%。**让下次 reviewer 抓不到漏，PR review → merge 一次到位**
  - **A 修复（每个 invariant 直接测试）**：14 invariants 中现有 7 个有隐式覆盖，新加 7 个直接断言测试到 §7.1/§7.2/§7.3
  - **B 修复（每个 Edge case 补齐测试）**：12 Edge case 现有 ~7 个有测试，补 5 个让每条 Edge 都有 1 测试
  - **C 修复（集成测试）**：新增 §7.4 broker → worker → cache 真实调用链测试（mock 仅 subprocess.run，broker/cache.py 走真实代码路径）= +8 集成测试
  - **D 修复（Negative testing 矩阵）**：新增 §7.5 worker 失败 × broker 状态组合 = +10 negative case 测试
  - **F 修复（端到端用户场景）**：新增 §7.6 5 个用户视角端到端测试（首次装 SW / 升级期混跑 / cache 损坏 / 双 SW / 大 BOM 100 件）
  - **H 修复（覆盖率 enforce）**：新增 §12 CI gate — `pyproject.toml` 加 pytest-cov 配置，CI workflow 加 `pytest --cov-fail-under=95`，spec 加硬约束"每个新代码行 ≥1 测试覆盖"
  - **附带 §7.7 (新)**：Invariant ↔ 测试 一一对应映射表，防 reviewer 报告"未测的 invariant"
- **rev**: 4（4 路 subagent 敌对审查后**缩 scope** — 砍 transient cache + 修 F-3 数值 + A1 + 综合 fix）
- **rev 3 → rev 4 修订记录**（4 reviewer 共抓 5 Critical / 13 Important / 12 Minor，集中在 transient cache，2026-04-27）：
  - **核心决策：砍掉 short-TTL transient cache 整套**（rev 3 引入的复杂度产生了 3 Critical + 7 Important 问题，且 multiprocessing 失效让重试风暴防御本身存疑）。M-4 退化到 rev 2 行为：rc=3/4/未知/Timeout/OSError 都"不 cache 就 return []"。"BOM loop 同 sldprt 多次调用触发 N×30s SW boot"作为已知 limitation 推迟到 §11 followup（实际频率低 — codegen 一次跑通 prewarm 后正常路径都走 L1 hit）
  - **F-3 修复（reality checker 用真 SW SDK 文档校准）**：swFileLoadError 数值表全部修正——`swFutureVersion=8` (was 64) / `swApplicationBusy=8192` (was 4096) / `swLowResourceError=16384` (was 256) / `swFileWithSameTitleAlreadyOpen=4096` (was 128)。`_TRANSIENT_OPENDOC_ERRORS = {4096, 8192, 16384}`（原 {128, 256, 4096} 全错）；plan task 0 必须用 `from win32com.client import constants` 校准
  - **A1 修复（hostile reviewer）**：worker `_run_batch_mode` 顶部 ImportError / DispatchEx 失败改为输出 `[{"path": p, "configs": [], "exit_code": EXIT_TRANSIENT} for p in sldprt_list] + rc=0` 让 broker 走 entry-level 分流而不是整批 fallthrough；防 SW boot 故障下 M-4 prewarm 失效
  - **F-1 / E3 修复（reality+consistency reviewer）**：I9 不变性描述与 §3.3 rev 3 C2 实现矛盾（I9 说"默认 0"，§3.3 改成"rc is None → continue"）— 改 I9 为"旧 worker batch 缺字段 → entries 整批跳过 + log.warning，broker 不抛"
  - **F-2 修复（reality reviewer）**：§3.4 cache.py 改动需新增 `import sys` 顶部 import；明确登记到 §8 文件清单
  - **B2 修复（consistency reviewer）**：§3.1.2 worker 端常量表错列 `EXIT_LEGACY` — 删除 worker 端 EXIT_LEGACY 行，仅保留 broker 端 `WORKER_EXIT_LEGACY`
  - **A1-consistency / F1 修复**：§7.2 实际 16 测试 vs 多处声称 17 → 砍 transient cache 后测试矩阵重算（worker 12 + broker ~12 + cache 4 = ~28），统一所有数字
  - **A3 LOC 修复**：用真实加和；砍 transient cache 后 LOC 大幅下降
  - **D2 修复**：§7.3 后段"测试增量说明"位置归属错 — 移到 §7.2 末尾
  - **F-4 修复**：§6 Edge 4 `_install_fake_win32com` 位置错 — 改为 `_patch_com` helper（在 `tests/test_sw_convert_worker.py` L34）
  - **F-5 修复**：§3.4 caller 简化表 L628 措辞改为"无需主动改动；M-2 后 save 自愈，外层 OSError 不再可能因 save 触发"
  - **4 条 invariant 缺测试补**：I1 prewarm 不抛 / I2 mtime 失效 / I5 (砍后变 I_legacy_no_pollute) / I8 schema 兼容 — 各加 1 个对应测试
  - **保留**：rev 3 的 banner 安抚文案 (I3) / dead code 注 (M4) / 双边维护 maintainer note (M5) — 这 3 处 rev 3 修复正确，无需改
- **rev 2 → rev 3 修订记录**（user 反向影响审查触发，2026-04-27 — 已部分被 rev 4 撤销）：
  - **C1 修复（重试风暴防御）**：rev 2 的 `rc=3 → 不 cache + 重试` 在 BOM loop × 多次调用同 sldprt 场景下会触发 N × 30s SW boot 浪费。改为 **short-TTL cache**（60s 内同 process 同 sldprt 复用 `[]`，超 60s 失效允许重试）— 见 §3.2 + §4 Path 6 + I13 + Edge 11
  - **C2 修复（旧 worker batch 兼容真兼容）**：rev 2 `entry.get("exit_code", WORKER_EXIT_OK)` 让旧 worker 的 catch-all `configs=[]` 被当 success 永久 cache 污染（M-4 在升级期窗口完全失效）。改为 **缺字段当 invalidate signal**（不写 entries）— 见 §3.3 改写 + 测试断言反转
  - **I3 修复（banner 信息密度）**：banner 加安抚文案"本次 codegen 不受影响；下次 prewarm 仍会自动重试"防止用户误以为 hard fail
  - **M4 标注（dead code 防御性）**：§3.1.6 `try: import pythoncom / except ImportError: pass` 加注释说明"防御 worker 启动后 pythoncom 异常 unload 边角，几乎不触发"
  - **M5 标注（worker/broker 常量双边维护）**：§10 加 maintainer note "worker `EXIT_*` 改值必同步 broker `WORKER_EXIT_*`"
- **rev 1 → rev 2 修订记录**（user-review drift 触发，2026-04-27）：
  - **Drift 1 修复**：明确 worker 现状已有 4 退出码合约（0/2/4/64），`rc=4` 在本 PR 后**废弃**并分流到 `rc=2/rc=3`；broker 端为兼容旧 worker 进程混跑场景加 `rc=4 → transient` 兜底
  - **Drift 2 修复**：worker 改造点是**重写 `_list_configs` 内部 except 映射**（L75-95），不是新建 `main()` try/except；伪代码位置错误已修
  - **Drift 3 修复**：`pythoncom.com_error` 在 OpenDoc6 路径上被 `RuntimeError("OpenDoc6 errors=N ...")` 包装，**hresult 分类只对 DispatchEx / GetConfigurationNames 路径有效**；OpenDoc6 路径改用**带字段的 `OpenDocFailure(RuntimeError)` 子类异常**（用户 review 选 B 方案：改 primitive 而不是字符串解析），按 `errors: int` 数值分流；新增"swFileLoadError 数值表"作分类基底
  - **Drift 4 修复**：`_run_batch_mode` for 循环 except 改调共享 `_classify_worker_exception(e)` 函数，单件 + batch 共享分类逻辑（DRY）；batch stdout schema 加 `exit_code` 字段
  - **Drift 5 修复**：`tests/test_sw_config_lists_cache.py` 已存在，§7.3 措辞改 "扩展现有 `TestSaveCache` 类"
- **scope**: 仅 M-2（save 异常下沉）+ M-4（worker rc 合约 + transient/terminal 分类）
- **依赖 spec**：
  - `2026-04-26-sw-toolbox-config-list-cache-design.md` §11（M-2 / M-4 follow-up 登记）
  - `2026-04-25-sw-toolbox-llm-config-broker-design.md` §5.3 invariant 1（prewarm 永不抛打断 codegen）
  - `2026-04-26-sw-config-broker-i2-i3-fix-design.md` §3（banner 风格 — 撞锁 banner 同模板）
- **依赖 memory**：
  - `project_north_star.md`（北极星 5 gate）
  - `user_simplicity_and_accuracy.md`（简单+准确，能不加 CLI 不加）
  - `feedback_external_subsystem_safety_valve.md`（COM 调用安全阀已在 broker 入口）

---

## §1 动机

PR #19 self-review 登记 4 Important + 7 Minor follow-up；I-2 + I-3 已在 v2.20.0 (PR #20) 关闭，剩余 7 项推迟到本 PR 与未来。

本 PR 优先 M-2 + M-4 — memory `project_current_status.md` 标定的两项「中优先」技术债：

- **M-2 `_save_config_lists_cache` 异常上抛** — 任何 `OSError` / `PermissionError` 会冒泡到 caller。`broker.py` L570-580 已在 prewarm envelope save 处加 caller-side try/except（I-2 修复时引入），但其他 callsite（L628 + 未来扩展）仍裸调用 → 形态上不对称（`_load_config_lists_cache` L72-75 已自愈，`_save_*` 未自愈）。
- **M-4 transient COM 失败永久缓存** — worker 任何失败（subprocess 超时 / rc!=0 / JSON parse 错）都被 broker 缓存 `[]` 到 in-process L2（broker.py L514/522/531）。一旦缓存 `[]`，同 sldprt 同 process 内永不重试 → 单次 COM hiccup 把整 BOM 这件子永久打废。

两项都是**北极星「稳定可靠 / 照片级」边角缺陷**：当前 5 gate 全过，但留这两根刺，下次外部环境波动（磁盘临时满 / SW license 服务器抖动）会暴露用户面影响。

---

## §2 Scope

| 范围内 ✓ | 范围外 ✗ |
|---------|---------|
| M-2 `_save_config_lists_cache` 异常下沉 + banner | M-1 `fsync` 缺失（power-loss 语义改动，独立 PR） |
| M-4 worker 退出码合约（rc=0/2/3） | M-3 `_PROJECT_ROOT_FOR_WORKER` import 不对称（仅文档） |
| broker rc 分流（terminal cache / transient 不 cache） | M-5 prewarm timeout 缩放公式（独立性能调优） |
| prewarm batch 路径 entry-level rc 分流 | M-6 `detect_solidworks` 重复 import（reload 兼容讨论） |
| 单元测试（worker / broker / cache 三端） | M-7 `INVALIDATION_REASONS` frozenset 校验删除 |
| | I-4 mtime+size collision（罕见边界，文档化即可） |
| | 新 CLI flag — 用户不需要，靠自动重试机制 |

**北极星 gate 检查**：

| Gate | 是否影响 | 说明 |
|------|---------|------|
| 零配置 | 中性 | 不引入新配置项 / 新 env / 新 CLI flag |
| 稳定可靠 | **改善 ↑** | M-2 防 save 异常打断 caller；M-4 防 transient 污染 cache |
| 结果准确 | **改善 ↑** | M-4 防 BOM 单件被单次 hiccup 永久打废 → 渲染时不会缺零件 |
| SW 装即用 | 不变 | 兼容 v2.20.0 cache schema v1（不需 schema bump） |
| 傻瓜式 | 中性 | M-2 banner 是用户面新增物，但仅在持续失败时出现，对齐 I-3 锁等待 banner 风格 |

---

## §3 设计决策

### §3.1 Worker 退出码合约

#### §3.1.1 现状基线（rev 2 修 Drift 1）

`adapters/solidworks/sw_list_configs_worker.py` L6-15 已有 4 退出码合约：

```
0  成功
2  OpenDoc6 errors 非 0 或 null model（仅单件模式）
4  任何未预期 Exception（仅单件模式）  ← 本 PR 废弃，分流到 rc=2/3
64 命令行参数错误 / batch JSON 错（不变）
```

batch 路径（`_run_batch_mode` L98-153）现状：for 循环 `except Exception` catch-all 设 `configs=[]`，**不区分异常类型，整 batch 始终 rc=0**。

#### §3.1.2 rev 4 目标合约（worker 端常量）

```
EXIT_OK        = 0  成功（stdout 含 configs JSON / batch JSON list）
EXIT_TERMINAL  = 2  重试仍失败（OpenDoc6 errors 是终态 / SLDPRT 损坏 / pywin32 未装 / 已知 terminal COM hresult）
EXIT_TRANSIENT = 3  重试可能成功（OpenDoc6 errors 是瞬时态 / DispatchEx COM 暂断 / 未识别异常兜底）
EXIT_USAGE     = 64 命令行参数错误（不变）
```

> **rev 4 注（B2 修复）**：worker 端**不**定义 `EXIT_LEGACY` — rc=4 是"旧 worker 输出"的语义，仅 broker 端需要 `WORKER_EXIT_LEGACY=4` 兜底（见 §3.2.1）。本 PR 同时改 worker，所以 worker 端不会再产出 rc=4；rc=4 仅在升级期混跑场景由 broker 防御性识别。

#### §3.1.3 新增子类异常 `OpenDocFailure`（修 Drift 3 — user 选 B）

`pythoncom.com_error` 在 OpenDoc6 路径**根本不会被抛**——`_open_doc_get_configs` (L23-47) 已把 OpenDoc6 errors 包成 `RuntimeError("OpenDoc6 errors=N ...")`。rev 2 改 primitive 让分类按字段走，避免脆弱字符串解析：

```python
# adapters/solidworks/sw_list_configs_worker.py（新增）

class OpenDocFailure(RuntimeError):
    """OpenDoc6 失败带结构化字段；分类按 errors 数值走，不解析字符串。"""
    def __init__(self, errors: int, warnings: int, model_was_null: bool):
        self.errors = errors
        self.warnings = warnings
        self.model_was_null = model_was_null
        super().__init__(
            f"OpenDoc6 errors={errors} warnings={warnings} "
            f"model={'NULL' if model_was_null else 'OK'}"
        )
```

`_open_doc_get_configs` L33-39 失败分支替换为 `raise OpenDocFailure(err_var.value, warn_var.value, model is None)`。

**向后兼容**：`OpenDocFailure(RuntimeError)` 子类，所有现有 `except RuntimeError` 不破。

#### §3.1.4 swFileLoadError 数值映射表（rev 4 F-3 用真 SW SDK 文档校准）

来源：SolidWorks SDK `swFileLoadError_e` 枚举（SOLIDWORKS API Help 2021/2022 — bitmask 枚举值）。

| errors 值 | 名称 | 分类 | 理由 |
|----------|------|------|------|
| 1 | `swGenericError` | terminal | 通用未知错，重试不变 |
| 2 | `swFileNotFoundError` | terminal | 文件不存在 |
| 8 | `swFutureVersion`（SLDPRT 比 SW 版本新） | terminal | 升级前重试不会变 |
| 32 | `swInvalidFileTypeError` | terminal | 文件类型错 |
| 64 | `swFileNotFoundWarning` | terminal | 同 2 |
| 128 | `swNoDisplayData` | terminal | LDR 显示数据缺失 |
| 1024 | `swFileRequiresRepair` | terminal | 需手动修复 |
| **4096** | `swFileWithSameTitleAlreadyOpen` | **transient** | 同名文件已开（典型 UI 残留 / 并发场景） |
| **8192** | `swApplicationBusy` | **transient** | SW 进程忙（典型 boot 中） |
| **16384** | `swLowResourceError` | **transient** | 资源不足 / 内存压力 |
| **null model（errors=0）** | `model is None` 但 errors=0 | terminal | 罕见边角，归 terminal 保守 |

**`_TRANSIENT_OPENDOC_ERRORS` 集合**：`{4096, 8192, 16384}`（未来扩充走单独 PR）。

> **🔴 实施前强制校准（rev 4 F-3 修复）**：上表数值取自公开 SW SDK 2021/2022 文档；plan task 0 必须在本机 SW 装好的环境用 `from win32com.client import constants` 校准实际枚举值（不同 SW 版本可能微调 bitmask 位）。校准代码：
>
> ```python
> from win32com.client import constants
> _TRANSIENT_OPENDOC_ERRORS = frozenset({
>     constants.swFileLoadError_FileWithSameTitleAlreadyOpen,
>     constants.swFileLoadError_ApplicationBusy,
>     constants.swFileLoadError_LowResourceError,
> })
> ```
>
> 若 `pywin32` constants 不可读（极罕见），保留裸数字 + 注释枚举名 + 在 `tests/test_sw_list_configs_worker.py` 加一个 SDK 校准 fixture 验证数字与本机 SW 实际匹配。

#### §3.1.5 已知 transient COM hresult（DispatchEx / GetConfigurationNames 路径）

`pythoncom.com_error` 仅在 OpenDoc6 之外的 COM 调用路径有效（`DispatchEx("SldWorks.Application")` / `model.ConfigurationManager.GetConfigurationNames()` / `app.CloseDoc(...)`）。

| HRESULT | 名称 | 描述 |
|---------|------|------|
| `-2147023170` | `RPC_E_DISCONNECTED` | RPC 服务器不可用（COM 服务器进程退出） |
| `-2147418113` | `E_FAIL` | 通用失败 — 保守归 transient |
| `-2147023174` | `RPC_S_CALL_FAILED` | 调用瞬时中断 |

**`_TRANSIENT_COM_HRESULTS` 集合**：上表 3 个 HRESULT 值（未来扩充走单独 PR）。

#### §3.1.6 共享分类函数 `_classify_worker_exception`（修 Drift 4 — DRY）

```python
# adapters/solidworks/sw_list_configs_worker.py（新增）

EXIT_OK = 0
EXIT_TERMINAL = 2
EXIT_TRANSIENT = 3
EXIT_USAGE = 64

_TRANSIENT_OPENDOC_ERRORS: frozenset[int] = frozenset({4096, 8192, 16384})  # spec §3.1.4 (rev 4 F-3)
_TRANSIENT_COM_HRESULTS: frozenset[int] = frozenset({                    # spec §3.1.5
    -2147023170, -2147418113, -2147023174,
})

def _classify_worker_exception(e: BaseException) -> int:
    """worker 端异常分类的唯一入口；单件 + batch 共享调用（DRY）。

    返回 EXIT_TERMINAL (2) / EXIT_TRANSIENT (3)。
    KeyboardInterrupt / SystemExit 不应进入此函数 — caller 必须先 raise。
    """
    if isinstance(e, OpenDocFailure):
        if e.errors in _TRANSIENT_OPENDOC_ERRORS:
            return EXIT_TRANSIENT
        return EXIT_TERMINAL  # 含未识别 errors 值 + null model 边角
    if isinstance(e, ImportError):
        return EXIT_TERMINAL  # pywin32 没装是部署问题，重试不会变
    # pythoncom.com_error 仅在 worker 已 import pythoncom 后才能 isinstance 检查
    try:
        import pythoncom
        if isinstance(e, pythoncom.com_error):
            hresult = getattr(e, "hresult", None) or (e.args[0] if e.args else None)
            return EXIT_TRANSIENT if hresult in _TRANSIENT_COM_HRESULTS else EXIT_TERMINAL
    except ImportError:
        # rev 3 M4 注：理论 dead code — _list_configs_returning 已 import pythoncom，
        # 此处 import 不会失败。保留作防御：worker 启动后 pythoncom 异常 unload 边角，
        # 或者 _classify_worker_exception 被 _list_configs 路径以外的 caller 误调
        # （现状无此 caller，但函数应自完备）。
        pass
    # 兜底：未识别 Exception 归 transient（避免 worker 自身 bug 永久污染 cache）
    return EXIT_TRANSIENT
```

**「双向保守」语义注释**：COM 未识别 hresult 归 terminal（COM 错根因在 SW/SLDPRT 上）；非 COM 未识别 Exception 归 transient（典型来自 worker 自身 bug，需保留重试机会防 cache 永久污染）。两个保守方向相反但各自域内合理。

#### §3.1.7 `_list_configs` 重写（修 Drift 2）

替换 L75-95 现有 3 层嵌套 try：

```python
def _list_configs(sldprt_path: str) -> int:
    """单件 CLI 模式入口：返 exit code，stdout 打印 JSON list of strings."""
    try:
        names = _list_configs_returning(sldprt_path)
        print(json.dumps(names, ensure_ascii=False))
        return EXIT_OK
    except (KeyboardInterrupt, SystemExit):
        raise  # 永不当作可恢复错误吞掉
    except BaseException as e:
        print(f"worker: {type(e).__name__}: {e!r}", file=sys.stderr)
        return _classify_worker_exception(e)
```

`_list_configs_returning` (L50-72) 内部 try/except 不变（CoInitialize/CoUninitialize 必须有 finally）；其抛出的所有异常（含 `pythoncom.com_error` from DispatchEx / `OpenDocFailure` from `_open_doc_get_configs` / `ImportError` from win32com）都被 `_list_configs` 捕获按 `_classify_worker_exception` 分流。

#### §3.1.8 `_run_batch_mode` 改造（修 Drift 4 + rev 4 A1 修复）

##### §3.1.8.1 顶部 boot fail 路径（rev 4 A1 修复）

替换 L118-123 + L125-127 顶部 import + DispatchEx 失败分支：

```python
# 原 L118-123：ImportError 直接 return 4
# 原 L125-127：DispatchEx 失败抛到外层未捕获

# rev 4 改：顶部 boot fail 也走 entry-level 分流（防 broker 整批 fallthrough）
try:
    import pythoncom
    from win32com.client import DispatchEx
except ImportError as e:
    print(f"worker --batch: pywin32 import failed: {e!r}", file=sys.stderr)
    # 输出每件 transient entry 让 broker 走 entry 分流而不是整批 rc 路径
    print(json.dumps([
        {"path": p, "configs": [], "exit_code": EXIT_TERMINAL}
        for p in sldprt_list
    ], ensure_ascii=False))
    return EXIT_OK  # 整 batch rc=0；分类信号通过 entries

pythoncom.CoInitialize()
try:
    try:
        app = DispatchEx("SldWorks.Application")
    except pythoncom.com_error as e:
        # SW DispatchEx 失败：典型 transient（SW license 暂断 / RPC 抖动）
        # 整 batch 退化让 broker entry 分流而不是整批 fallthrough
        print(f"worker --batch: DispatchEx failed: {e!r}", file=sys.stderr)
        print(json.dumps([
            {"path": p, "configs": [], "exit_code": _classify_worker_exception(e)}
            for p in sldprt_list
        ], ensure_ascii=False))
        return EXIT_OK
    try:
        app.Visible = False
        app.UserControl = False
        app.FrameState = 0
        # ... §3.1.8.2 for 循环
    finally:
        try:
            app.ExitApp()
        except Exception as e:
            print(f"worker --batch: ExitApp ignored: {e!r}", file=sys.stderr)
finally:
    pythoncom.CoUninitialize()
```

**A1 修复语义**：worker 顶层失败不再让 broker 走 fallthrough；通过 entry-level `exit_code` 把分类信号透传，broker 按既有路径处理（§3.3）。pywin32 没装是部署级 terminal；DispatchEx 暂断是 transient。

##### §3.1.8.2 for 循环改造（不变 — 来自 rev 2）

替换 L134-143 batch for 循环：

```python
results = []
for sldprt_path in sldprt_list:
    try:
        configs = _open_doc_get_configs(app, sldprt_path)
        exit_code = EXIT_OK
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:
        print(
            f"worker --batch: {sldprt_path} failed: "
            f"{type(e).__name__}: {e!r}",
            file=sys.stderr,
        )
        configs = []
        exit_code = _classify_worker_exception(e)
    results.append({
        "path": sldprt_path,
        "configs": configs,
        "exit_code": exit_code,  # 新增字段（spec §3.3）
    })
print(json.dumps(results, ensure_ascii=False))
return EXIT_OK
```

**整 batch rc 仍是 0**（外部错误如 stdin JSON parse 错走原 rc=64 不变）；分类信号通过 entry-level `exit_code` 字段透传给 broker。

### §3.2 Broker rc 分流（rev 4：砍 transient cache，简单 rc 分流）

#### §3.2.1 broker 端常量

`adapters/solidworks/sw_config_broker.py` 顶部新增：

```python
# spec §3.1.2 — 与 worker 退出码合约同步（双边维护，见 §10 maintainer note）
WORKER_EXIT_OK = 0
WORKER_EXIT_TERMINAL = 2
WORKER_EXIT_TRANSIENT = 3
WORKER_EXIT_LEGACY = 4  # 防御性：旧 worker rc=4 当 transient 处理（升级期混跑）
```

> **rev 4 砍 transient cache 决策**：rev 3 引入的 `TRANSIENT_CACHE_TTL_SEC` + `_CONFIG_LIST_TRANSIENT_CACHE` 在 4 路 reviewer 审查中暴露 3 Critical + 7 Important 问题（multiprocessing 子进程 cache 各一份失效 / mtime stale / 跨进程并发覆盖 / TTL 过期窗口 spawn 风暴 / Layer 顺序矛盾等）。决策：**M-4 退化到"transient 不 cache 直接返 []"**（rev 2 行为）；"BOM loop 同 sldprt 多次调用重试" 作为 known limitation 推迟到 §11.1 followup。理由：实际 codegen 一次 prewarm 后正常路径走 L1 hit；transient 失败件**频率低**（M-4 修复关注的是单件被 hiccup 永久打废，不是单件被反复重试）。

#### §3.2.2 `_list_configs_via_com` rc 分流流程（替换 L499-536）

```
入参 sldprt_path → abs_path = _normalize_sldprt_key(...)

├─ Layer 2 (in-process L2)：现有 _CONFIG_LIST_CACHE 查询（不变） → hit return
├─ Layer 1 (持久化 L1)：现有 cache_mod 查询（不变） → hit return
│
└─ Layer 3 (fallback) spawn worker：
    ├─ subprocess.TimeoutExpired → log + return [] （★ 不 cache，下次重试）
    ├─ OSError → log + return [] （★ 不 cache，下次重试）
    ├─ rc=0 (EXIT_OK):
    │   ├─ JSON parse 成功 → cache L2 = configs + return configs
    │   └─ JSON parse 失败 → log + return [] （★ 不 cache，下次重试）
    ├─ rc=2 (EXIT_TERMINAL) → cache L2 = [] + return [] （唯一永久 cache 失败路径）
    ├─ rc=3 (EXIT_TRANSIENT) → log + return [] （★ 不 cache，下次重试）
    ├─ rc=4 (EXIT_LEGACY，旧 worker) → log + return [] （★ 不 cache，下次重试）
    └─ 其他 rc（SIGKILL=-9 / 未知） → log + return [] （★ 不 cache，保守归 transient）
```

#### §3.2.3 不变性

- rc=2 是**唯一**会污染 L2 cache 为 `[]` 的路径
- 其余失败（rc=3/4/未知 + Timeout/OSError/JSONDecodeError）都不 cache，让下次同 sldprt 调用重试
- 同 process 内重试可能触发同 sldprt 多次 spawn worker（已知 limitation，见 §11.1）；prewarm 一次成功后正常路径走 L1 hit 不受影响

### §3.3 Prewarm batch 路径 entry-level rc 分流

worker `--batch` 模式 stdout JSON schema 升级：

```jsonc
// 旧（v2.20.0）
[
  {"path": "X.sldprt", "configs": ["A", "B"]}
]
// 新（本 PR）
[
  {"path": "X.sldprt", "configs": ["A", "B"], "exit_code": 0},
  {"path": "Y.sldprt", "configs": [],         "exit_code": 2},
  {"path": "Z.sldprt", "configs": [],         "exit_code": 3}
]
```

broker `prewarm_config_lists` L615-628 改为（rev 3：缺 exit_code 当 invalidate signal）：

```python
for entry in results:
    sldprt_path = entry.get("path", "")
    configs = entry.get("configs", [])
    rc = entry.get("exit_code")  # ★ rev 3：不给 default，缺字段 → None → 当 invalidate
    mtime = cache_mod._stat_mtime(sldprt_path)
    size = cache_mod._stat_size(sldprt_path)
    if mtime is None or size is None:
        continue  # sldprt 文件已删 — 跳过不写（现状 L620-621 行为保留）
    key = _normalize_sldprt_key(sldprt_path)

    if rc is None:
        # ★ rev 3 C2 修复：旧 worker (≤v2.20.0) batch stdout 缺 exit_code 字段。
        # 旧 worker 的 catch-all 异常分支已设 configs=[]，无法区分成功 vs 失败。
        # 不写 entries → 强制 broker 走单件 fallback 路径（_list_configs_via_com）
        # 用新 worker 的 rc 合约重新 probe；防 cache 永久污染。
        # 升级期窗口结束后，新 worker 始终带 exit_code，此分支不再触发。
        log.warning(
            "config_lists batch entry 缺 exit_code 字段（旧 worker schema），"
            "跳过不写 entries：%s", sldprt_path,
        )
        continue
    if rc == WORKER_EXIT_OK:
        cache["entries"][key] = {"mtime": mtime, "size": size, "configs": configs}
    elif rc == WORKER_EXIT_TERMINAL:
        # 写 [] 防重试（与 _list_configs_via_com rc=2 路径对称）
        cache["entries"][key] = {"mtime": mtime, "size": size, "configs": []}
    else:
        # rc=3 (transient) / rc=4 (legacy 当 transient) / 未识别 rc：
        # 跳过不写 entries — 下次 prewarm 重试此 sldprt
        # 跟 _list_configs_via_com 单件路径"未识别 rc → transient"语义对齐
        continue
```

**向后兼容三层（与 §3.2 单件路径语义严格对齐）**：
1. 缺 `exit_code` 字段（rc is None）→ ★ **invalidate signal** 不写 entries（rev 3 C2 修复，防旧 worker 永久污染 cache）
2. `WORKER_EXIT_LEGACY=4` + 未识别 rc 都走 transient 分支（不 cache，下次重试）— 跟单件路径 §3.2 `_list_configs_via_com` 完全一致
3. `WORKER_EXIT_OK=0` + `WORKER_EXIT_TERMINAL=2` 写 entries（前者写 configs / 后者写 []）

### §3.4 cache.py `_save_config_lists_cache` 异常下沉

`adapters/solidworks/sw_config_lists_cache.py` 引入模块级 flag + 包 try/except。

**rev 4 F-2 修复**：模块顶部需新增 `import sys`（现有 imports 仅 `json/logging/os/datetime/Path/typing.Any`，缺 `sys`）。

```python
# 模块顶部需新增（rev 4 F-2 修）
import sys

_save_failure_warned = False

def _save_config_lists_cache(cache: dict[str, Any]) -> None:
    global _save_failure_warned
    path = get_config_lists_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        if not _save_failure_warned:
            _save_failure_warned = True
            sys.stderr.write(
                f"\n⚠ cache 文件 {path} 写入失败 ({type(e).__name__}: {e})\n"
                f"  照片级渲染依赖跨 process 一致 cache — 请检查该路径权限后重启。\n"
                f"  本次 codegen 不受影响；下次 prewarm 仍会自动重试 cache 写入。\n"
                f"  本次运行后续失败将仅 log，不再 banner。\n\n"
            )
        else:
            log.warning("config_lists save 重复失败: %s", e)
```

#### caller 简化

`broker.py` 现有 caller-side try/except 全部移除：

| 位置 | 改动 |
|------|------|
| L570-580（I-2 envelope save） | 去掉 `try/except`，裸调 `cache_mod._save_config_lists_cache(cache)` |
| L628（prewarm batch 末尾 save） | rev 4 F-5 修：**无需主动改动**；M-2 后 save 自愈不抛 OSError，外层 `except (TimeoutExpired, OSError, JSONDecodeError)` 不再可能因 save 触发，自然不再相关 |

**对称性**：`_load_config_lists_cache` L72-75 自愈（损坏返空 envelope）；`_save_*` 自愈（失败 banner+继续）— 两端契约都是「caller 不必 try/except，函数自管失败」。

### §3.5 banner 防 spam（首次失败即 banner）

| 行为 | 触发 |
|------|------|
| stderr banner（4 行 with ⚠） | 同 process 内**首次** save 失败 |
| log.warning（1 行） | 同 process 内**第 2+ 次** save 失败 |

`_save_failure_warned` 是模块级 flag，process 生命周期内只翻一次。

#### 测试隔离

`tests/test_sw_config_lists_cache.py` 添加 autouse fixture：

```python
@pytest.fixture(autouse=True)
def _reset_save_failure_warned():
    import adapters.solidworks.sw_config_lists_cache as mod
    mod._save_failure_warned = False
    yield
    mod._save_failure_warned = False
```

防 cross-test 污染。

---

## §4 数据流（5 条 path）

### Path 1 — 单件成功（无 cache）

```
broker._list_configs_via_com(p)
  L2 miss → L1 miss
  spawn worker(p)
  worker: open SLDPRT → 列 configs → print JSON → exit(0)
  broker: rc=0 → cache L2 + return configs
  L1 不写 — fallback 路径决策不变（spec §3.1 issue 4）
```

### Path 2 — Terminal 失败（SLDPRT 是错版本号 / 损坏 / 不存在）

```
broker._list_configs_via_com(p)
  L2 miss → L1 miss
  spawn worker(p)
  worker._list_configs_returning(p)
    → app.OpenDoc6(...) errors=64 (swFutureVersion)
    → _open_doc_get_configs raise OpenDocFailure(errors=64, ...)
    → 冒到 _list_configs except → _classify_worker_exception(e)
    → e.errors=64 ∉ _TRANSIENT_OPENDOC_ERRORS → return EXIT_TERMINAL=2
  worker exit(2)
  broker: rc=2 → cache L2 = [] + return []
  同 process 后续调用 = L2 hit → return [] 不再 spawn ✓
```

### Path 3 — Transient 失败（rev 4：不 cache 直接返 []）

```
broker._list_configs_via_com(p)
  Layer 2 miss → Layer 1 miss
  spawn worker(p)
  worker._list_configs_returning(p)
    → app.OpenDoc6(...) errors=8192 (swApplicationBusy)
    → OpenDocFailure(errors=8192) → _classify_worker_exception
    → e.errors=8192 ∈ _TRANSIENT_OPENDOC_ERRORS → return EXIT_TRANSIENT=3
  worker exit(3)
  broker: rc=3 → log + return [] (不 cache)
  同 process 后续调用 = L2 miss → L1 miss → 重新 spawn worker → 第 2 次可能成功
  （已知 limitation：BOM loop 同 sldprt 多次调用会触发多次 spawn — §11.1 followup）
```

### Path 4 — Prewarm batch（混合 rc）

```
prewarm_config_lists([p1, p2, p3])
  spawn worker --batch
  worker stdout = [
    {"path": "p1", "configs": ["A","B"], "exit_code": 0},
    {"path": "p2", "configs": [],        "exit_code": 2},  # terminal
    {"path": "p3", "configs": [],        "exit_code": 3},  # transient
  ]
  broker:
    p1 rc=0 → entries[p1] = {mtime, size, configs: ["A","B"]}
    p2 rc=2 → entries[p2] = {mtime, size, configs: []}      # 写 [] 防重试
    p3 rc=3 → 跳过不写 entries[p3]                           # 下次 prewarm 重试
  cache_mod._save_config_lists_cache(cache)  # M-2 自愈：失败 banner+继续
```

### Path 5 — Save 失败（PermissionError）

```
cache_mod._save_config_lists_cache(cache)
  tmp.write_text → PermissionError
  except OSError:
    if not _save_failure_warned:
      stderr banner ⚠ + set _save_failure_warned = True
    else:
      log.warning
  函数返 None 正常退出
  caller 不感知；跨 process L1 cache 失效但 L2 仍存活；下次 prewarm 重做
```

---

## §5 不变性（invariants）

| ID | 不变性 | 保证机制 |
|----|--------|---------|
| **I1** | prewarm 永远不抛异常打断 codegen | M-2 后 `_save_*` 不抛；M-4 后 broker rc 分流不抛；现有 `except (TimeoutExpired, OSError, JSONDecodeError)` 兜底保留 |
| **I2** | 同 process 内 terminal sldprt 不重复 spawn worker | rc=2 → cache L2 = [] |
| **I3** | 同 process 内 transient sldprt 后续调用会重试 | rc=3 → 不 cache，后续 L2 miss 触发新 spawn |
| **I4** | 跨 process L1 cache 不被 transient 污染 | rc=3 在 batch 路径跳过不写 entries |
| **I5** | 跨 process L1 cache 用 [] 标记 terminal 防重试 | rc=2 在 batch 路径写 entries[key] = {..., configs: []} |
| **I6** | save 失败 banner 同 process 内最多 1 次（不 spam） | `_save_failure_warned` 模块级 flag |
| **I7** | 北极星「照片级 > 傻瓜式」— 静默退化前必有醒目提示 | banner 模板含原因 + 用户行动指引（"请检查路径权限后重启"） |
| **I8** | 向后兼容 v2.20.0 cache schema v1 | 不 bump schema_version；entries 结构不变 |
| **I9** | 旧 worker batch 缺 `exit_code` 字段 → broker entries 整批跳过不写 + log.warning，broker 不抛 | rev 4 F-1/E3 修复（与 §3.3 rev 3 C2 实现对齐）：`entry.get("exit_code")` 无 default → `if rc is None: continue` invalidate signal |
| **I10** | 单件 + batch 路径"未识别 rc"语义严格一致（都归 transient 不 cache） | 两路径都走 `else: 不 cache` 兜底；spec §3.2 + §3.3 镜像 |
| **I11** | OpenDocFailure 是 RuntimeError 子类，不破现有 `except RuntimeError` 调用方 | spec §3.1.3 类定义 |
| **I12** | `_classify_worker_exception` 是单件 + batch 唯一分类入口（DRY） | spec §3.1.6 共享函数；§3.1.7 + §3.1.8 调用 |
| **I13** | rev 4 删除（原 transient cache TTL — 已砍） | — |
| **I14** | rev 4 删除（原 transient cache TTL 过期重试 — 已砍） | — |
| **I15** | rev 4 删除（原 transient cache 仅 in-process — 已砍） | — |
| **I16** | batch entry 缺 `exit_code` 字段 → 跳过不写 entries（防旧 worker 永久污染） | rev 3 C2：§3.3 `if rc is None: continue`（rev 4 保留）|
| **I17** | worker `_run_batch_mode` 顶部 boot fail（pywin32 ImportError / DispatchEx）也透 entry-level rc 让 broker 走 entry 分流 | rev 4 A1：§3.1.8.1 替换 stdout 输出 `[{"path": p, "configs": [], "exit_code": ...} for p in sldprt_list] + rc=0` |

---

## §6 边界 case

| Case | 处理 | 测试 |
|------|------|------|
| Edge 1 — sldprt mtime 改后旧 terminal cache 自动失效 | 现有 `_config_list_entry_valid` 已覆盖（mtime/size 比较） | 已有测试 |
| Edge 2 — worker 进程被 OS kill（rc=-9） | 落入"未知 rc 保守归 transient"分支 → 不 cache | `test_list_configs_unknown_rc_defaults_transient` |
| Edge 3 — worker print stdout 后才崩溃（rc!=0 但 stdout 有 JSON） | 保守归失败 — 不解析 partial stdout（现有逻辑保留） | 已有测试 |
| Edge 4 — `pythoncom` 模块在非 Windows 不存在 | worker 测试用 per-test `_patch_com` helper（参 `tests/test_sw_convert_worker.py` L34）mock；本 PR 不引入新 import 路径 | rev 4 F-4 修：现有 `_patch_com` 模板兼容（不是 `_install_fake_win32com`） |
| Edge 5 — banner stderr write 本身失败（极罕见） | 不再处理 — sys.stderr 不可写说明环境已极端损坏 | 不测 |
| Edge 6 — 多线程并发 save（_save_failure_warned race） | flag 是 best-effort（多线程下偶尔出 2 次 banner 可接受）— 不加锁，对齐"最简实现"原则 | 不测 |
| Edge 7 — `OpenDocFailure(errors=0, model_was_null=True)` 边角 | `e.errors=0 ∉ _TRANSIENT_OPENDOC_ERRORS` → terminal；`model_was_null` 字段保留方便日志 / 未来扩展决策 | `test_classify_open_doc_failure_null_model_terminal` |
| Edge 8 — broker 跨升级期混跑：旧 worker 进程返 rc=4 | broker 视 rc=4 为 transient（不 cache，下次 prewarm 自然换新 worker） | `test_list_configs_legacy_rc4_treated_as_transient` |
| Edge 9 — `pythoncom` import 失败时分类 com_error 实例（理论不可能但代码路径要稳） | `_classify_worker_exception` 内部 `try: import pythoncom` 失败时 `pass` 走兜底 transient | `test_classify_worker_exception_without_pythoncom` |
| Edge 10 — batch 模式整批 stdin JSON parse 失败 | rc=64（不变）— 现有路径保留；broker 收到 rc=64 不命中任一 entry 分流分支 → batch 整体 fallback 到 _list_configs_via_com 单件路径（已有逻辑 L605-610 retain） | 已有测试 + `test_prewarm_batch_rc64_full_fallback` |
| Edge 11 — rev 4 删除（原 transient cache TTL 边界） | — | — |
| Edge 12 — rev 4 删除（原 transient cache 内存增长） | — | — |
| Edge 13 — rev 4 删除（原 transient cache 与 prewarm 交互） | — | — |
| Edge 14 — worker batch 顶部 ImportError 路径（rev 4 A1）| `_run_batch_mode` 顶部 pywin32 ImportError → 输出 `[{"path": p, "configs": [], "exit_code": EXIT_TERMINAL} for p in sldprt_list] + rc=0`，broker 走 entry 分流；防整批 fallthrough M-4 失效 | `test_batch_mode_pywin32_import_failure_emits_terminal_per_entry` |
| Edge 15 — worker batch DispatchEx 失败路径（rev 4 A1）| `_run_batch_mode` DispatchEx 抛 com_error → 输出 `[{"path": p, "configs": [], "exit_code": _classify_worker_exception(e)}, ...] + rc=0`；broker 按 entry 分类 | `test_batch_mode_dispatchex_com_error_emits_classified_per_entry` |

---

## §7 测试策略

### §7.1 新增 `tests/test_sw_list_configs_worker.py`（worker 端 unit test）

复用 `tests/test_sw_convert_worker.py` 的 `_patch_com` 模板（"全 mock pythoncom + Dispatch，不依赖真实 SW"）。

| 测试 | 断言 |
|------|------|
| `test_worker_success_returns_rc0_with_configs_json` | mock `_list_configs_returning` 返 ["A","B"] → rc=0；stdout 解析为 ["A","B"] |
| `test_worker_open_doc_failure_terminal_errors_returns_rc2` | mock OpenDoc6 errors=64 (swFutureVersion) → 抛 `OpenDocFailure` → rc=2 |
| `test_worker_open_doc_failure_transient_errors_returns_rc3` | mock OpenDoc6 errors=4096 (swApplicationBusy) → 抛 `OpenDocFailure` → rc=3 |
| `test_worker_open_doc_null_model_returns_rc2` | mock OpenDoc6 returns None (errors=0) → `OpenDocFailure(errors=0, model_was_null=True)` → rc=2 |
| `test_worker_com_error_transient_hresult_returns_rc3` | mock `pythoncom.com_error` hresult=-2147023170 (RPC_E_DISCONNECTED) → rc=3 |
| `test_worker_com_error_terminal_hresult_returns_rc2` | mock `pythoncom.com_error` hresult=-2147467259（未识别） → rc=2 |
| `test_worker_import_error_returns_rc2` | mock pywin32 import 失败 → rc=2 |
| `test_worker_unknown_exception_defaults_transient_rc3` | mock 抛 ValueError → rc=3；stderr 含 "ValueError" |
| `test_classify_open_doc_failure_table_lookup` | 直接单测 `_classify_worker_exception(OpenDocFailure(errors=N))` 各 N 值 |
| `test_classify_com_error_table_lookup` | 直接单测 `_classify_worker_exception(pythoncom.com_error)` 各 hresult |
| `test_classify_worker_exception_without_pythoncom` | mock pythoncom import 失败 → 走兜底 transient（Edge 9） |
| `test_classify_open_doc_failure_null_model_terminal` | `OpenDocFailure(errors=0, model_was_null=True)` → terminal（Edge 7） |
| `test_batch_mode_pywin32_import_failure_emits_terminal_per_entry` | rev 4 A1：mock batch 顶部 `import pythoncom` 抛 ImportError → stdout = `[{"path": p, "configs": [], "exit_code": 2} for p in 输入]`，rc=0；防整批 fallthrough 让 broker 走 entry 分流（Edge 14） |
| `test_batch_mode_dispatchex_com_error_emits_classified_per_entry` | rev 4 A1：mock batch 顶部 `DispatchEx` 抛 `pythoncom.com_error` (transient hresult) → stdout = `[{"path": p, "configs": [], "exit_code": 3} for p in 输入]`，rc=0（Edge 15） |
| `test_invariant_open_doc_failure_is_runtime_error_subclass` | **rev 5 A 直测 I11**：`assert issubclass(OpenDocFailure, RuntimeError)` + 创建实例 + 验证 `isinstance(e, RuntimeError)` 仍 True（防 except RuntimeError 调用方破） |
| `test_invariant_classify_worker_exception_called_by_both_single_and_batch_paths` | **rev 5 A 直测 I12**：monkeypatch.setattr `_classify_worker_exception` spy 函数；分别跑 `_list_configs(p)` 失败路径 + `_run_batch_mode([p1, p2])` 失败路径；assert spy 被两条路径都调用过（DRY 验证）|
| `test_invariant_open_doc_failure_carries_structured_fields` | **rev 5 A 补**：`raise OpenDocFailure(errors=4096, warnings=0, model_was_null=False)` 后 catch；assert `e.errors == 4096 and e.warnings == 0 and e.model_was_null is False`（防字段被吞）|

### §7.2 扩展 `tests/test_sw_config_broker.py`

| 测试 | 断言 |
|------|------|
| `test_list_configs_rc2_caches_empty_list_to_prevent_retry` | mock subprocess rc=2 → 第 1 次返 []；**第 2 次同 sldprt `subprocess.run.call_count == 1`**（L2 hit） |
| `test_list_configs_rc3_does_not_cache_for_retry` | mock subprocess rc=3 → 第 1 次返 []；**第 2 次同 sldprt `subprocess.run.call_count == 2`**（重 spawn） |
| `test_list_configs_legacy_rc4_treated_as_transient` | mock subprocess rc=4 → 不 cache；第 2 次重试（Edge 8 兼容） |
| `test_list_configs_timeout_treated_as_transient_no_cache` | TimeoutExpired → 不 cache；第 2 次重试 |
| `test_list_configs_oserror_treated_as_transient_no_cache` | OSError → 不 cache；第 2 次重试 |
| `test_list_configs_rc0_with_invalid_json_stdout_treated_as_transient` | mock rc=0 + stdout 非合法 JSON → 不 cache；第 2 次重试 |
| `test_list_configs_unknown_rc_defaults_transient` | mock rc=99 → 不 cache；第 2 次重试 |
| `test_prewarm_batch_mixed_rc_writes_terminal_skips_transient` | mock batch stdout 含 3 entry 混合 exit_code → cache entries 写 rc=0 与 rc=2 项，跳过 rc=3 项 |
| `test_prewarm_batch_legacy_no_exit_code_field_skipped_not_polluting_cache` | rev 3 C2 + rev 4 保留：mock batch stdout 缺 `exit_code` 字段 → broker 跳过不写 entries；caplog 含 "缺 exit_code 字段（旧 worker schema）" |
| `test_prewarm_batch_rc4_legacy_skipped_like_transient` | mock batch entry exit_code=4 → 跳过不写 entries（与单件路径一致） |
| `test_prewarm_batch_unknown_rc_skipped_like_transient` | mock batch entry exit_code=99 → 跳过不写 entries（I10 一致性） |
| `test_prewarm_batch_rc64_full_fallback` | mock subprocess rc=64（worker stdin JSON parse 错） → broker 不写 cache（Edge 10） |
| `test_prewarm_save_failure_does_not_propagate_to_caller` | rev 4 补 I1 测试：mock `cache_mod._save_config_lists_cache` 抛 OSError → `prewarm_config_lists` 不抛（M-2 自愈契约） |
| `test_invariant_l1_cache_not_polluted_by_transient_after_save` | **rev 5 A 直测 I4**：mock prewarm batch 含 rc=3 entry → 调 `prewarm_config_lists` → 跑完后读 L1 cache 文件验证：`abs_path in cache["entries"]` is False（transient 不污染 L1）|
| `test_invariant_l1_cache_terminal_marked_with_empty_configs` | **rev 5 A 直测 I5**：mock prewarm batch 含 rc=2 entry → 跑完后读 L1 cache 文件验证：`cache["entries"][abs_path]["configs"] == []`（terminal 用 [] 标记防重试）|
| `test_invariant_unknown_rc_consistent_single_vs_batch` | **rev 5 A 直测 I10**：mock 单件 rc=99 + mock batch entry exit_code=99 → 行为一致：两路径都不写 cache（直接对比 L1 + L2 状态）|
| `test_negative_worker_rc2_with_existing_l1_success_entry_overrides_with_terminal` | **rev 5 D 负面组合**：预填 L1 entry success + mtime 没变 → 调 `_list_configs_via_com` → broker 应该 L1 hit return success（rc=2 路径不触发因 L1 hit）|
| `test_negative_worker_rc0_with_save_failure_returns_configs_anyway` | **rev 5 D 负面组合**：mock subprocess rc=0 + mock cache_mod._save_config_lists_cache 抛 OSError → 函数仍返 configs（save 失败不影响读结果）|
| `test_negative_worker_timeout_with_l1_envelope_invalidated` | **rev 5 D 负面组合**：mock L1 envelope sw_version 过期 + worker TimeoutExpired → broker 不写 L1（envelope 升级但 entries 不写）|
| `test_negative_unknown_rc_with_existing_l2_terminal_does_not_respawn` | **rev 5 D 负面组合**：预填 L2 = [] (rc=2 终态) → 调 `_list_configs_via_com` → L2 hit 返 [] 不 spawn worker；assert subprocess.run.call_count == 0 |
| `test_negative_invalid_json_stdout_with_l1_partial_load` | **rev 5 D 负面组合**：mock subprocess rc=0 + stdout 非合法 JSON + L1 partial load → broker 不 cache + 返 [] + L1 不破 |
| `test_negative_concurrent_l1_load_save_atomicity` | **rev 5 D 负面组合**：先 prewarm 写 L1 → 同时 mock _save 抛 PermissionError → 后续 _load 必须能读到 partial 写之前的内容（os.replace 原子性）|

### §7.3 扩展 `tests/test_sw_config_lists_cache.py`（已存在，扩 `TestSaveCache` 类）

文件已含 `TestModuleConstants` / `TestEmptyCache` / `TestSaveCache` 等类。本 PR 在 `TestSaveCache` 类内新增 4 测试 + module-level autouse fixture：

| 测试 | 断言 |
|------|------|
| `TestSaveCache.test_save_permission_error_first_call_writes_banner_to_stderr` | mock `Path.write_text` 抛 PermissionError → `capsys.readouterr().err` 含 "⚠ cache 文件" + path + "PermissionError" |
| `TestSaveCache.test_save_failure_second_call_no_banner_only_log_warning` | 同 process 内第 2 次 save 失败 → `capsys.err` 不含 banner；`caplog.records` 含 "重复失败" log.warning |
| `TestSaveCache.test_save_oserror_does_not_propagate_to_caller` | mock 抛 OSError → 函数返 None 不 raise |
| `TestSaveCache.test_save_oserror_subclass_disk_full_does_not_propagate` | mock 抛 `OSError(errno.ENOSPC)` 子类 → 同样静默自愈（不只 PermissionError）|
| `TestSaveCache.test_invariant_save_failure_emits_user_visible_banner` | **rev 5 A 直测 I7**：mock 抛 PermissionError → `capsys.readouterr().err` 含 "⚠"（视觉 emoji） + "请检查"（用户行动指引）+ "本次 codegen 不受影响"（rev 3 I3 安抚）三 marker 同时出现，对齐"照片级 > 傻瓜式" |
| `TestSaveCache.test_invariant_v220_cache_schema_v1_loads_without_break` | **rev 5 A 直测 I8**：用 `tests/fixtures/sw_config_lists_v220.json`（真实 v2.20.0 cache schema 内容）→ `_load_config_lists_cache()` 返合法 envelope dict + `cache["schema_version"] == 1` + entries 解析 OK |

**`tests/conftest.py` 新增 autouse fixtures（rev 4 D8/I1 修复 — 跨文件作用域）**：

```python
# tests/conftest.py（追加，不替换现有内容）
@pytest.fixture(autouse=True)
def _reset_save_failure_warned():
    """rev 4 D8/I1：cache.py 的 _save_failure_warned flag 跨 process 测试隔离。
    放 conftest.py 而不是单文件 fixture，因 broker 测试也间接触发 _save_*。"""
    import adapters.solidworks.sw_config_lists_cache as mod
    mod._save_failure_warned = False
    yield
    mod._save_failure_warned = False

@pytest.fixture(autouse=True)
def _reset_config_list_caches():
    """rev 4 补：broker 端 _CONFIG_LIST_CACHE (L2) 跨测试清理 + autouse 防 cross-test pollution。"""
    from adapters.solidworks import sw_config_broker
    sw_config_broker._CONFIG_LIST_CACHE.clear()
    yield
    sw_config_broker._CONFIG_LIST_CACHE.clear()
```

### §7.4 集成测试 — broker → worker → cache 真实调用链（rev 5 C，新增 8 测试）

**测试文件**：`tests/test_sw_config_broker_integration.py`（**新增**）

**模式**：mock 仅 `subprocess.run`（控制 worker stdout / rc / stderr / TimeoutExpired），其余 broker / cache_mod / sw_config_lists_cache 代码全走真实路径。用 `tmp_path` fixture 隔离 cache file。

| 测试 | 断言 |
|------|------|
| `test_integration_prewarm_to_l1_cache_to_save_full_chain_rc0` | mock subprocess.run rc=0 + JSON entries → 调真实 `prewarm_config_lists([p1, p2])` → 真实 cache_mod._save_config_lists_cache 写盘 → 读 file 验证 entries 写入 + envelope 字段齐全 |
| `test_integration_prewarm_terminal_persists_empty_to_l1_cache_rc2` | mock rc=0 但 entry exit_code=2 → 真实落盘 → 读 file 验证 `cache["entries"][key]["configs"] == []`（terminal mark）|
| `test_integration_prewarm_transient_does_not_persist_rc3` | mock entry exit_code=3 → 真实跑完 → 读 file 验证 `key not in cache["entries"]` |
| `test_integration_prewarm_legacy_no_exit_code_skipped_to_save` | mock entry 缺 exit_code → 真实跑 + log capture → entries 不写 + caplog 含 "缺 exit_code 字段" |
| `test_integration_save_failure_does_not_break_subsequent_calls` | mock subprocess rc=0 + monkeypatch get_config_lists_cache_path 指向只读路径 → save banner 出 stderr + return 不抛 + 后续 `_list_configs_via_com(p)` 仍能 spawn worker 工作 |
| `test_integration_l1_cache_load_corrupt_self_heals_then_prewarm_rebuilds` | 预先写非法 JSON 到 cache file → 真实 `_load_config_lists_cache` self-heal 返空 envelope → 真实 prewarm 跑通后重写合法 cache file |
| `test_integration_envelope_invalidated_clears_entries_and_rewrites_envelope` | 预填 cache file 含 sw_version=旧 + entries → mock detect_solidworks 返新 sw_version → 真实 prewarm → cache file envelope sw_version 已升 + entries 全清重列 |
| `test_integration_normalize_sldprt_key_consistency_forward_vs_back_slash` | 用 `C:/foo/bar.sldprt` 写入 prewarm → 用 `C:\foo\bar.sldprt` 调 `_list_configs_via_com` → L1 hit return（key 归一化跨整链一致） |

### §7.5 Negative testing 矩阵（rev 5 D，新增）

**已分布在 §7.2** broker 测试 6 个 `test_negative_*`（worker 5 种失败 × broker 3 种状态的代表性组合）。这一节文档化矩阵：

| Worker 失败类型 \ broker 状态 | L1 missing | L1 has success entry | L1 envelope invalidated |
|------|------|------|------|
| **rc=0** | 单 hit cache L2 + L1 entry | 不重 spawn return L1 | 跑 prewarm rebuild |
| **rc=2 (terminal)** | L2=[] return [] | L1 hit return success（rc=2 不触发 — 已 §7.2 测试）| envelope 升级 + entries 不写 |
| **rc=3 (transient)** | 不 cache return [] | L1 hit return success | envelope 升级但 entries 不写 |
| **TimeoutExpired** | 不 cache return [] | L1 hit return success | envelope 升级但 entries 不写 |
| **OSError** | 不 cache return [] | L1 hit return success | envelope 升级但 entries 不写 |

**矩阵覆盖说明**：5 worker 失败 × 3 broker 状态 = 15 组合；§7.2 已直测 6 个代表性 + 隐式覆盖 9 个（其余组合的 L1 hit 路径行为完全相同 — broker rc 分流根本不触发，由 L1 hit 早 return）。如需 100% 矩阵覆盖再加测试，标 §11.7 followup。

### §7.6 端到端用户场景测试（rev 5 F，新增 5 测试）

**测试文件**：`tests/test_sw_config_broker_e2e.py`（**新增**）

**模式**：用 user 视角描述场景；mock 必要的外部依赖（subprocess / SW detect / file system）；跑真实 broker / cache 全 layer。

| 测试 | 用户场景 |
|------|---------|
| `test_e2e_first_install_sw_default_settings_prewarm_to_lookup_path` | **场景**：用户首次装 SW + 跑 codegen。Mock detect_solidworks 返合法 SwInfo + subprocess 模拟 batch 全部 rc=0 → 跑 `prewarm_config_lists([p1..p5])` → 紧接着跑 5 次 `_list_configs_via_com(pN)` → 每次都 L1 hit + assert subprocess.run.call_count == 1（仅 prewarm 一次 spawn）|
| `test_e2e_upgrade_period_legacy_worker_skip_then_single_fallback` | **场景**：升级期混跑（broker 新 / worker 旧）。Mock prewarm batch stdout 缺 exit_code → broker 跳过不写 entries → 模拟下一次单件 `_list_configs_via_com(p)` 也是旧 worker 返 rc=4 → broker 当 transient 不 cache → 第 3 次同 sldprt 又 spawn |
| `test_e2e_corrupt_cache_file_self_heals_and_rebuilds` | **场景**：用户磁盘工具把 cache file 写坏。预先写 `~/.cad-spec-gen/sw_config_lists.json` = "INVALID_JSON" → 跑 prewarm → load self-heal 返空 envelope → batch worker 跑通 → 落盘合法 cache → assert 后续 `_load_config_lists_cache` 返新合法内容 |
| `test_e2e_double_sw_concurrent_prewarm_last_writer_wins` | **场景**：用户笔记本 + RDP 双开 codegen。模拟两次顺序 prewarm（process A 写 entries={p1: cfg1} → process B 写 entries={p2: cfg2}）；assert 第二次写后 cache 仅含 p2（last-writer-wins，已知 limitation 见 §11.4）|
| `test_e2e_large_bom_100_components_no_excessive_spawn_after_prewarm` | **场景**：100 件大 BOM。Mock prewarm batch 100 entries 全 rc=0 → 跑 prewarm 一次 → 跑 100 次 `_list_configs_via_com` → assert subprocess.run.call_count == 1（仅 prewarm 一次 spawn，所有 100 件都 L1 hit）|

### §7.7 Invariant ↔ 测试 一一对应映射表（rev 5 A，新增）

防 reviewer 报告"未测的 invariant"。每条 invariant 必有 ≥1 个测试直接断言。

| Invariant | 测试名 | 测试位置 |
|-----------|--------|---------|
| **I1** prewarm 永远不抛 | `test_prewarm_save_failure_does_not_propagate_to_caller` | §7.2 |
| **I2** terminal sldprt 同 process 不重复 spawn | `test_list_configs_rc2_caches_empty_list_to_prevent_retry` | §7.2 |
| **I3** transient sldprt 同 process 后续重试 | `test_list_configs_rc3_does_not_cache_for_retry` | §7.2 |
| **I4** L1 cache 不被 transient 污染 | `test_invariant_l1_cache_not_polluted_by_transient_after_save` | §7.2 |
| **I5** L1 cache [] 标记 terminal | `test_invariant_l1_cache_terminal_marked_with_empty_configs` | §7.2 |
| **I6** banner 同 process 内最多 1 次 | `test_save_failure_second_call_no_banner_only_log_warning` | §7.3 |
| **I7** 静默退化前必有醒目提示 | `test_invariant_save_failure_emits_user_visible_banner` | §7.3 |
| **I8** 向后兼容 v2.20.0 schema v1 | `test_invariant_v220_cache_schema_v1_loads_without_break` | §7.3 |
| **I9** 旧 worker batch 缺 exit_code → 跳过 | `test_prewarm_batch_legacy_no_exit_code_field_skipped_not_polluting_cache` | §7.2 |
| **I10** 单件 + batch "未识别 rc" 一致 | `test_invariant_unknown_rc_consistent_single_vs_batch` | §7.2 |
| **I11** OpenDocFailure 是 RuntimeError 子类 | `test_invariant_open_doc_failure_is_runtime_error_subclass` | §7.1 |
| **I12** _classify_worker_exception 单+batch 唯一入口 | `test_invariant_classify_worker_exception_called_by_both_single_and_batch_paths` | §7.1 |
| **I16** batch entry 缺 exit_code → 跳过 | 同 I9（重叠语义） | §7.2 |
| **I17** worker batch 顶部 boot fail 透 entry rc | `test_batch_mode_pywin32_import_failure_emits_terminal_per_entry` + `test_batch_mode_dispatchex_com_error_emits_classified_per_entry` | §7.1 |

**14 invariants 100% 测试覆盖** ✓（不变性 zero gap）。

### §7.8 Edge case ↔ 测试 一一对应映射表（rev 5 B，新增）

| Edge case | 测试名 | 状态 |
|-----------|--------|------|
| Edge 1 — sldprt mtime 改后旧 terminal cache 失效 | 现有 `tests/test_sw_config_lists_cache.py::TestEntryValid` | ✓ 已有 |
| Edge 2 — worker 进程被 OS kill (rc=-9) | `test_list_configs_unknown_rc_defaults_transient` | ✓ §7.2 |
| Edge 3 — worker print stdout 后崩溃 | 现有覆盖（partial stdout 不解析）| ✓ 已有 |
| Edge 4 — `pythoncom` 在非 Windows 不存在 | `_patch_com` mock 模板复用 | ✓ §7.1 工具 |
| Edge 5 — banner stderr write 本身失败 | 不测（环境极端损坏，by-design）| 不测 |
| Edge 6 — 多线程 _save_failure_warned race | 不测（best-effort）| 不测 |
| Edge 7 — OpenDocFailure null model | `test_classify_open_doc_failure_null_model_terminal` | ✓ §7.1 |
| Edge 8 — broker 跨升级期混跑 rc=4 | `test_list_configs_legacy_rc4_treated_as_transient` | ✓ §7.2 |
| Edge 9 — pythoncom import 失败时分类 | `test_classify_worker_exception_without_pythoncom` | ✓ §7.1 |
| Edge 10 — batch stdin JSON parse 失败 rc=64 | `test_prewarm_batch_rc64_full_fallback` | ✓ §7.2 |
| Edge 14 — worker batch 顶部 ImportError | `test_batch_mode_pywin32_import_failure_emits_terminal_per_entry` | ✓ §7.1 |
| Edge 15 — worker batch DispatchEx 失败 | `test_batch_mode_dispatchex_com_error_emits_classified_per_entry` | ✓ §7.1 |

**12 Edge case 中 10 有测试覆盖，2 显式标"不测"** ✓。

### §7.9 测试总数（rev 5 重算）

| 类型 | 测试文件 | 测试数 |
|------|---------|-------|
| Worker unit | `tests/test_sw_list_configs_worker.py` | 17（rev 4 14 + rev 5 A 3 invariant 直测）|
| Broker unit + invariant + negative | `tests/test_sw_config_broker.py` | 22（rev 4 13 + rev 5 A 3 invariant 直测 + rev 5 D 6 negative）|
| Cache unit + invariant | `tests/test_sw_config_lists_cache.py` | 6（rev 4 4 + rev 5 A 2 invariant 直测）|
| **集成** | `tests/test_sw_config_broker_integration.py` (**新**) | 8（rev 5 C）|
| **端到端** | `tests/test_sw_config_broker_e2e.py` (**新**) | 5（rev 5 F）|
| Conftest fixtures | `tests/conftest.py` | 不计入 |
| **总计** | — | **58 个新测试** |

> rev 4 31 → rev 5 58（约 1.9x），覆盖率从隐式 → CI 强制 ≥95% (§12)。

---

## §8 文件清单

| 文件 | 改动 | 估算 LOC |
|------|------|---------|
| 文件 | 改动 | 估算 LOC |
|------|------|---------|
| `adapters/solidworks/sw_list_configs_worker.py` | 新增 `OpenDocFailure(RuntimeError)` 子类异常（§3.1.3）；新增 `EXIT_OK/TERMINAL/TRANSIENT/USAGE` 常量 + `_TRANSIENT_OPENDOC_ERRORS = {4096, 8192, 16384}`（rev 4 F-3 用真 SW SDK 数值） + `_TRANSIENT_COM_HRESULTS` + `_classify_worker_exception` 共享分类函数（§3.1.6）；`_open_doc_get_configs` 失败分支替换为 `raise OpenDocFailure(...)`（§3.1.3）；`_list_configs` 重写 try/except 走分类（§3.1.7）；`_run_batch_mode` 顶部 ImportError/DispatchEx 失败也透 entry-level rc（rev 4 A1，§3.1.8.1） + for 循环 except 改调分类函数 + entry 加 `exit_code` 字段（§3.1.8.2） | +110 / -30 |
| `adapters/solidworks/sw_config_broker.py` | 顶部新增 `WORKER_EXIT_OK/TERMINAL/TRANSIENT/LEGACY` 常量（§3.2.1）；`_list_configs_via_com` rc 分流（替换 L499-536，§3.2.2）—— rc=0 cache configs / rc=2 cache [] / rc=3+rc=4+未知 + TimeoutExpired+OSError+JSON parse 失败 不 cache；`prewarm_config_lists` batch 路径 entry-level rc 处理含 rc is None invalidate 分支（替换 L615-628，§3.3）；移除 L570-580 caller-side try/except | +50 / -35 |
| `adapters/solidworks/sw_config_lists_cache.py` | 顶部新增 `import sys`（rev 4 F-2）；`_save_config_lists_cache` 包 try/except + 模块级 `_save_failure_warned` flag + banner（§3.4-§3.5） | +27 / -3 |
| `tests/test_sw_list_configs_worker.py` | **新增** 17 测试（rev 4 14 + rev 5 A 3 invariant 直测）| +450 / -0 |
| `tests/test_sw_config_broker.py` | 扩展 22 测试（rev 4 13 + rev 5 A 3 + rev 5 D 6 negative）| +500 / -0 |
| `tests/test_sw_config_lists_cache.py` | 扩展现有 `TestSaveCache` 类加 6 测试（rev 4 4 + rev 5 A 2 invariant 直测）| +110 / -0 |
| `tests/test_sw_config_broker_integration.py` | **新增**（rev 5 C）8 集成测试 | +280 / -0 |
| `tests/test_sw_config_broker_e2e.py` | **新增**（rev 5 F）5 端到端用户场景测试 | +220 / -0 |
| `tests/fixtures/sw_config_lists_v220.json` | **新增**（rev 5 A I8 直测用）真实 v2.20.0 cache schema sample | +20 / -0 |
| `tests/conftest.py` | rev 4 D8/I1：新增 2 个 autouse fixture (`_reset_save_failure_warned` + `_reset_config_list_caches`) 跨文件作用域 | +25 / -0 |
| `pyproject.toml` | rev 5 H：新增 `[tool.coverage.run]` 配置 + `[tool.pytest.ini_options]` addopts `--cov=adapters/solidworks --cov-report=term-missing --cov-fail-under=95` | +15 / -0 |
| `.github/workflows/ci.yml` 或 `.github/workflows/test.yml` | rev 5 H：CI workflow `pytest` 步骤加 `--cov-fail-under=95`；fail 时 PR block | +10 / -2 |
| `docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md` | §11 标 M-2 + M-4 closed + 引用本 spec | +5 / -2 |

**总估算**：~1840 LOC 变化（1605 测试 + fixture / 195 实现 / 25 config / 15 文档）。

> **rev 5 LOC 增长说明**（user 选"测试越详尽越好 全集"）：rev 4 770 LOC → rev 5 1840 LOC，测试 LOC 从 735 → 1605（+870）+ 实施 LOC 不变 195 + 新加 conftest 25 + pyproject/CI 25 + fixture file 20。测试: 实施 比例 8.2:1（rev 4 是 3.8:1）。
>
> **回报**：每个 invariant 都有直测（无"未测的 invariant"）+ Edge case 覆盖率 100% + 集成测试覆盖 broker→worker→cache 真实链 + 端到端用户场景 + CI gate enforce 防 future regression。期望下次 reviewer 抓不到漏。

---

## §9 Phase / Task 路线图（writing-plans 接口）

预设 **5 phase / 24 task + 1 plan-level 前置校准** 量级（rev 5 加测试覆盖后；具体粒度 plan 阶段细化）：

### Plan-level 前置校准（rev 4 F-3 强制前置 — 不计入 phase task）

**plan task 0**：在本机 SW 装好的环境跑：
```bash
python -c "from win32com.client import constants; print({k: getattr(constants, k) for k in dir(constants) if k.startswith('swFileLoadError_')})"
```
校准 `swFileLoadError_e` 真实数值；如与 spec §3.1.4 表（`_TRANSIENT_OPENDOC_ERRORS = {4096, 8192, 16384}`）有出入，**先更新 spec rev 6** 再开 Phase 1。这是 plan 阶段的环境校准，不算实施 task。

### Phase 1 — Worker 端分类基建 + rc 合约 + 3 invariant 直测（7 task）

1. 写测试：`test_sw_list_configs_worker.py` 17 测试全部 RED（rev 4 14 + rev 5 A I11/I12 + OpenDocFailure 字段直测 3 个 invariant 测试）
2. 实现：定义 `class OpenDocFailure(RuntimeError)` 含 `errors: int / warnings: int / model_was_null: bool` 字段（§3.1.3）
3. 实现：`EXIT_OK/TERMINAL/TRANSIENT/USAGE` 常量（**不**含 EXIT_LEGACY，B2 修）+ `_TRANSIENT_OPENDOC_ERRORS = frozenset({4096, 8192, 16384})`（rev 4 F-3 真值） + `_TRANSIENT_COM_HRESULTS`
4. 实现：`_classify_worker_exception(e)` 共享函数（§3.1.6）
5. 实现：`_list_configs` 重写（§3.1.7） + `_run_batch_mode` 顶部 boot fail emit per-entry stdout（§3.1.8.1） + for 循环 except 改调分类（§3.1.8.2）
6. 实现：`_open_doc_get_configs` 失败分支改抛 `OpenDocFailure(...)`
7. 验证：17 测试全绿 + ruff/mypy + 覆盖率 worker 模块 ≥95%

### Phase 2 — Broker rc 分流 + batch 协议升级 + 3 invariant 直测 + 6 negative（5 task）

8. 写测试：`test_sw_config_broker.py` 22 新测试全部 RED（rev 4 13 + rev 5 A I4/I5/I10 + rev 5 D 6 negative）
9. 实现：broker 顶部新增 `WORKER_EXIT_OK/TERMINAL/TRANSIENT/LEGACY` 常量（§3.2.1）
10. 实现：`_list_configs_via_com` rc 分流（替换 L499-536，§3.2.2）
11. 实现：`prewarm_config_lists` batch entry-level rc 处理（§3.3）含 `rc is None → continue` invalidate signal（rev 3 C2 保留）
12. 验证：22 测试全绿 + 覆盖率 broker 模块 ≥95%

### Phase 3 — cache.py save 自愈 + 2 invariant 直测 + conftest fixture（4 task）

13. 写测试：`tests/test_sw_config_lists_cache.py` `TestSaveCache` 类加 6 测试（4 rev 4 + 2 rev 5 I7/I8 invariant 直测）；`tests/fixtures/sw_config_lists_v220.json` 真实 v2.20.0 cache sample
14. 实现：`tests/conftest.py` 加 2 个 autouse fixture（rev 4 D8/I1）
15. 实现：`sw_config_lists_cache.py` 顶部加 `import sys`（rev 4 F-2）；`_save_config_lists_cache` try/except OSError + `_save_failure_warned` + banner（rev 3 I3 安抚文案）
16. 验证：6 测试全绿 + 覆盖率 cache 模块 ≥95% + 移除 broker.py L570-580 caller-side try/except

### Phase 4 — 集成测试（rev 5 C，4 task）

17. 写 `tests/test_sw_config_broker_integration.py` 8 集成测试 全部 RED（broker → worker → cache 真实链 mock 仅 subprocess.run）
18. 跑测试 GREEN，发现 unit 测试漏掉的 cross-layer bug（mock 隔离的天然盲区）
19. 修任何集成测试发现的 bug（修代码而不是 fudge 测试）；spec rev 加 followup 记录
20. 验证：8 集成测试全绿 + 总覆盖率 ≥95%

### Phase 5 — 端到端 user 场景 + CI gate + 文档（4 task，task 21-24）

21. 写 `tests/test_sw_config_broker_e2e.py` 5 端到端用户场景测试 全部 RED（首次装 SW / 升级期混跑 / cache 损坏 / 双 SW / 100 件 BOM）
22. 跑 e2e GREEN
23. 实现 CI gate：`pyproject.toml` 加 `[tool.pytest.ini_options]` addopts `--cov=adapters/solidworks --cov-fail-under=95`；`.github/workflows/ci.yml` `pytest` 步骤同步加 flag；本地 `pytest --cov-fail-under=95` 通过
24. 实现：`docs/.../2026-04-26-sw-toolbox-config-list-cache-design.md` §11 标 M-2 + M-4 closed + 引用本 spec；端到端跑 `pytest tests/test_sw_*.py` 全绿不 regression

每 phase 末跑 quality reviewer 抓系统视角问题（命名一致性 / 模块边界 / 文档同步）；按 memory `feedback_cp_batch_quality_review.md` phase 末整体 reviewer 优于 per-task。**Phase 4-5 集成 + e2e 测试是 rev 5 新加重点**，预期能在实施期间抓到单元测试漏掉的 cross-layer bug。

---

## §10 引用与上下文

- **memory `project_session38_handoff.md`** — subagent-driven 全流程 (implementer / spec / quality / final reviewer 串联)
- **memory `feedback_cp_batch_quality_review.md`** — phase 末整体 quality reviewer 优于 per-task
- **memory `feedback_external_subsystem_safety_valve.md`** — `CAD_SW_BROKER_DISABLE` env 安全阀已存在；本 PR 无新 env
- **spec `2026-04-26-sw-config-broker-i2-i3-fix-design.md` §3** — banner 风格模板（与 I-3 锁等待 banner 同模板）
- **spec `2026-04-25-sw-toolbox-llm-config-broker-design.md` §5.3** — invariant 1 「prewarm 永不抛打断 codegen」

### §10.1 Maintainer notes（rev 3 M5 标注）

| 跟点 | 说明 |
|------|------|
| **Worker rc 双边维护** | `sw_list_configs_worker.py` 的 `EXIT_OK/TERMINAL/TRANSIENT/USAGE` 与 `sw_config_broker.py` 的 `WORKER_EXIT_OK/TERMINAL/TRANSIENT/LEGACY` 是**两边独立定义**；改 worker 端任一 rc 数值或新增 rc 时**必须同步 broker 端常量 + `_list_configs_via_com` rc 分流分支 + `prewarm_config_lists` batch entry-level 处理**。未来若需进一步解耦可抽 `adapters/solidworks/sw_worker_contract.py` 共享 module，但当前两文件距离短，重复定义的维护成本可接受 |
| **transient cache TTL 调优** | rev 4 删除（已砍 transient cache）|
| **swFileLoadError 数值表（rev 4 F-3 已用真值）** | `_TRANSIENT_OPENDOC_ERRORS = {4096, 8192, 16384}` 来自 SW SDK 2021/2022 公开文档 + plan task 0 校准。如生产观察某 errors 值实际呈现 transient 行为（例如 swFileLoadError_X 在某 SW 版本 retry 后成功率 > 50%），按 memory feedback 模式收证后扩充集合 |

---

## §11 推迟到 followup PR

### §11.1 重试风暴防御（rev 3 transient cache 设计 — rev 4 砍后推迟）

**Why 推迟**：rev 3 引入的 short-TTL transient cache 在 4 路 reviewer 审查中暴露 3 Critical + 7 Important 问题：
- multiprocessing 子进程独立 import → cache 各一份失效
- prewarm 写 L1 后不清同 key transient cache → mtime stale
- TTL 过期到 worker 返回 30s 窗口并发 spawn → 自我加剧
- 双进程 cache 互覆（无跨进程写锁）
- 用户改 sldprt 后 transient cache 无 mtime 校验仍 stale

**何时做**：实际观察到 BOM loop 同 sldprt 多次调用触发明显性能问题（如单 codegen 3-5 件 transient × 30s spawn 多次）后，**带可观测证据**开 followup PR。届时设计应满足：
- 跨 multiprocessing 进程一致语义（要么 L1 transient flag + TTL，要么文件锁）
- mtime 校验（用户改 sldprt 立即失效）
- 并发 spawn 序列化（threading.Lock 或 inflight flag）
- 完整 dry-run 状态生命周期审查 + multiprocessing 端到端测试

### §11.2 banner 恢复反馈（hostile B4）

**Why 推迟**：`_save_failure_warned` 单向 True → 用户改完权限后 process 内无"恢复"反馈。本 PR 接受作为已知 limitation；如用户实际报告"不知道修没修好"，加 `if _save_failure_warned: print("✓ cache 写入恢复正常", stderr); _save_failure_warned = False`。

### §11.3 banner 文案外行用户化（hostile C6）

**Why 推迟**：banner "请检查该路径权限后重启" 对外行用户语义模糊（重启什么）。本 PR 沿用 I-3 锁等待 banner 模板保持一致；followup 可考虑结合具体错误提供可执行指引（如检测 OneDrive 同步路径主动提示）。

### §11.4 双进程 cache 互覆防御（hostile D7）

**Why 推迟**：`os.replace` 仅保证 reader 不读 partial，不防 writer 互覆。罕见双 SW 实例场景下 A 进程 entries 可能被 B 覆盖。followup 加 `msvcrt.locking` 写锁（与 sw_config_broker.py 现有 `_project_file_lock` 风格一致）。

### §11.5 升级期端到端测试（hostile E9）

**Why 推迟**：当前测试矩阵覆盖单端（旧 worker batch / 新 worker batch）；缺旧 worker batch + 旧 worker 单件 fallback 联动 path 的端到端集成测试。该测试涉及 fixture 模拟两版本 worker 进程混跑，复杂度跨过 PR scope；followup 加 `test_legacy_worker_batch_skip_then_legacy_single_fallback_writes_transient`。

### §11.6 编码契约统一（hostile A2）

**Why 推迟**：subprocess 单件路径 `text=True, encoding="utf-8"` vs batch 路径 `text=False / .decode()` — 不一致但当前都能工作。中文路径乱码场景未观察；followup 加 invariant I17 约束并对齐两路径。

---

PR 创建后 self-review 与 user-review 发现的新问题登记此节，按 Critical / Important / Minor 分级，类比 `2026-04-26-sw-toolbox-config-list-cache-design.md` §11。

### §11.7 PR Review followup（占位）

（PR 开后 reviewer 发现的新问题填入此节）

---

## §12 覆盖率 enforce（rev 5 H 新增）

### §12.1 配置层

**`pyproject.toml`** 追加：

```toml
[tool.coverage.run]
source = ["adapters/solidworks"]
omit = [
    "*/tests/*",
    "*/__pycache__/*",
    "*/sw_*_helpers.py",  # 测试辅助文件不计
]
branch = true  # 覆盖率含分支覆盖

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if __name__ == \"__main__\":",
    "if TYPE_CHECKING:",
]
fail_under = 95  # 总覆盖率门槛
show_missing = true
skip_covered = false

[tool.pytest.ini_options]
addopts = [
    "--cov=adapters/solidworks",
    "--cov-report=term-missing",
    "--cov-fail-under=95",
]
```

### §12.2 CI gate 层

**`.github/workflows/ci.yml`**（或现有 workflow）的 `pytest` 步骤改为：

```yaml
- name: Run tests with coverage
  run: |
    pytest tests/ \
      --cov=adapters/solidworks \
      --cov-report=term-missing \
      --cov-report=xml \
      --cov-fail-under=95
- name: Upload coverage
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: coverage-report
    path: coverage.xml
```

### §12.3 硬约束

**spec 锁定**：本 PR 实施期间任何新代码行（broker / worker / cache.py）必须有 ≥1 测试覆盖。Phase 末校验：

```bash
pytest tests/test_sw_*.py --cov=adapters/solidworks --cov-fail-under=95
```

不通过 → 实施 task 不能 marked done；要么补测试，要么把未测代码砍掉（YAGNI）。

### §12.4 Per-module 覆盖率细化要求

| 模块 | 总覆盖率 | 分支覆盖率（branch） |
|------|---------|--------------------|
| `sw_list_configs_worker.py` | ≥ 95% | ≥ 90% |
| `sw_config_broker.py`（_list_configs_via_com + prewarm_config_lists 部分） | ≥ 95% | ≥ 90% |
| `sw_config_lists_cache.py` | ≥ 95% | ≥ 95%（小模块要求高）|

> rev 5 设计意图：**用测试覆盖率 anchor 实施正确性**，让 reviewer 抓不到"未测代码路径"。如果某分支无法测（如 `_list_configs_returning` 内部 `pythoncom.CoInitialize()` 失败），用 `# pragma: no cover` 显式标注 + 注释理由。
