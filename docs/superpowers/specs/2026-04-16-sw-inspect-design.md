# sw-inspect 子命令 — 设计文档

- **日期**：2026-04-16
- **作者**：proecheng（Claude Code 协作）
- **状态**：design（待实施）
- **归属 phase**：Part 2c P2 Follow-up F-1
- **前置决策**：#34 / #35 / #36 / #37
- **实施计划**（待生成）：`docs/superpowers/plans/2026-04-16-sw-inspect.md`

---

## 1. 背景与动机

### 1.1 现状：诊断散点

SW 集成已走完 SW-A / SW-B / SW-B9 / SW-C / Part 2c P0–P2 五个大阶段，`main@a07d80f` 在装了 SolidWorks 2024 的开发机上能正确跑 Toolbox STEP 转换、材质桥接与 BOM 匹配。但**诊断 SW 状态的入口分散**，导致用户和后续开发者每次排障都要翻不同位置：

| 既有入口 | 位置 | 覆盖面 | 成本 |
|---|---|---|---|
| `cad_pipeline.py env-check` | `tools/hybrid_render/check_env.py:detect_environment` | 7 条 pipeline 并列（Blender / Gemini / fal / ComfyUI / engineering / SW），SW 段仅 ok/installed/version/com/pywin32/materials 数量/addin | 秒级 |
| `scripts/sw_spike_diagnose.py` | 非 CLI，直接 `python scripts/sw_spike_diagnose.py` | 6 层逐层 COM 探测（Python/pywin32/detect/CLSID/Dispatch/LoadAddIn）| Dispatch 冷启 ~15s |
| `cad_pipeline.py sw-warmup --dry-run` | `tools/sw_warmup.py:run_sw_warmup` | 列出会转换的 sldprt 目标，隐式检查 Toolbox index 可用 | < 1s |
| （无公开入口） | `adapters/solidworks/sw_toolbox_catalog.load_toolbox_index` | Toolbox 索引 fingerprint / 条目数 | < 100ms |
| （无公开入口） | `adapters/solidworks/sw_material_bridge.load_sw_material_bundle` | sldmat 解析 + preset/type_keywords | 秒级 |

用户问「SW 装没装？Toolbox 索引还活着吗？warmup 为什么这次挂了？」时，需要混合使用 3 种命令 + 读源码才能得到完整画面。

### 1.2 目标

提供**单一正式 CLI 入口** `cad_pipeline.py sw-inspect`，聚合上述所有诊断信息，覆盖两种使用场景：

- **日常速查**（默认，< 500ms）：只读、不启动 SW 进程，看装没装、索引健康度、材质/贴图数量、warmup 产物大小与上一次失败日志。
- **深度诊断**（`--deep`，冷启约 10–20s）：真跑 win32com.client.Dispatch + LoadAddIn，等价于把 `scripts/sw_spike_diagnose.py` 的 6 层探测收编为 CLI 子命令。

同时提供**机读契约**（`--json`）供 CI、未来 `sw-status` dashboard、Stage C 可观测性的 F-4b `timeout_rate` 消费。

### 1.3 非目标

- **不**替换 `env-check`。env-check 仍是多 pipeline 并列的"全局健康"入口；sw-inspect 是"SW 专属深度快照"。
- **不**删除 `scripts/sw_spike_diagnose.py`。保留为"开发机 REPL 友好的历史兜底工具"，内部重构成薄壳调共享内核。
- **不**新增 extras。`--deep` 依赖 pywin32 仍走 `[solidworks]` extra（决策 #37），在未装时给明确安装提示而非崩溃。
- **不**改动 `sw-warmup` / `env-check` / `sw_detect` 等现有模块的公开接口。

---

## 2. 决策总览

