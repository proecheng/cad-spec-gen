# 设计文档：Stage C 可观测性改进（capture worker stderr/exit_code）

**日期**: 2026-04-16
**状态**: 已批准
**范围**: Stage C COM 稳定性排障的副产物——可观测性补强

---

## 背景

在系统化调试 Stage C COM 失败（0/8 → 现 8/8）过程中，发现真正的代码路径在隔离测试下完全正常。之前 `artifacts/sw_b9/stage_c.json` 的 0/8 失败是**瞬态环境问题**（可能 SW 许可瞬态 / 启动时序 / 后台 COM 状态），无法复现。

但暴露了一个真正的工程缺陷：**Stage C 在 convert 失败时吞掉了 worker 的 stderr**，`stage_c.json` 的 per_target 只记录：

```json
{"index": 0, "sldprt": "...", "step_size": 0, "failed": true}
```

没有 exit_code、stderr 或任何错误分类。下次再故障时同样无法回溯，只能靠实时取证（手跑 worker）。这对瞬态故障极度不友好。

---

## 目标

Stage C 下次失败时，`stage_c.json` 的 per_target 条目直接包含诊断信息（exit_code、stderr 前缀、失败分类），无需再实时运行取证。

---

## 设计

### 1. `SwComSession` 新增 `last_convert_diagnostics` 属性

在 `adapters/solidworks/sw_com_session.py` 的 `SwComSession` 类：

```python
class SwComSession:
    def __init__(self) -> None:
        self._consecutive_failures = 0
        self._unhealthy = False
        self._lock = threading.Lock()
        self._last_convert_diagnostics: Optional[dict] = None

    @property
    def last_convert_diagnostics(self) -> Optional[dict]:
        """最近一次 convert_sldprt_to_step 的诊断信息（失败回溯用）。"""
        return self._last_convert_diagnostics
```

### 2. 诊断 dict 字段契约

```python
{
    "stage": str,           # 失败分类（见下）
    "exit_code": int | None, # subprocess 退出码；timeout/circuit_breaker 下为 None
    "stderr_tail": str,      # subprocess stderr 前 500 字符，成功或无 stderr 时为 ""
}
```

`stage` 的六种取值：

| stage | 含义 | exit_code | stderr_tail |
|---|---|---|---|
| `"success"` | 转换成功，STEP 写出并通过 validation | `0` | worker stderr（如 CloseDoc warning），前 500 字符 |
| `"subprocess_error"` | worker 非零退出（exit=2/3/4/64） | 实际 rc | 前 500 字符 |
| `"timeout"` | `subprocess.run` 超时 kill | `None` | `""` |
| `"validation_failure"` | worker 成功但 STEP 文件不符合 MIN_STEP_FILE_SIZE 或 magic | `0` | worker stderr，前 500 字符 |
| `"circuit_breaker_open"` | 熔断器已开，convert 被跳过 | `None` | `""` |
| `"unexpected_exception"` | `_do_convert` 抛未预期 exception | `None` | exception repr，前 500 字符 |

### 3. `_do_convert` 在每个失败/成功路径写入 diagnostics

在 `adapters/solidworks/sw_com_session.py`：

```python
def convert_sldprt_to_step(self, sldprt_path, step_out) -> bool:
    ...
    with self._lock:
        if self._unhealthy:
            self._last_convert_diagnostics = {
                "stage": "circuit_breaker_open",
                "exit_code": None,
                "stderr_tail": "",
            }
            log.info("熔断器已开：跳过 convert ...")
            return False
        ...

def _do_convert(self, sldprt_path: str, step_out: str) -> bool:
    ...
    try:
        proc = subprocess.run(...)
    except subprocess.TimeoutExpired:
        self._last_convert_diagnostics = {
            "stage": "timeout",
            "exit_code": None,
            "stderr_tail": "",
        }
        ...
        return False

    if proc.returncode != 0:
        self._last_convert_diagnostics = {
            "stage": "subprocess_error",
            "exit_code": proc.returncode,
            "stderr_tail": (proc.stderr or "")[:500],
        }
        ...
        return False

    if not self._validate_step_file(tmp_path):
        self._last_convert_diagnostics = {
            "stage": "validation_failure",
            "exit_code": proc.returncode,
            "stderr_tail": (proc.stderr or "")[:500],
        }
        ...
        return False

    self._last_convert_diagnostics = {
        "stage": "success",
        "exit_code": proc.returncode,
        "stderr_tail": (proc.stderr or "")[:500],  # 保留 warning
    }
    os.replace(tmp_path, step_out)
    return True
```

