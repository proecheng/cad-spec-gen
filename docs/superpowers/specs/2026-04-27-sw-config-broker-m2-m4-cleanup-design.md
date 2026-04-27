# sw_config_broker §11 技术债清理 — M-2 + M-4 设计 spec

- **rev**: 2（user-review 抓 5 处 drift 后修订）
- **rev 1 → rev 2 修订记录**（user-review 触发，2026-04-27）：
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

#### §3.1.2 rev 2 目标合约

```
EXIT_OK        = 0  成功（stdout 含 configs JSON / batch JSON list）
EXIT_TERMINAL  = 2  重试仍失败（OpenDoc6 errors 是终态 / SLDPRT 损坏 / pywin32 未装 / 已知 terminal COM hresult）
EXIT_TRANSIENT = 3  重试可能成功（OpenDoc6 errors 是瞬时态 / DispatchEx COM 暂断 / 未识别异常兜底）
EXIT_USAGE     = 64 命令行参数错误（不变）
EXIT_LEGACY    = 4  ❌ 废弃，broker 收到旧 worker rc=4 当 transient 处理（向后兼容混跑场景）
```

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

#### §3.1.4 swFileLoadError 数值映射表（spec 锁定，未来扩充走单独 PR）

来源：SolidWorks SDK `swFileLoadError_e` 枚举。**仅列已知 transient + terminal 边界值**，未列入的归 terminal（保守 — 多数 SW 错误是 SLDPRT 内部状态问题）。

| errors 值 | 名称 | 分类 | 理由 |
|----------|------|------|------|
| 1 | `swGenericError` | terminal | 通用未知错，重试不变 |
| 2 | `swFileNotFoundError` | terminal | 文件不存在 |
| 32 | `swInvalidFileTypeError` | terminal | 文件类型错 |
| 64 | `swFutureVersion`（SLDPRT 比 SW 版本新） | terminal | 升级前重试不会变 |
| 128 | `swFileWithSameTitleAlreadyOpen` | **transient** | 同名文件已开（典型 batch 内并发或 UI 残留） |
| 256 | `swLowResourceError` | **transient** | 资源不足 / 内存压力 |
| 512 | `swNoDisplayData` | terminal | LDR 显示数据缺失 |
| 1024 | `swFileNotFoundWarning` | terminal | 同 2 |
| 2048 | `swFileRequiresRepair` | terminal | 需手动修复 |
| 4096 | `swApplicationBusy` | **transient** | SW 进程忙（典型 boot 中） |
| **null model（errors=0）** | `model is None` 但 errors=0 | terminal | 罕见边角，归 terminal 保守 |

**`_TRANSIENT_OPENDOC_ERRORS` 集合**：`{128, 256, 4096}`（未来扩充走单独 PR）。

> **数值表准确性免责声明**：上表是基于公开 SW SDK 文档的工程估算；如未来发现某 errors 值在生产环境实际呈现 transient 行为（or vice versa），按 memory feedback 模式收证后调整集合。
> 实施时若 `pywin32` constants 模块可读 swFileLoadError 枚举（如 `from win32com.client import constants`），优先用枚举名而非裸数字常量；若不可读则保留数字 + 注释枚举名。

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

_TRANSIENT_OPENDOC_ERRORS: frozenset[int] = frozenset({128, 256, 4096})  # spec §3.1.4
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
        pass  # pythoncom 不可用 → 不可能是 com_error 实例
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