| # | 决策 | 来源章节 |
|---|---|---|
| D1 | 扁平单命令 + flag 矩阵：`sw-inspect [--deep] [--json]` | Q5 / §2.3 |
| D2 | 共享内核 `sw_probe.py`：纯函数、dataclass 返回、不 print / 不 sys.exit | Q2 / §2.1 |
| D3 | spike 脚本保留为薄壳，调 sw_probe；退出码体系与 sw-inspect **独立**（spike 沿用旧 1..4；sw-inspect 用新 0/1/2/3/4/64）| Q2 / §4.1 |
| D4 | `--deep` off 覆盖 6 条 probe：environment / pywin32 / detect / clsid / toolbox_index / materials / warmup；`--deep` on 追加 dispatch + loadaddin | Q4 / §3.1 |
| D5 | 材质仅点数量，不解析 sldmat XML；deep 模式未来可升级（本轮 YAGNI）| Q4 / §2.1 |
| D6 | 输出双模：默认彩色文本，`--json` 切 JSON；schema `version="1"` 起步，字段扩充不破坏 | Q3 / §3.1 |
| D7 | 退出码矩阵：0 全绿 / 1 warn / 2 静态 fail / 3 deep-COM fail / 4 deep-addin fail（保留坑位）/ 64 参数错 | §4.1 |
| D8 | `probe_dispatch` 用 `ThreadPoolExecutor` 做 60s 软超时；不走 subprocess 隔离（YAGNI，诊断工具非批跑）| §4.3 |
| D9 | 零破坏兼容：env-check / sw-warmup / sw_detect 全部不动；新增一个 subparser + 一个内核模块 + 一个 CLI 入口 | §6.1 |

---

## 3. 架构

### 3.1 分层

```
          cad_pipeline.py (CLI dispatcher, 已有)
          │
          ├── sw-warmup   ──► tools/sw_warmup.py          (已有, 不改)
          ├── sw-inspect  ──► tools/sw_inspect.py         (新增, CLI 格式化层)
          └── env-check   ──► tools/hybrid_render/...     (已有, 不改)
                                    │
                                    ▼
          adapters/solidworks/sw_probe.py                 (新增, 共享内核)
          │
          │   9 个 probe_* 纯函数（详见 §4.1）
          │
          ▲
          │
          scripts/sw_spike_diagnose.py                    (重写内部, 接口不变)
```

### 3.2 依赖约束

- `sw_probe` 依赖 `sw_detect` / `sw_toolbox_catalog`（仅 fingerprint 相关）/ 标准库 `winreg`（Windows）/ `win32com.client`（仅 deep 层）。
- `sw_probe` **不** 依赖 `sw_com_session`（避免把 subprocess-per-convert 会话管理耦合进诊断）。
- `sw_inspect.py` 只依赖 `sw_probe` + `argparse` + `json` + `sys`。
- `scripts/sw_spike_diagnose.py` 改造后只依赖 `sw_probe` + `traceback`。

---

## 4. 组件细节

### 4.1 `adapters/solidworks/sw_probe.py`（新增）

```python
@dataclass(frozen=True)
class ProbeResult:
    layer: str
    ok: bool
    severity: Literal["ok", "warn", "fail"]
    summary: str
    data: dict
    error: Optional[str] = None

# 静态层（--deep off/on 都调）
def probe_environment() -> ProbeResult: ...
def probe_pywin32() -> ProbeResult: ...
def probe_detect() -> ProbeResult: ...
def probe_clsid() -> ProbeResult: ...
def probe_toolbox_index_cache(cache_root: Path, toolbox_dir: Path) -> ProbeResult: ...
def probe_material_files(info: SwInfo) -> ProbeResult: ...
def probe_warmup_artifacts(cache_root: Path) -> ProbeResult: ...

# 深度层（仅 --deep 调）
def probe_dispatch(timeout_sec: int = 60) -> ProbeResult: ...
def probe_loadaddin(app) -> ProbeResult: ...
```

**设计不变量**：

- 任何 probe 函数都不抛异常（除 `KeyboardInterrupt/SystemExit`），捕获 `Exception` 转成 `severity="fail", error=str(exc)[:200]`。
- 非 Windows 平台：`probe_clsid` 返回 `severity="warn", summary="not applicable"`；`probe_pywin32` 返回 `severity="fail"`；deep 层在 argparse 层被拦（`--deep` + 非 Windows → exit 64）。
- `probe_dispatch` 用 `concurrent.futures.ThreadPoolExecutor(max_workers=1).submit(win32com.client.Dispatch, "SldWorks.Application").result(timeout=timeout_sec)`；超时 → `severity="fail", error="dispatch timeout after Xs"`。已知悬挂的 COM 后台线程无法强制 kill，这是本轮接受的妥协。
- `probe_dispatch` 返回的 `data` 里携带 `elapsed_ms`（F-4a baseline 会消费此字段）。

### 4.2 `tools/sw_inspect.py`（新增）

```python
def run_sw_inspect(args) -> int:
    """
    args: argparse.Namespace，含 args.deep: bool, args.json: bool
    返回 exit code，见 §5.1
    """
```