`convert_sldprt_to_step` 的 except 分支（捕获未预期异常）：

```python
except Exception as e:
    log.warning("convert 未预期异常: %s", e)
    self._last_convert_diagnostics = {
        "stage": "unexpected_exception",
        "exit_code": None,
        "stderr_tail": repr(e)[:500],
    }
    success = False
```

### 4. Stage C 读取 diagnostics 合并进 per_target

在 `tools/sw_b9_acceptance.py` 的 `stage_c_session_restart`：

```python
for i, t in enumerate(targets):
    sldprt = t["sldprt"]
    step_path = step_dir / f"{i:02d}_{Path(sldprt).stem}.step"
    ok = session.convert_sldprt_to_step(sldprt, str(step_path))
    diag = session.last_convert_diagnostics or {}

    entry = {
        "index": i,
        "sldprt": sldprt,
        "step_size": step_path.stat().st_size if step_path.exists() else 0,
    }
    if ok and step_path.exists() and step_path.stat().st_size > 1024:
        success += 1
    else:
        entry["failed"] = True
    entry.update(diag)  # 合并 stage/exit_code/stderr_tail
    per_target.append(entry)
```

### 5. 公共 API 变更（向后兼容）

- `SwComSession.convert_sldprt_to_step` 返回类型**不变**（仍 `bool`）
- 新增属性 `last_convert_diagnostics`（只读 property）
- 老调用方（`sw_toolbox_adapter.py` / `sw_warmup.py`）无需改动

---

## 测试计划

### 新增测试（`tests/test_sw_com_session_subprocess.py`）

1. **`test_diagnostics_on_success`**: 成功路径 → `stage == "success"`, `exit_code == 0`
2. **`test_diagnostics_on_subprocess_error`**: mock worker 返回 rc=3 + stderr → `stage == "subprocess_error"`, `exit_code == 3`, `stderr_tail` 含内容
3. **`test_diagnostics_on_timeout`**: mock worker 挂起触发 timeout → `stage == "timeout"`, `exit_code is None`
4. **`test_diagnostics_on_validation_failure`**: worker rc=0 但 tmp STEP 太小 → `stage == "validation_failure"`
5. **`test_diagnostics_on_circuit_breaker_open`**: 先触发熔断，再 convert → `stage == "circuit_breaker_open"`
6. **`test_diagnostics_on_unexpected_exception`**: mock `_do_convert` 抛异常 → `stage == "unexpected_exception"`
7. **`test_diagnostics_reset_on_new_call`**: 连续两次 convert，第二次的 diag 不保留第一次的内容

### 新增测试（`tests/` 中 Stage C 集成）

- 查现有 `tests/test_sw_b9*.py` 相关集成测试
- 如有 `stage_c_session_restart` 测试，扩展断言 per_target 含 `stage` 字段

---

## 验收标准

1. `uv run pytest tests/test_sw_com_session_subprocess.py -v` 全绿（含 7 条新测试）
2. `uv run pytest` 完整套件无退化
3. `uv run ruff check . && uv run ruff format --check .` 零告警
4. 人工触发一次 Stage C convert 失败（mock worker rc=3），`stage_c.json` 的 per_target 条目包含 `stage`、`exit_code`、`stderr_tail`

---

## YAGNI/取舍

- **不改** `convert_sldprt_to_step` 返回类型（避免破坏 adapter 和其他调用方）
- **不加** per-convert 日志文件落盘（`last_convert_diagnostics` 只保留最近一次，对 Stage C 的"每次读一次"模式足够）
- **不重构** 熔断器状态到诊断 dict 里（熔断是跨 convert 状态，诊断是单 convert 快照）
- **不增加** stderr 完整记录（500 字符足够诊断，worker stderr 通常只有一行错误）