#### §3.1.8 `_run_batch_mode` for 循环改造（修 Drift 4）

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
```

**整 batch rc 仍是 0**（外部错误如 stdin JSON parse 错走原 rc=64 不变）；分类信号通过 entry-level `exit_code` 字段透传给 broker。

### §3.2 Broker rc 分流

`adapters/solidworks/sw_config_broker.py` `_list_configs_via_com`（替换 L499-536）：

```
spawn worker
├─ subprocess.TimeoutExpired → log + return [] （★ 不 cache，transient）
├─ OSError → log + return [] （★ 不 cache，transient）
├─ rc=0 (EXIT_OK) → JSON parse → cache L2 = configs + return configs
│   └─ JSON parse 失败 → log + return [] （★ 不 cache，transient — worker stdout 损坏可能瞬时态）
├─ rc=2 (EXIT_TERMINAL) → cache L2 = [] + return []
├─ rc=3 (EXIT_TRANSIENT) → return [] （★ 不 cache）
├─ rc=4 (EXIT_LEGACY，旧 worker) → return [] （★ 不 cache，向后兼容当 transient 处理；spec §3.1.2）
└─ 其他 rc（未知值 / SIGKILL=-9 / 等） → return [] （★ 不 cache，保守归 transient）
```

**broker 端常量同步**：`adapters/solidworks/sw_config_broker.py` 顶部新增模块级常量与 worker 端语义对齐：

```python
# spec §3.1.2 — 与 worker 退出码合约同步
WORKER_EXIT_OK = 0
WORKER_EXIT_TERMINAL = 2
WORKER_EXIT_TRANSIENT = 3
WORKER_EXIT_LEGACY = 4  # 废弃，broker 收到当 transient 处理
```

**不变性**：rc=2 是**唯一**会污染 L2 cache 为 `[]` 的路径；其余失败都让下次调用重试。

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

broker `prewarm_config_lists` L615-628 改为：

```python
for entry in results:
    sldprt_path = entry.get("path", "")
    configs = entry.get("configs", [])
    rc = entry.get("exit_code", WORKER_EXIT_OK)  # 缺字段 = 旧 worker，默认 0 兼容
    mtime = cache_mod._stat_mtime(sldprt_path)
    size = cache_mod._stat_size(sldprt_path)
    if mtime is None or size is None:
        continue  # sldprt 文件已删 — 跳过不写（现状 L620-621 行为保留）
    key = _normalize_sldprt_key(sldprt_path)

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

**向后兼容两层（与 §3.2 单件路径语义严格对齐）**：
1. 缺 `exit_code` 字段当 `WORKER_EXIT_OK=0`（旧 worker stdout 格式不破 broker）
2. `WORKER_EXIT_LEGACY=4` + 未识别 rc 都走 transient 分支（不 cache，下次重试）— 跟单件路径 §3.2 `_list_configs_via_com` 完全一致

### §3.4 cache.py `_save_config_lists_cache` 异常下沉

`adapters/solidworks/sw_config_lists_cache.py` 引入模块级 flag + 包 try/except：

```python
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
| L628（prewarm batch 末尾 save） | 已在外层 except OSError 内 — 移除外层 OSError 捕获中的 save 关联 |

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

### Path 3 — Transient 失败（OpenDoc6 swApplicationBusy / DispatchEx COM 暂断）

```
broker._list_configs_via_com(p)
  L2 miss → L1 miss
  spawn worker(p)
  worker._list_configs_returning(p)
    → app.OpenDoc6(...) errors=4096 (swApplicationBusy)
    → OpenDocFailure(errors=4096) → _classify_worker_exception
    → e.errors=4096 ∈ _TRANSIENT_OPENDOC_ERRORS → return EXIT_TRANSIENT=3
  worker exit(3)
  broker: rc=3 → 不 cache + return []
  同 process 后续调用 = L2 miss → 重新 spawn worker → 第 2 次可能成功
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
| **I9** | 旧 worker（无 exit_code 字段）不破 broker | broker 解析 `entry.get("exit_code", WORKER_EXIT_OK)` 默认 0 |
| **I10** | 单件 + batch 路径"未识别 rc"语义严格一致（都归 transient 不 cache） | 两路径都走 `else: 不 cache` 兜底；spec §3.2 + §3.3 镜像 |
| **I11** | OpenDocFailure 是 RuntimeError 子类，不破现有 `except RuntimeError` 调用方 | spec §3.1.3 类定义 |
| **I12** | `_classify_worker_exception` 是单件 + batch 唯一分类入口（DRY） | spec §3.1.6 共享函数；§3.1.7 + §3.1.8 调用 |