职责：
1. 按 `args.deep` 决定调用 7 条静态 probe 还是 9 条全量 probe。
2. 聚合所有 `ProbeResult` 到顶层 payload（见 §4.3）。
3. 按 `severity` 计算 `overall.exit_code`。
4. 按 `args.json` 分流到 JSON 输出或彩色文本输出。
5. 返回 exit code 给 `cad_pipeline.py` dispatcher。

### 4.3 JSON 契约（顶层）

```json
{
  "version": "1",
  "generated_at": "2026-04-16T14:23:05Z",
  "mode": "fast",
  "overall": {
    "ok": true,
    "severity": "ok",
    "exit_code": 0,
    "warning_count": 0,
    "fail_count": 0,
    "summary": "SolidWorks 2024 ready (toolbox 1844 parts, 3 sldmat files)"
  },
  "layers": {
    "environment":   { "ok": true, "severity": "ok", "summary": "...", "data": { ... } },
    "pywin32":       { ... },
    "detect":        { ... },
    "clsid":         { ... },
    "toolbox_index": { ... },
    "materials":     { ... },
    "warmup":        { ... },
    "dispatch":      { ... },
    "loadaddin":     { ... }
  }
}
```

**稳定保证**（`version="1"` 范围内）：

- 保证：顶层键名（5 个）、layer 名称、每层 `ok/severity/summary/data` 4 个键名语义不变。
- 不保证：`data.*` 子字段增加（消费方用 `.get()`）、`summary` 文案演化。
- `dispatch` / `loadaddin` 只在 `mode="deep"` 时出现；消费方判断 `layer in doc["layers"]` 再读。

### 4.4 每层 `data` 字段清单

详见 §3.2 原设计章节（brainstorming 已确认）。摘要：

- **environment**: os / python_version / python_bits / pid
- **pywin32**: available / module_path
- **detect**: installed / version_year / version / install_dir / sldmat_paths_count / textures_dir / p2m_dir / toolbox_dir / com_available / pywin32_available / toolbox_addin_enabled
- **clsid**: progid / clsid / registered
- **toolbox_index**: cache_path / exists / entry_count / fingerprint_current / fingerprint_cached / stale / size_bytes
- **materials**: sldmat_files / textures_categories / textures_total / p2m_files
- **warmup**: cache_root / step_files / step_size_bytes / error_log_last_line / error_log_mtime / lock_held / lock_pid
- **dispatch**（deep only）: dispatched / elapsed_ms / revision_number / visible_set_ok / exit_app_ok
- **loadaddin**（deep only）: attempts[{progid, return_code}] / loaded

### 4.5 severity 汇总规则

顶层 `overall.severity = max(fail, warn, ok)` over 所有已跑 layer，排序：`fail > warn > ok`。

```python
def _summarize(layers: dict) -> tuple[str, bool]:
    severities = [L["severity"] for L in layers.values()]
    if "fail" in severities: return "fail", False
    if "warn" in severities: return "warn", True
    return "ok", True
```

### 4.6 彩色文本渲染

复用 `check_env.py` 现有的 `[OK]/[WARN]/[FAIL]` 分段风格，**不引入新依赖**（colorama / rich）。每 layer 一段，顶层摘要一段，末尾一行 `Overall: <severity> (exit N)`。

### 4.7 `cad_pipeline.py` 改动

```python
# 靠近现有 sw-warmup 注册处新增：
p_sw_inspect = sub.add_parser(
    "sw-inspect",
    help="SolidWorks 环境/索引/材质/产物快速诊断（--deep 启动 COM）",
)
p_sw_inspect.add_argument("--deep", action="store_true",
    help="启动 win32com Dispatch + LoadAddIn（冷启约 10–20s，纯诊断用）")
p_sw_inspect.add_argument("--json", action="store_true",
    help="输出机读 JSON 而非彩色文本")

def cmd_sw_inspect(args):
    from tools.sw_inspect import run_sw_inspect
    return run_sw_inspect(args)

# _command_dispatch 映射表追加一行：
# "sw-inspect": cmd_sw_inspect,
```

### 4.8 `scripts/sw_spike_diagnose.py` 重写

保留：print 布局 / 失败立即早退 / 退出码 1..4 的语义。

去除：每层重复的 try/except 原生逻辑；全部委托给 `sw_probe.probe_*()`，主函数只做：

