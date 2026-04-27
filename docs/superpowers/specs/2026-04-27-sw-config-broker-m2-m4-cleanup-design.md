# sw_config_broker §11 技术债清理 — M-2 + M-4 设计 spec

- **rev**: 1（初稿，待 self-review 与 user-review）
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

`adapters/solidworks/sw_list_configs_worker.py` 入口建立 rc 合约：

```
EXIT_OK       = 0  成功，stdout 含 configs JSON
EXIT_TERMINAL = 2  重试仍失败（文件不存在 / SLDPRT 损坏 / SW 未装 / com_error 已知 terminal hresult）
EXIT_TRANSIENT = 3 重试可能成功（com_error 已知 transient hresult / 未知异常默认归此类）
```

#### 异常 → rc 映射规则

| 异常类型 | 退出码 | 理由 |
|---------|------|------|
| `FileNotFoundError` / `IsADirectoryError` | 2 | 文件不存在/目录错位 — 重试结果不变 |
| `PermissionError` | 3 | 文件锁典型场景 = SW UI 同时打开 SLDPRT；用户关 UI 后重试可能成功 → 归 transient（不 cache 防 mtime 未变 + 锁释放后永久错的死锁） |
| `pythoncom.com_error` hresult ∈ `_TRANSIENT_COM_HRESULTS` | 3 | 已知瞬时类（RPC 暂断 / 调用瞬时失败） |
| `pythoncom.com_error` 其他 hresult | 2 | 未识别但是 COM 层，保守归 terminal — COM 错典型来自 SW / SLDPRT 内部状态问题 |
| 其他 `Exception`（兜底） | 3 | 保守归 transient — 典型来自 worker 自身代码 bug，不应永久打废 cache；真 terminal 类型应显式列举到上面分支 |

**「双向保守」语义注释**：COM 层未识别 hresult 归 terminal，非 COM 层未识别 Exception 归 transient — 看似矛盾，实则各自域内合理。COM 错的根因在 SW/SLDPRT 上，重试不会改变；Python 层异常的根因在 worker 代码上，需要保留重试机会以免被自身 bug 永久污染 cache。

#### `_TRANSIENT_COM_HRESULTS` 初始集合（spec 锁定，未来扩充走单独 PR）

| HRESULT | 名称 | 描述 |
|---------|------|------|
| `-2147023170` | `RPC_E_DISCONNECTED` | RPC 服务器不可用（COM 服务器进程退出） |
| `-2147418113` | `E_FAIL` | 通用失败 — 保守归 transient |
| `-2147023174` | `RPC_S_CALL_FAILED` | 调用瞬时中断 |

未来加新 hresult 走单独 PR + memory feedback 记录证据。

### §3.2 Broker rc 分流

`adapters/solidworks/sw_config_broker.py` `_list_configs_via_com`（替换 L499-536）：

```
spawn worker
├─ subprocess.TimeoutExpired → log + return [] （★ 不 cache，transient）
├─ OSError → log + return [] （★ 不 cache，transient）
├─ rc=0 → cache L2 = configs + return configs
├─ rc=EXIT_TERMINAL → cache L2 = [] + return []
├─ rc=EXIT_TRANSIENT → return [] （★ 不 cache）
└─ 其他 rc（未知 / 旧版 worker） → return [] （★ 不 cache，保守归 transient）
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

```
for entry in results:
    rc = entry.get("exit_code", 0)  # 缺字段 = 旧 worker，默认 0 兼容
    if rc == EXIT_TERMINAL:
        # 写 [] 防重试（与 _list_configs_via_com rc=2 路径对称）
        cache["entries"][key] = {"mtime": mtime, "size": size, "configs": []}
    elif rc == EXIT_TRANSIENT:
        # 跳过不写 — 下次 prewarm 重试此 sldprt
        continue
    else:  # rc=0 或未识别（向后兼容）
        cache["entries"][key] = {"mtime": mtime, "size": size, "configs": configs}
```

**向后兼容**：缺 `exit_code` 字段当 0（让旧 worker stdout 格式不破 broker）。

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

### Path 2 — Terminal 失败（SLDPRT 损坏 / 文件不存在）

```
broker._list_configs_via_com(p)
  L2 miss → L1 miss
  spawn worker(p)
  worker: FileNotFoundError → exit(2)
  broker: rc=2 → cache L2 = [] + return []
  同 process 后续调用 = L2 hit → return [] 不再 spawn ✓
```

### Path 3 — Transient 失败（COM RPC 暂时失败）

```
broker._list_configs_via_com(p)
  L2 miss → L1 miss
  spawn worker(p)
  worker: pythoncom.com_error hresult=-2147023170 → exit(3)
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
| **I9** | 旧 worker（无 exit_code 字段）不破 broker | broker 解析 `entry.get("exit_code", 0)` 默认 0 |

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

---

## §7 测试策略

### §7.1 新增 `tests/test_sw_list_configs_worker.py`（worker 端 unit test）

复用 `tests/test_sw_convert_worker.py` 模板（"全 mock pythoncom + Dispatch，不依赖真实 SW"）。

| 测试 | 断言 |
|------|------|
| `test_worker_success_returns_rc0_with_configs_json` | mock `_list_configs` 返 ["A","B"] → rc=0；stdout 解析为 ["A","B"] |
| `test_worker_file_not_found_returns_rc2_terminal` | mock 抛 FileNotFoundError → rc=2；stderr 含 "file-layer" |
| `test_worker_permission_error_returns_rc3_transient` | mock 抛 PermissionError → rc=3（防 SW UI 锁场景永久 miscache） |
| `test_worker_com_error_transient_hresult_returns_rc3` | mock `pythoncom.com_error` hresult=-2147023170 → rc=3 |
| `test_worker_com_error_terminal_hresult_returns_rc2` | mock `pythoncom.com_error` hresult=-2147467259（catastrophic） → rc=2 |
| `test_worker_unknown_exception_defaults_transient_rc3` | mock 抛 ValueError → rc=3；stderr 含 "unknown" |
| `test_classify_com_error_table_lookup` | 直接单测 `_classify_com_error(mock_com_error_with_hresult)` |