---

## §6 边界 case

| Case | 处理 | 测试 |
|------|------|------|
| Edge 1 — sldprt mtime 改后旧 terminal cache 自动失效 | 现有 `_config_list_entry_valid` 已覆盖（mtime/size 比较） | 已有测试 |
| Edge 2 — worker 进程被 OS kill（rc=-9） | 落入"未知 rc 保守归 transient"分支 → 不 cache | `test_list_configs_unknown_rc_defaults_transient` |
| Edge 3 — worker print stdout 后才崩溃（rc!=0 但 stdout 有 JSON） | 保守归失败 — 不解析 partial stdout（现有逻辑保留） | 已有测试 |
| Edge 4 — `pythoncom` 模块在非 Windows 不存在 | worker 在 conftest mock；本 PR 不引入新 import 路径 | 现有 `_install_fake_win32com` 兼容 |
| Edge 5 — banner stderr write 本身失败（极罕见） | 不再处理 — sys.stderr 不可写说明环境已极端损坏 | 不测 |
| Edge 6 — 多线程并发 save（_save_failure_warned race） | flag 是 best-effort（多线程下偶尔出 2 次 banner 可接受）— 不加锁，对齐"最简实现"原则 | 不测 |
| Edge 7 — `OpenDocFailure(errors=0, model_was_null=True)` 边角 | `e.errors=0 ∉ _TRANSIENT_OPENDOC_ERRORS` → terminal；`model_was_null` 字段保留方便日志 / 未来扩展决策 | `test_classify_open_doc_failure_null_model_terminal` |
| Edge 8 — broker 跨升级期混跑：旧 worker 进程返 rc=4 | broker 视 rc=4 为 transient（不 cache，下次 prewarm 自然换新 worker） | `test_list_configs_legacy_rc4_treated_as_transient` |
| Edge 9 — `pythoncom` import 失败时分类 com_error 实例（理论不可能但代码路径要稳） | `_classify_worker_exception` 内部 `try: import pythoncom` 失败时 `pass` 走兜底 transient | `test_classify_worker_exception_without_pythoncom` |
| Edge 10 — batch 模式整批 stdin JSON parse 失败 | rc=64（不变）— 现有路径保留；broker 收到 rc=64 不命中任一 entry 分流分支 → batch 整体 fallback 到 _list_configs_via_com 单件路径（已有逻辑 L605-610 retain） | 已有测试 + `test_prewarm_batch_rc64_full_fallback` |

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
| `test_prewarm_batch_legacy_no_exit_code_field_treated_as_rc0` | mock batch stdout 缺 `exit_code` 字段 → 当 rc=0 写 cache（向后兼容） |
| `test_prewarm_batch_rc4_legacy_skipped_like_transient` | mock batch entry exit_code=4 → 跳过不写 entries（与单件路径一致） |
| `test_prewarm_batch_unknown_rc_skipped_like_transient` | mock batch entry exit_code=99 → 跳过不写 entries（I10 一致性） |
| `test_prewarm_batch_rc64_full_fallback` | mock subprocess rc=64（worker stdin JSON parse 错） → broker 不写 cache（Edge 10） |

### §7.3 扩展 `tests/test_sw_config_lists_cache.py`（已存在，扩 `TestSaveCache` 类）

文件已含 `TestModuleConstants` / `TestEmptyCache` / `TestSaveCache` 等类。本 PR 在 `TestSaveCache` 类内新增 4 测试 + module-level autouse fixture：