```python
def main() -> int:
    for probe_fn, expected_layer, exit_on_fail in [
        (probe_pywin32, "pywin32", 1),
        (probe_detect, "detect", 2),
        (probe_clsid, "clsid", 3),
        (probe_dispatch, "dispatch", 4),
        (probe_loadaddin, "loadaddin", None),  # 不早退
    ]:
        result = probe_fn() if probe_fn is not probe_loadaddin else probe_fn(app)
        _print(result)  # 彩色文本
        if result.severity == "fail" and exit_on_fail is not None:
            return exit_on_fail
    return 0
```

> spike 脚本的 shebang 注释追加一行："一般用户优先用 `cad_pipeline.py sw-inspect --deep`；本脚本保留为 SW-B0 时期 REPL 友好的历史兜底工具。"

---

## 5. 退出码

### 5.1 sw-inspect 退出码表

| exit | 语义 | 触发条件 |
|---|---|---|
| `0` | 全绿 | 所有 layer `severity="ok"` |
| `1` | warning | 至少一层 `severity="warn"`，无 `fail`（例：toolbox index stale / warmup_error.log 非空 / toolbox_addin_enabled=false）|
| `2` | fail：环境 | environment / pywin32 / detect / clsid 任一层 `fail`（这 4 层是 SW 可用性的硬前提；toolbox_index / materials / warmup 层**只产生 warn 不产生 fail**——它们描述"SW 周边状态"，不足以判定 SW 不可用）|
| `3` | fail：deep-COM | `--deep` 下 dispatch 层 `fail`（许可证 / 位数 / SW 独占 / 60s 超时）|
| `4` | fail：deep-addin | `--deep` 下 loadaddin 层 `fail`（保留坑位；当前 rc=3 降级为 warn，实际很少触发）|
| `64` | 参数错 | sw-inspect 自查 invalid flag 组合时 exit=64（BSD `sysexits.h` EX_USAGE，与 argparse 默认 2 区分）|

### 5.2 与 spike 脚本退出码的关系

**独立编号**，不互通：

| 工具 | 退出码语义 | 规范来源 |
|---|---|---|
| `cad_pipeline.py sw-inspect` | 0/1/2/3/4/64 见上表 | 本设计 |
| `scripts/sw_spike_diagnose.py` | 1 = pywin32 fail, 2 = detect fail, 3 = clsid fail, 4 = dispatch fail | 历史（SW-B0 spike）|

**理由**：spike 脚本是"调试辅助"，不进生产流程；sw-inspect 是正式 CLI，与 sw-warmup exit code 体系对齐（sw-warmup: 0/1/2/3，同样保留扩展坑位）。向后兼容优先。

### 5.3 `probe_dispatch` fail 时跳过 `probe_loadaddin`

loadaddin 需要 `app` 对象。dispatch fail → 无 app → loadaddin 被跳过，不出现在 `layers` 里，`mode="deep"` 但只输出 8 个 layer。消费方判断 `"loadaddin" in doc["layers"]` 再读。

### 5.4 每层失败不中断邻层

除 5.3 的特例外，前一层 fail 不阻止后续层继续跑。诊断工具的价值在于"一次跑完给全貌"，而非"看到第一个错就跑"。

---

## 6. 测试策略

### 6.1 测试层次

| 层 | 文件 | 覆盖 | 真 SW？ |
|---|---|---|---|
| 单元 | `tests/test_sw_probe.py` | 9 个 probe 函数的 happy / warn / fail 三态 | 否（mock）|
| CLI 契约 | `tests/test_sw_inspect_cli.py` | argparse 解析 / JSON schema / exit code 矩阵 / text 分段 | 否 |
| 脚本契约 | `tests/test_sw_spike_diagnose.py` | 薄壳调 sw_probe 的顺序 + 早退语义 | 否 |
| 真跑集成 | `tests/test_sw_inspect_real.py` | `@requires_solidworks` 标记；fast/deep 各 1 smoke | 是（CI skip）|
| pyproject 契约 | `tests/test_pyproject_contract.py` | 追加：sw-inspect 不引入新 extras；`--deep` 路径依赖 `[solidworks]` extra | 否 |

### 6.2 关键 mock 技巧