### §7.2 扩展 `tests/test_sw_config_broker.py`

| 测试 | 断言 |
|------|------|
| `test_list_configs_rc2_caches_empty_list_to_prevent_retry` | mock subprocess rc=2 → 第 1 次返 []；**第 2 次同 sldprt subprocess.run.call_count == 1**（L2 hit） |
| `test_list_configs_rc3_does_not_cache_for_retry` | mock subprocess rc=3 → 第 1 次返 []；**第 2 次同 sldprt subprocess.run.call_count == 2**（重 spawn） |
| `test_list_configs_timeout_treated_as_transient_no_cache` | TimeoutExpired → 不 cache；第 2 次重试 |
| `test_list_configs_oserror_treated_as_transient_no_cache` | OSError → 不 cache；第 2 次重试 |
| `test_list_configs_unknown_rc_defaults_transient` | mock rc=99 → 不 cache；第 2 次重试 |
| `test_prewarm_batch_mixed_rc_writes_terminal_skips_transient` | mock batch stdout 含 3 entry 混合 exit_code → cache entries 写 rc=0 与 rc=2 项，跳过 rc=3 项 |
| `test_prewarm_batch_legacy_no_exit_code_field_treated_as_rc0` | mock batch stdout 缺 `exit_code` 字段 → 当 rc=0 写 cache（向后兼容） |

### §7.3 扩展 `tests/test_sw_config_lists_cache.py`（若不存在则新建）

| 测试 | 断言 |
|------|------|
| `test_save_permission_error_first_call_writes_banner_to_stderr` | mock open 抛 PermissionError → capsys.readouterr().err 含 "⚠ cache 文件" + path + "PermissionError" |
| `test_save_failure_second_call_no_banner_only_log_warning` | 同 process 内第 2 次 save 失败 → capsys.err 不含 banner；caplog 含 "重复失败" log.warning |
| `test_save_oserror_does_not_propagate_to_caller` | mock 抛 OSError → 函数返 None 不 raise |
| `test_save_failure_warned_flag_resets_per_test` | autouse fixture 验证 cross-test isolation |

**总测试增量**：约 **18 个新测试**（worker 7 + broker 7 + cache 4）。

---

## §8 文件清单

| 文件 | 改动 | 估算 LOC |
|------|------|---------|
| `adapters/solidworks/sw_list_configs_worker.py` | 入口加 try/except + rc 合约 + `_classify_com_error` + `_TRANSIENT_COM_HRESULTS`；`--batch` 模式 stdout entry 加 `exit_code` 字段 | +60 / -10 |
| `adapters/solidworks/sw_config_broker.py` | `_list_configs_via_com` rc 分流（替换 L499-536）；`prewarm_config_lists` batch 路径 entry-level rc 处理（替换 L615-628）；移除 L570-580 caller-side try/except | +40 / -30 |
| `adapters/solidworks/sw_config_lists_cache.py` | `_save_config_lists_cache` 包 try/except + `_save_failure_warned` flag + banner | +25 / -3 |
| `tests/test_sw_list_configs_worker.py` | **新增** 6 测试 | +180 / -0 |
| `tests/test_sw_config_broker.py` | 扩展 7 测试 | +180 / -0 |
| `tests/test_sw_config_lists_cache.py` | 扩展（或新增）4 测试 + autouse fixture | +90 / -0 |
| `docs/superpowers/specs/2026-04-26-sw-toolbox-config-list-cache-design.md` | §11 标 M-2 + M-4 closed + 引用本 spec | +5 / -2 |

**总估算**：~580 LOC 变化（450+ 测试 / 130 实现）。

---

## §9 Phase / Task 路线图（writing-plans 接口）

预设 **3 phase / 11 task** 量级（具体粒度 plan 阶段细化）：

### Phase 1 — Worker 端 rc 合约（4 task）

1. 写测试：`test_sw_list_configs_worker.py` 7 测试（先全 fail / RED）
2. 实现：worker 入口 try/except + `EXIT_OK/TERMINAL/TRANSIENT` 常量 + `_TRANSIENT_COM_HRESULTS`
3. 实现：`_classify_com_error` 辅助函数 + PermissionError → rc=3 分支
4. 验证：7 测试全绿（GREEN）+ ruff/mypy 通过

### Phase 2 — Broker rc 分流 + batch 协议升级（4 task）

5. 写测试：`test_sw_config_broker.py` 7 测试（先全 fail）
6. 实现：`_list_configs_via_com` rc 分流（rc=0/2/3 + TimeoutExpired + OSError + 未知 rc）
7. 实现：`prewarm_config_lists` batch entry-level rc 处理（含向后兼容 default 0）
8. 实现：worker `--batch` stdout schema 加 `exit_code` 字段
9. 验证：7 测试全绿 + ruff/mypy + 端到端 `pytest tests/test_sw_*.py` 不 regression

### Phase 3 — cache.py save 自愈 + caller 清理 + 文档（3 task）

10. 写测试：`test_sw_config_lists_cache.py` 4 测试 + autouse fixture（先全 fail）
11. 实现：`_save_config_lists_cache` try/except + `_save_failure_warned` + banner
12. 实现：移除 broker.py L570-580 caller-side try/except；§11 spec 更新标 M-2/M-4 closed；4 测试全绿

每 phase 末跑 quality reviewer 抓系统视角问题（命名一致性 / 模块边界 / 文档同步）。

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