| 测试 | 断言 |
|------|------|
| `TestSaveCache.test_save_permission_error_first_call_writes_banner_to_stderr` | mock `Path.write_text` 抛 PermissionError → `capsys.readouterr().err` 含 "⚠ cache 文件" + path + "PermissionError" |
| `TestSaveCache.test_save_failure_second_call_no_banner_only_log_warning` | 同 process 内第 2 次 save 失败 → `capsys.err` 不含 banner；`caplog.records` 含 "重复失败" log.warning |
| `TestSaveCache.test_save_oserror_does_not_propagate_to_caller` | mock 抛 OSError → 函数返 None 不 raise |
| `TestSaveCache.test_save_oserror_subclass_disk_full_does_not_propagate` | mock 抛 `OSError(errno.ENOSPC)` 子类 → 同样静默自愈（不只 PermissionError）|

模块顶部加 autouse fixture：

```python
@pytest.fixture(autouse=True)
def _reset_save_failure_warned():
    import adapters.solidworks.sw_config_lists_cache as mod
    mod._save_failure_warned = False
    yield
    mod._save_failure_warned = False
```

**总测试增量**：约 **28 个新测试**（worker 12 + broker 12 + cache 4）。

---

## §8 文件清单

| 文件 | 改动 | 估算 LOC |
|------|------|---------|
| `adapters/solidworks/sw_list_configs_worker.py` | 新增 `OpenDocFailure(RuntimeError)` 子类异常（§3.1.3）；新增 `EXIT_OK/TERMINAL/TRANSIENT/USAGE` 常量 + `_TRANSIENT_OPENDOC_ERRORS` + `_TRANSIENT_COM_HRESULTS` + `_classify_worker_exception` 共享分类函数（§3.1.6）；`_open_doc_get_configs` 失败分支替换为 `raise OpenDocFailure(...)`（§3.1.3）；`_list_configs` 重写 try/except 走分类（§3.1.7）；`_run_batch_mode` for 循环 except 改调分类函数 + entry 加 `exit_code` 字段（§3.1.8） | +90 / -25 |
| `adapters/solidworks/sw_config_broker.py` | 顶部新增 `WORKER_EXIT_OK/TERMINAL/TRANSIENT/LEGACY` 常量（§3.2）；`_list_configs_via_com` rc 分流（替换 L499-536）；`prewarm_config_lists` batch 路径 entry-level rc 处理（替换 L615-628）；移除 L570-580 caller-side try/except | +50 / -35 |
| `adapters/solidworks/sw_config_lists_cache.py` | `_save_config_lists_cache` 包 try/except + 模块级 `_save_failure_warned` flag + banner（§3.4-§3.5） | +25 / -3 |
| `tests/test_sw_list_configs_worker.py` | **新增** 12 测试 | +320 / -0 |
| `tests/test_sw_config_broker.py` | 扩展 12 测试 | +280 / -0 |
| `tests/test_sw_config_lists_cache.py` | 扩展现有 `TestSaveCache` 类加 4 测试 + module 顶部 autouse fixture | +95 / -0 |
| `docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md` | §11 标 M-2 + M-4 closed + 引用本 spec | +5 / -2 |

**总估算**：~870 LOC 变化（695 测试 / 165 实现）。

---

## §9 Phase / Task 路线图（writing-plans 接口）

预设 **3 phase / 14 task** 量级（具体粒度 plan 阶段细化）：

### Phase 1 — Worker 端分类基建 + rc 合约（6 task）