- **probe_pywin32 fail**：`monkeypatch.setitem(sys.modules, "win32com.client", None)` 触发 ImportError 分支。
- **probe_clsid fail**：`@pytest.mark.skipif(sys.platform != "win32")` 保护 + `monkeypatch.setattr(winreg, "OpenKey", lambda *a, **kw: raise FileNotFoundError)`。
- **probe_clsid 非 Windows**：跑在 Linux CI 时直接走 `severity="warn", summary="not applicable"` 分支（不 mock）。
- **probe_dispatch 超时**：`monkeypatch.setattr(concurrent.futures.Future, "result", lambda self, timeout: raise TimeoutError)`。
- **probe_toolbox_index_cache stale**：写两份不同 fingerprint 的 JSON fixture，断言 `stale=True`。
- **probe_warmup_artifacts lock_held**：tmp_path 下启 subprocess 持有 `msvcrt.locking`（Windows）/ `fcntl.flock`（Linux）；Linux CI 可跑。
- **probe_loadaddin**：mock `app.LoadAddIn` 返回 1 / 3 / 抛异常三种路径。

### 6.3 JSON 共享断言函数

```python
def _assert_inspect_json_shape(doc: dict):
    assert doc["version"] == "1"
    assert doc["mode"] in {"fast", "deep"}
    assert isinstance(doc["overall"]["exit_code"], int)
    assert set(doc["layers"].keys()) >= {
        "environment", "pywin32", "detect", "clsid",
        "toolbox_index", "materials", "warmup",
    }
    if doc["mode"] == "deep":
        assert "dispatch" in doc["layers"]
        # 注意：loadaddin 是可选存在的——probe_dispatch fail 时被跳过（见 §5.3），
        # 所以不能强制断言 "loadaddin" in layers；消费方应 .get() 容错。
    for name, layer in doc["layers"].items():
        assert {"ok", "severity", "summary", "data"} <= layer.keys()
        assert layer["severity"] in {"ok", "warn", "fail"}
```

所有测试复用此断言；未来升 `version="2"` 只改一处。

### 6.4 退出码参数化测试

```python
@pytest.mark.parametrize("probe_overrides, mode, expected_exit", [
    ({},                              "fast", 0),
    ({"warmup": WARN_ONLY},           "fast", 1),
    ({"pywin32": FAIL},               "fast", 2),
    ({"dispatch": FAIL},              "deep", 3),
    ({"loadaddin": FAIL},             "deep", 4),
])
def test_inspect_exit_code(probe_overrides, mode, expected_exit):
    ...
```

### 6.5 真跑测试（`@requires_solidworks`）

- `test_sw_inspect_fast_real_smoke`：断言 `overall.exit_code in {0, 1}` + `detect.data.version_year >= 2020` + total elapsed < 500ms（可选）。
- `test_sw_inspect_deep_real_smoke`：断言 `dispatch.ok == True` + `dispatch.data.elapsed_ms < 30_000` + total elapsed < 30s。

两条都加 `@pytest.mark.requires_solidworks`，Part 2c P1 的 `tests/conftest.py` 钩子自动 skip CI。

### 6.6 覆盖率目标

- `sw_probe.py` / `sw_inspect.py`：**≥ 95% line coverage**（诊断代码失败分支多，低于 95% 意味着失败路径漏测）。
- 每个 probe 函数至少 3 个测试：ok / warn / fail。

---

## 7. 性能指标

| 模式 | 目标耗时（装 SW 的机器）| 理由 |
|---|---|---|
| `--deep` off | < 500 ms | 静态层 + 文件系统轻 I/O（Toolbox index JSON 读 ~100ms + 材质目录 scandir）|
| `--deep` on | < 30 s | 冷启 Dispatch ~15s（spike 实测）+ Revision / Visible / ExitApp 秒级 + LoadAddIn 秒级 + 容错余量 |

基准数据由 §6.5 真跑测试记录，写入 `docs/superpowers/reports/sw-inspect-baseline-2026-04-16.md`（实施时生成）。

---

## 8. 向后兼容

| 既有入口 | 本次是否改动 | 说明 |
|---|---|---|
| `cad_pipeline.py sw-warmup` | **不动** | 接口、行为、exit code 全保留 |
| `cad_pipeline.py env-check` | **不动** | solidworks 段仍是宽口径简版；**不**加"建议改用 sw-inspect"提示（避免文案噪声）|
| `scripts/sw_spike_diagnose.py` | **重写内部**、**保留 CLI 接口** | `python scripts/sw_spike_diagnose.py` + `return 1..4` 不变；内部改调 `sw_probe.*` |
| `adapters/solidworks/sw_detect.py` / `sw_toolbox_catalog.py` / `sw_material_bridge.py` / `sw_com_session.py` | **不动** | 仅被 sw_probe 调用；不新增字段不改签名 |

**零破坏**：新增一个 subparser + 一个内核模块（`sw_probe.py`）+ 一个 CLI 入口（`tools/sw_inspect.py`）。

---

## 9. 文档更新

| 文件 | 更新点 |
|---|---|
| `README.md`（如有 CAD 管道 README） | 新增 `sw-inspect` 条目，与 `sw-warmup` 并列；一句话说明 + 示例 |
| `docs/superpowers/decisions.md` | 追加决策 #38（sw-inspect 作为正式入口；退出码体系与 spike 脚本独立）|
| `tools/cad_pipeline_agent_guide.md` | 新增 sw-inspect 用法段（agent 文档是 LLM 触发命令的主要说明源）|
| `docs/design/solidworks-integration-plan.md` | 存在则补"诊断入口"段指向 sw-inspect；不存在不创建 |

---

## 10. Packaging / Extras

- **不新增**任何 extras：
  - `--deep` off：所有 probe 都有非 Windows / 无 pywin32 降级分支，零新依赖。
  - `--deep` on：需要 pywin32，沿用决策 #37 的 `[solidworks]` extra。未装 pywin32 时 `probe_dispatch` 返回 `severity="fail", error="pywin32 not installed; install cad-spec-gen[solidworks]"`，exit=3，不崩。
- `tests/test_pyproject_contract.py` 追加断言：无新增 extras；sw-inspect 模块在不装 `[solidworks]` 时仍可 import（只是 `--deep` 会报 fail）。

---

## 11. 国际化

- 所有 summary / error 文案强制中文（CLAUDE.md 语言规范）。
- JSON key / layer 名称全 ASCII 英文（机读契约）。

---

## 12. 风险与妥协

| 风险 | 影响 | 本轮选择 | 升级路径 |
|---|---|---|---|
| `probe_dispatch` 悬挂时无法真 kill 后台 COM 线程 | CLI 看起来 Ctrl-C 生效但进程仍有残留线程直到整体退出 | 接受（ThreadPoolExecutor 软超时）| F-1 follow-up：`sw_inspect_worker.py` subprocess 隔离（参考 Part 2c P0 `sw_convert_worker.py`）|
| deep 模式的 real smoke 测试无法进 GitHub Ubuntu CI | 靠 `@requires_solidworks` skip，实机验证只能在开发者本机跑 | 接受 | F-1 follow-up：Windows self-hosted runner |
| sldmat XML 解析不在本轮覆盖 | materials 层只数文件不解析 preset / type_keywords 分布 | 接受（YAGNI）| 升级 `probe_material_files` 在 deep 模式调 `load_sw_material_bundle()` |
| JSON schema v1 的 `data` 字段扩充不破坏性、但**字段名冲突时**必须 bump v2 | 低概率 | 接受 | 若出现就按 `version="2"` 发布新契约 |

---

## 13. 实施范围（Plan Scope）

下一步 `superpowers:writing-plans` 要产出的实施计划覆盖：

1. `adapters/solidworks/sw_probe.py` 9 个 probe 函数 + `ProbeResult` dataclass
2. `tools/sw_inspect.py` CLI 入口 + 文本/JSON 双渲染
3. `cad_pipeline.py` subparser + dispatch 注册
4. `scripts/sw_spike_diagnose.py` 改造为薄壳
5. `tests/test_sw_probe.py` / `tests/test_sw_inspect_cli.py` / `tests/test_sw_spike_diagnose.py` / `tests/test_sw_inspect_real.py`
6. `tests/test_pyproject_contract.py` 追加
7. `docs/superpowers/decisions.md` 追加决策 #38
8. `tools/cad_pipeline_agent_guide.md` / README / solidworks-integration-plan.md 文档更新

按 TDD RED → GREEN → REFACTOR 执行，每任务 2–5 分钟粒度，含验收标准。

---

## 14. 参考

- `docs/superpowers/decisions.md`（#34 / #35 / #36 / #37）
- `docs/superpowers/plans/2026-04-14-sw-integration-phase-b-part2c-p1.md`（`@requires_solidworks` marker 机制）
- `docs/design/sw-com-session-threading-model.md`（dispatch 60s 超时依据）
- `scripts/sw_spike_diagnose.py`（层结构来源）
- `tools/hybrid_render/check_env.py`（文本渲染风格参照）

---

*— End of Design Document —*