1. 写测试：`test_sw_list_configs_worker.py` 12 测试 全部 RED（含 `OpenDocFailure` 子类异常 / `_classify_worker_exception` / `_list_configs` rc 0/2/3 / `_run_batch_mode` entry exit_code 矩阵）
2. 实现：定义 `class OpenDocFailure(RuntimeError)` 含 `errors: int / warnings: int / model_was_null: bool` 字段（§3.1.3）；`_open_doc_get_configs` L33-39 改抛 `OpenDocFailure(...)`
3. 实现：`EXIT_OK/TERMINAL/TRANSIENT/USAGE` 常量 + `_TRANSIENT_OPENDOC_ERRORS = frozenset({128, 256, 4096})` + `_TRANSIENT_COM_HRESULTS = frozenset({-2147023170, -2147418113, -2147023174})`
4. 实现：`_classify_worker_exception(e)` 共享函数（§3.1.6）—— `OpenDocFailure → errors 数值查 `_TRANSIENT_OPENDOC_ERRORS` / `ImportError → terminal` / `pythoncom.com_error → hresult 查 `_TRANSIENT_COM_HRESULTS` / 兜底 transient`
5. 实现：`_list_configs` 重写（§3.1.7） + `_run_batch_mode` for 循环 except 改调 `_classify_worker_exception` + entry 加 `exit_code` 字段（§3.1.8）
6. 验证：12 测试全绿（GREEN）+ ruff/mypy 通过

### Phase 2 — Broker rc 分流 + batch 协议升级（5 task）

7. 写测试：`test_sw_config_broker.py` 12 新测试 全部 RED（含 rc=0/2/3/4/64/99/TimeoutExpired/OSError + batch 4 entry-level 路径）
8. 实现：broker 顶部新增 `WORKER_EXIT_OK/TERMINAL/TRANSIENT/LEGACY` 常量（§3.2）
9. 实现：`_list_configs_via_com` rc 分流（替换 L499-536）—— rc=0 cache configs / rc=2 cache [] / rc=3+rc=4+未知 不 cache / TimeoutExpired+OSError 不 cache
10. 实现：`prewarm_config_lists` batch entry-level rc 处理（替换 L615-628）—— 复用同一组 WORKER_EXIT_* 常量；rc=0/2 写 entries（不同 configs 值），rc=3/4/未知 跳过不写（§3.3 与 §3.2 严格对称 / I10）
11. 验证：12 测试全绿 + ruff/mypy + `pytest tests/test_sw_*.py` 全跑不 regression

### Phase 3 — cache.py save 自愈 + caller 清理 + 文档（3 task）

12. 写测试：`tests/test_sw_config_lists_cache.py` `TestSaveCache` 类加 4 测试 + module 顶部 autouse fixture（全 RED）
13. 实现：`_save_config_lists_cache` try/except OSError + 模块级 `_save_failure_warned` + banner（§3.4 + §3.5）
14. 实现：移除 broker.py L570-580 caller-side try/except；`docs/.../2026-04-26-sw-toolbox-config-list-cache-design.md` §11 标 M-2 + M-4 closed + 引用本 spec；4 测试全绿；端到端跑 `pytest tests/test_sw_*.py` 不 regression

每 phase 末跑 quality reviewer 抓系统视角问题（命名一致性 / 模块边界 / 文档同步）；按 memory `feedback_cp_batch_quality_review.md` phase 末整体 reviewer 优于 per-task。

---

## §10 引用与上下文

- **memory `project_session38_handoff.md`** — subagent-driven 全流程 (implementer / spec / quality / final reviewer 串联)
- **memory `feedback_cp_batch_quality_review.md`** — phase 末整体 quality reviewer 优于 per-task
- **memory `feedback_external_subsystem_safety_valve.md`** — `CAD_SW_BROKER_DISABLE` env 安全阀已存在；本 PR 无新 env
- **spec `2026-04-26-sw-config-broker-i2-i3-fix-design.md` §3** — banner 风格模板（与 I-3 锁等待 banner 同模板）
- **spec `2026-04-25-sw-toolbox-llm-config-broker-design.md` §5.3** — invariant 1 「prewarm 永不抛打断 codegen」

---

## §11 待 review-followup 占位

PR 创建后 self-review 与 user-review 发现的新问题登记此节，按 Critical / Important / Minor 分级，类比 `2026-04-26-sw-toolbox-config-list-cache-design.md` §11。

（占位）
