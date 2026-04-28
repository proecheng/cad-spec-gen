# sw-inspect 子命令 — 设计文档

> 历史文档提示（2026-04-28）：当前模型库、SolidWorks 接入与几何质量执行依据已合并到
> `docs/PARTS_LIBRARY.md`。本文保留为 sw-inspect 设计记录；若路径、命名或文档入口与
> `docs/PARTS_LIBRARY.md` 冲突，以 `docs/PARTS_LIBRARY.md` 为准。

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

- `sw_probe` 依赖：
  - `adapters.solidworks.sw_detect`（`detect_solidworks` / `_reset_cache`）
  - `adapters.solidworks.sw_toolbox_catalog`（`get_toolbox_cache_root` / `get_toolbox_index_path` / `load_toolbox_index` / **私有** `_compute_toolbox_fingerprint` —— 封装破坏但单一消费者，接受；备选是把该函数升 public，本轮不做）
  - `parts_resolver.load_registry`（加载 `parts_library.default.yaml` 以获取 `solidworks_toolbox` 段）
  - 标准库 `winreg`（Windows）、`win32com.client`（仅 deep 层）、`concurrent.futures`、`msvcrt`/`fcntl`（平台分支）
- `sw_probe` **不** 依赖 `sw_com_session`（避免把 subprocess-per-convert 会话管理耦合进诊断）。
- `tools/sw_inspect.py` 依赖 `sw_probe` + `argparse` + `json` + `sys` + `parts_resolver.load_registry`。
- `scripts/sw_spike_diagnose.py` 改造后只依赖 `sw_probe` + `traceback`。

### 3.3 与现有管道的数据流融合（函数/变量/路径对齐）

**这是本 spec 与实际代码的接口契约**——所有 probe 函数必须沿用下表列出的既有 API，**不得**新造同义 helper。

| probe 函数 | 调用的既有 API | 变量/路径来源 | 现有消费者（做法参照）|
|---|---|---|---|
| `probe_detect` | `sw_detect._reset_cache()` 后 `sw_detect.detect_solidworks() -> SwInfo` | 无输入 | `tools/hybrid_render/check_env.py:163` |
| `probe_toolbox_index_cache` | `sw_toolbox_catalog.get_toolbox_cache_root(sw_cfg)`、`.get_toolbox_index_path(sw_cfg)`、`.load_toolbox_index(index_path, toolbox_dir)`、`._compute_toolbox_fingerprint(toolbox_dir)` | `sw_cfg = load_registry().get("solidworks_toolbox", {})`；`toolbox_dir = Path(info.toolbox_dir)` | `tools/sw_warmup.py:360-364` |
| `probe_material_files` | `SwInfo.sldmat_paths`、`SwInfo.textures_dir`、`SwInfo.p2m_dir`（三者均来自 `detect_solidworks()`）| `info = <probe_detect 已跑过的 SwInfo>`（为避免重复探测，sw_inspect 把 SwInfo 实例从 probe_detect 透传给 probe_material_files）| `tools/hybrid_render/check_env.py:170` 的 `len(sw.sldmat_paths)` |
| `probe_warmup_artifacts` | `Path.home() / ".cad-spec-gen"` 根目录 + `sw_toolbox_catalog.get_toolbox_cache_root(sw_cfg)` 子目录 | `sw_warmup.py:222-229` 的两个 `_default_*_path()` 私有函数是单行常量，sw_probe 直接重复该常量（不 import 私有函数）| `tools/sw_warmup.py:222-229、392` |
| `probe_dispatch` | `win32com.client.GetObject("SldWorks.Application")` 先查 → `win32com.client.Dispatch(...)` | 无 config 依赖 | `scripts/sw_spike_diagnose.py:85-114`（现行逻辑）|
| `probe_loadaddin` | 内部 `win32com.client.Dispatch` + `app.LoadAddIn("SwToolbox.1")` / `"SwToolbox"` | 无 config 依赖 | `scripts/sw_spike_diagnose.py:117-130`（现行逻辑）|

**路径常量（与实际代码对齐；spec 之前写的都要替换）**：

| 逻辑名 | 实际路径 | 来源 |
|---|---|---|
| home | `Path.home() / ".cad-spec-gen"` | 全局约定 |
| lock 文件 | `Path.home() / ".cad-spec-gen" / "sw_warmup.lock"` | `tools/sw_warmup.py:224` |
| error log | `Path.home() / ".cad-spec-gen" / "sw_warmup_errors.log"` | `tools/sw_warmup.py:229` |
| index json（默认）| `Path.home() / ".cad-spec-gen" / "sw_toolbox_index.json"` | `sw_toolbox_catalog.py:70` |
| STEP cache（默认）| `Path.home() / ".cad-spec-gen" / "step_cache" / "sw_toolbox"` | `sw_toolbox_catalog.py:56` |

**环境变量覆盖链**（probe 必须支持，否则与 sw-warmup 行为不一致）：

| env var | 作用 | 优先级 |
|---|---|---|
| `CAD_SPEC_GEN_SW_TOOLBOX_CACHE` | 覆盖 STEP cache 根 | yaml `cache` > env > 默认 |
| `CAD_SPEC_GEN_SW_TOOLBOX_INDEX` | 覆盖 index json 路径 | env > 默认 |

**注**：`CAD_SPEC_GEN_HOME` 是 `tests/conftest.py` 的测试隔离钩子（用于 monkeypatch `Path.home()`），**生产代码不读**它；probe 沿用 `Path.home()` 即可被 fixture 正确隔离。

### 3.4 Toolbox Index 结构（实施者必读）

`load_toolbox_index` 返回的 dict 真实结构（`sw_toolbox_catalog._make_index_envelope` 定义）：

```python
{
    "toolbox_fingerprint": str,   # SHA1 hex，或 "unavailable"（非 Windows / 读失败）
    "standards": {
        "GB": {
            "bolts and studs": [SwToolboxPart, SwToolboxPart, ...],
            "nuts": [...],
            ...
        },
        "ISO": { ... },
        "DIN": { ... },
        ...  # 实际有哪些标准完全取决于 toolbox_dir 扫描结果，无硬编码白名单
    }
}
```

- **`entry_count`** 字段**不存在**，probe 自行聚合：`sum(len(sub) for std in idx["standards"].values() for sub in std.values())`
- **`by_standard`** 也是自行聚合：`{std: sum(len(sub) for sub in std_dict.values()) for std, std_dict in idx["standards"].items()}`——**key 列表来自真实扫描**，不硬编码 4 键（ME-1 原措辞"至少含 GB/DIN/ISO/ANSI 4 键"过于强硬，应改为"出现哪些标准就列哪些"）
- **stale 判断**：`cached_fp = idx.get("toolbox_fingerprint", ""); current_fp = _compute_toolbox_fingerprint(toolbox_dir); stale = (cached_fp != current_fp) and cached_fp != "unavailable" and current_fp != "unavailable"`

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
    hint: Optional[str] = None      # 3D-1：用户可采取的下一步行动（中文），
                                    # 文本模式有则缩进打印；JSON schema v1 可选字段

# 静态层（--deep off/on 都调）
def probe_environment() -> ProbeResult: ...
def probe_pywin32() -> ProbeResult: ...
def probe_detect() -> ProbeResult: ...                  # SAR-2：每次内部调
                                                        # _reset_cache() 强制重测
def probe_clsid() -> ProbeResult: ...
def probe_toolbox_index_cache(sw_cfg: dict, info: SwInfo) -> ProbeResult:
    """
    参数：
      sw_cfg — parts_library.default.yaml 的 `solidworks_toolbox` 段；
               由调用方通过 `parts_resolver.load_registry().get("solidworks_toolbox", {})` 获取
      info — 已 probe_detect 过的 SwInfo 实例（避免重复检测）
    内部：
      index_path = get_toolbox_index_path(sw_cfg)
      toolbox_dir = Path(info.toolbox_dir)
      idx = load_toolbox_index(index_path, toolbox_dir)
      entry_count = 聚合 idx["standards"]
      by_standard = 聚合 idx["standards"]（key 来自真实扫描，无硬编码白名单）
      stale = cached_fp != current_fp（两端均非 "unavailable"）
    """

def probe_material_files(info: SwInfo) -> ProbeResult:
    """参数：已跑过的 SwInfo。只数 len(info.sldmat_paths) / textures 目录下 category
    子目录数 + 贴图总数 / p2m 目录下 .p2m 文件数；不解析 XML。"""

def probe_warmup_artifacts(sw_cfg: dict) -> ProbeResult:
    """
    参数：sw_cfg（同 probe_toolbox_index_cache），用于解析 STEP cache 根
    内部路径：
      home = Path.home() / ".cad-spec-gen"
      lock_path = home / "sw_warmup.lock"
      error_log_path = home / "sw_warmup_errors.log"
      step_cache_root = get_toolbox_cache_root(sw_cfg)  # 默认 home/step_cache/sw_toolbox
    SA-2：lock 用 non-blocking try-acquire + immediate release；不与 sw-warmup 争锁。
    SAR-3：step_files 统计降级——若 scandir 递归出 > 5000 文件，只报 count 跳过 size。
    """

# 深度层（仅 --deep 调）
def probe_dispatch(timeout_sec: int = 60) -> ProbeResult:
    """3D-2：先 win32com.client.GetObject("SldWorks.Application") 判断 SW 是否已运行；
    已运行 → 附着但不 ExitApp（保护用户未保存工作），severity=warn。
    未运行 → 正常 Dispatch + Visible=False + ExitApp。"""

def probe_loadaddin() -> ProbeResult:
    """SAR-1：无参数；内部自行 Dispatch 附着（deep 模式已付冷启成本，
    再附着是秒级）。与 probe_dispatch 解耦，保持"每层独立 / 签名对称"。"""
```

**设计不变量**：

- 任何 probe 函数都不抛异常（除 `KeyboardInterrupt/SystemExit`），捕获 `Exception` 转成 `severity="fail", error=str(exc)[:200]`。
- 非 Windows 平台：`probe_clsid` 返回 `severity="warn", summary="not applicable"`；`probe_pywin32` 返回 `severity="fail"`；deep 层在 argparse 层被拦（`--deep` + 非 Windows → exit 64）。
- `probe_dispatch` 用 `concurrent.futures.ThreadPoolExecutor(max_workers=1).submit(win32com.client.Dispatch, "SldWorks.Application").result(timeout=timeout_sec)`；超时 → `severity="fail", error="dispatch timeout after Xs"`。已知悬挂的 COM 后台线程无法强制 kill，这是本轮接受的妥协。
- `probe_dispatch` 返回的 `data` 里携带 `elapsed_ms`（F-4a baseline 会消费此字段）。
- **SAR-2（进程级缓存隔离）**：`probe_detect` 内部先 `sw_detect._reset_cache()` 再 `detect_solidworks()`，不复用进程级缓存。保证 dashboard / 长驻进程场景下每次都读到最新状态。
- **3D-2（SW 会话保护）**：`probe_dispatch` 开头 `try: app = win32com.client.GetObject("SldWorks.Application")` 若成功（SW 已在跑）→ 附着、采集 Revision、**不设 Visible、不 ExitApp**；severity=`warn`；summary="SW 已在另一会话运行，本次 probe 附着未接管 visibility / 未退出以保护用户工作"。否则走正常 Dispatch。
- **hint 字段**（3D-1）：probe 函数在诊断结论明确时填充 `hint`（例：pywin32 缺 → "运行 `pip install 'cad-spec-gen[solidworks]'`"；toolbox_index stale → "删除 `~/.cad-spec-gen/toolbox_index.json` 后再跑 sw-warmup 刷新"）。文本模式缩进 4 格打印；JSON 按 §4.3 是可选字段。

### 4.2 `tools/sw_inspect.py`（新增）

```python
def run_sw_inspect(args) -> int:
    """
    args: argparse.Namespace，含 args.deep: bool, args.json: bool
    返回 exit code，见 §5.1
    """
```

职责：
1. 加载配置：`sw_cfg = parts_resolver.load_registry().get("solidworks_toolbox", {})`（与 `tools/sw_warmup.py:360-361` 同机制）。
2. 顺序调 probe（每个 ProbeResult 不会抛异常）：
   - `probe_environment()` → `probe_pywin32()` → `probe_detect()` 得 `info: SwInfo`
   - `probe_clsid()`
   - `probe_toolbox_index_cache(sw_cfg, info)` — info 复用，避免重新 detect
   - `probe_material_files(info)` — info 复用
   - `probe_warmup_artifacts(sw_cfg)`
   - 若 `args.deep`：`probe_dispatch()` → 若 dispatch ok，`probe_loadaddin()`
3. 聚合所有 `ProbeResult` 到顶层 payload（见 §4.3）。
4. 计时：整个 probe 序列用 `time.perf_counter()` 包起来，得 `overall.elapsed_ms`（QA-1）。
5. 按 `severity` 计算 `overall.exit_code`（见 §5.1）。
6. 按 `args.json` 分流 JSON / 彩色文本输出。
7. 返回 exit code 给 `cad_pipeline.py` dispatcher。

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
    "elapsed_ms": 287,                          // QA-1：整体耗时（perf_counter）
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
- 不保证：`data.*` 子字段增加（消费方用 `.get()`）、`summary` 文案演化、`hint` 字段出现与否（层不定性）。
- `dispatch` / `loadaddin` 只在 `mode="deep"` 时出现；消费方判断 `layer in doc["layers"]` 再读。
- **SA-3 时区**：`generated_at` 一律 UTC ISO-8601 + `Z` 后缀，由 `datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")` 生成；**禁止**写本地时间 / naive datetime。

### 4.3.1 消费者 → 字段依赖表（SA-1）

稳定契约的具体映射——若未来升 schema v2 需要改动以下字段，必须同步通知所有消费方：

| 消费者 | 依赖字段 | 用途 |
|---|---|---|
| CI（gates / smoke） | `overall.exit_code`、`layers.*.severity` | 判 pass/fail，分类失败类别 |
| F-4a baseline 脚本（未来） | `layers.dispatch.data.elapsed_ms`、`layers.dispatch.data.dispatched` | 记录 Dispatch 冷启动耗时分布，决策是否回退 timeout |
| F-4b `stage_c.json` 增补 | `layers.dispatch.data.elapsed_ms`、`overall.severity` | `timeout_rate` 字段填充依据 |
| `sw-status` dashboard（未来） | `overall.*`、`layers.detect.data.version_year`、`layers.toolbox_index.data.{entry_count, by_standard, stale}`、`layers.warmup.data.{step_files, error_log_last_line}` | 仪表板展示 |
| 开发者本机排障 | `layers.*.hint`、`layers.*.error` | 人读诊断 |

schema v1 的"稳定保证"范围明确包含上表第 2 列的每一个字段——**可增补**兄弟字段，但**不可删除/改名/改类型/改语义**。

### 4.4 每层 `data` 字段清单

详见 §3.2 原设计章节（brainstorming 已确认）。摘要：

- **environment**: os / python_version / python_bits / pid
- **pywin32**: available / module_path
- **detect**（镜像 `SwInfo` 的 public 字段；**删去冗余的 sldmat_paths_count**，sldmat 计数归 materials 层）：installed / version / version_year / install_dir / textures_dir / p2m_dir / toolbox_dir / com_available / pywin32_available / toolbox_addin_enabled
- **clsid**: progid / clsid / registered
- **toolbox_index**（对齐 §3.4 真实结构）：
  - `index_path` — `str(get_toolbox_index_path(sw_cfg))`
  - `exists` — `index_path.is_file()`
  - `entry_count` — probe 自行聚合（`sum(len(sub) for std in idx["standards"].values() for sub in std.values())`）
  - `toolbox_fingerprint_cached` — `idx.get("toolbox_fingerprint", "")`
  - `toolbox_fingerprint_current` — `_compute_toolbox_fingerprint(toolbox_dir)`
  - `stale` — bool（见 §3.4 stale 判断条件）
  - `size_bytes` — `index_path.stat().st_size`（不存在 = 0）
  - `by_standard` — **ME-1 修订**：`dict[str, int]` 来自 `idx["standards"]` 的 key 聚合，key 集合由真实扫描决定（无硬编码白名单；若 toolbox_dir 没有 GB 目录，结果就没有 "GB" 键）
- **materials**: sldmat_files（=`len(info.sldmat_paths)`，与 `check_env.py:170` 语义一致）/ textures_categories / textures_total / p2m_files（**仅数量，不解析 XML；**本轮 YAGNI——物理属性解析见 §12 ME-2 升级路径）
- **warmup**（路径对齐 §3.3 路径常量表）：
  - `home` — `str(Path.home() / ".cad-spec-gen")`
  - `step_cache_root` — `str(get_toolbox_cache_root(sw_cfg))`（默认 `home/step_cache/sw_toolbox`）
  - `step_files` / `step_size_bytes` — 对 step_cache_root 递归统计 .step 文件
  - `lock_path` — `str(home/"sw_warmup.lock")`
  - `lock_held` — bool
  - `lock_pid` — int | null（若 held 且可解析对方 PID；解析失败填 null）
  - `error_log_path` — `str(home/"sw_warmup_errors.log")`
  - `error_log_last_line` — str | null
  - `error_log_mtime` — ISO-8601 UTC | null
- **dispatch**（deep only）: dispatched / elapsed_ms / revision_number / visible_set_ok / exit_app_ok / **attached_existing_session**（bool，3D-2：GetObject 命中现有 SW 时为 true）
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
    for probe_fn, exit_on_fail in [
        (probe_pywin32, 1),
        (probe_detect, 2),
        (probe_clsid, 3),
        (probe_dispatch, 4),
        (probe_loadaddin, None),  # 不早退；SAR-1：无 app 参数，内部自行附着
    ]:
        result = probe_fn()
        _print(result)  # 彩色文本；有 hint 则缩进打印
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
| `1` | warning | 至少一层 `severity="warn"`，无 `fail`（例：toolbox index stale / `sw_warmup_errors.log` 非空 / toolbox_addin_enabled=false）|
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

- **probe_pywin32 fail（ImportError 路径）**：`monkeypatch.setitem(sys.modules, "win32com.client", None)` 触发 ImportError 分支。
- **probe_clsid fail**：`@pytest.mark.skipif(sys.platform != "win32")` 保护 + `monkeypatch.setattr(winreg, "OpenKey", lambda *a, **kw: raise FileNotFoundError)`。
- **probe_clsid 非 Windows**：跑在 Linux CI 时直接走 `severity="warn", summary="not applicable"` 分支（不 mock）。
- **QA-2 probe_dispatch com_error 路径**（pywin32 装了但 Dispatch 抛 COM 错）：
  - `monkeypatch.setattr(win32com.client, "Dispatch", lambda progid: raise OSError("(-2147221164, 'Class not registered', None, None)"))` 模拟 `pywintypes.com_error` 的 OSError 子类表现。
  - 同样 mock `GetObject` 抛同类异常，覆盖 3D-2 "SW 未在跑 + Dispatch 失败" 路径。
  - 断言 `result.severity == "fail"`、`result.error` 含 "Class not registered"、exit code = 3。
- **probe_dispatch 超时（mock 路径）**：`monkeypatch.setattr(concurrent.futures.Future, "result", lambda self, timeout: raise TimeoutError)`。
- **QA-4 probe_dispatch 超时（真阻塞路径）**：
  - 不 mock `ThreadPoolExecutor`；mock `win32com.client.Dispatch` 为 `lambda progid: time.sleep(2) or object()`，以 `probe_dispatch(timeout_sec=1)` 调用。
  - 断言 ~1s 内（±200ms 容差）返回 `severity="fail"`、`error` 含 "timeout after 1s"。
  - 验证真实 ThreadPoolExecutor 超时机制没被写坏（例如把 `timeout_sec=60` 误写成 `60ms`）。
- **3D-2 probe_dispatch 附着模式**（SW 已在跑）：
  - mock `GetObject` 返回一个带 `.RevisionNumber` 属性的 fake；断言 `severity="warn"`、`data.exit_app_ok` 不存在或为 `None`、summary 含 "已在另一会话"。
- **probe_toolbox_index_cache stale**：写两份不同 fingerprint 的 JSON fixture，断言 `stale=True`；另起一个 fixture 覆盖 entry_count + by_standard 聚合正确性（ME-1）。
- **QA-3 probe_warmup_artifacts lock_held**：两个平台都要断言：
  - Linux CI（含 GitHub Actions Ubuntu）：tmp_path 下启 subprocess 持有 `fcntl.flock`，主测试 non-blocking try-acquire 检测到占用返回 `lock_held=True`，测试末尾释放。
  - Windows（本机 + `@requires_solidworks` 机器、或 windows-latest runner 若未来开）：同样用 `msvcrt.locking` 分支。
  - 两个断言共用一个参数化测试用 `@pytest.mark.parametrize` 分路。
- **probe_loadaddin**：mock 内部 `win32com.client.Dispatch` 返回 fake app（含 `.LoadAddIn` 方法），测 `LoadAddIn` 返回 1 / 3 / 抛异常 3 种路径。

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

- `test_sw_inspect_fast_real_smoke`：断言 `overall.exit_code in {0, 1}` + `detect.data.version_year >= 2020`。
- `test_sw_inspect_deep_real_smoke`：断言 `dispatch.ok == True` + `dispatch.data.elapsed_ms < 30_000`。

两条都加 `@pytest.mark.requires_solidworks`，Part 2c P1 的 `tests/conftest.py` 钩子自动 skip CI。

**QA-1（计时机制）**：性能**不在测试断言里**，而在 baseline 报告里记录——理由：pytest collection/fixture 开销 200–500ms，与 "< 500ms" 目标同数量级，断言会时灵时不灵。

改用：`run_sw_inspect()` 内部记录 `total_elapsed_ms`（`time.perf_counter()` 精确包在 probe 序列前后），写入 JSON `overall.elapsed_ms`，baseline 报告聚合多次运行的 p50/p95。测试只断言 `isinstance(overall.elapsed_ms, int) and overall.elapsed_ms > 0`。

### 6.6 覆盖率目标

- `sw_probe.py` / `sw_inspect.py`：**≥ 95% line coverage**（诊断代码失败分支多，低于 95% 意味着失败路径漏测）。
- 每个 probe 函数至少 3 个测试：ok / warn / fail。

---

## 7. 性能指标

| 模式 | 目标耗时（装 SW 的机器）| 理由 |
|---|---|---|
| `--deep` off | < 500 ms | 静态层 + 文件系统轻 I/O（Toolbox index JSON 读 ~100ms + 材质目录 scandir）|
| `--deep` on | < 30 s | 冷启 Dispatch ~15s（spike 实测）+ Revision / Visible / ExitApp 秒级 + LoadAddIn 秒级 + 容错余量 |

基准数据来源：`run_sw_inspect()` 每次运行将 `overall.elapsed_ms`（§6.5 QA-1 约定）写入 JSON；开发机连续跑 10 次（5 fast + 5 deep）后由 `tools/` 下轻量脚本聚合 p50 / p95，写入 `docs/superpowers/reports/sw-inspect-baseline-2026-04-16.md`（实施时生成）。

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
| `docs/PARTS_LIBRARY.md` | 作为当前权威方案，必要时补充 `sw-inspect` 诊断入口说明 |

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
| `probe_dispatch` 悬挂时无法真 kill 后台 COM 线程 | CLI 看起来 Ctrl-C 生效但进程仍有残留线程直到整体退出 | 接受（ThreadPoolExecutor 软超时）| **F-1.2** follow-up：`sw_inspect_worker.py` subprocess 隔离（参考 Part 2c P0 `sw_convert_worker.py`）|
| deep 模式的 real smoke 测试无法进 GitHub Ubuntu CI | 靠 `@requires_solidworks` skip，实机验证只能在开发者本机跑 | 接受 | **F-1.3** follow-up：Windows self-hosted runner |
| **ME-2** sldmat XML 解析不在本轮覆盖 | materials 层只数文件不解析 preset / type_keywords 分布；机械设计师看不到物理属性可用性 | 接受（YAGNI——快速扫保持轻量）| **F-1.1** follow-up：`probe_material_files` 在 deep 模式调 `load_sw_material_bundle()`，data 补 `material_count` + `preset_mapped_count` + `with_physical_props_count` |
| JSON schema v1 的 `data` 字段扩充不破坏性、但**字段名冲突时**必须 bump v2 | 低概率 | 接受 | 若出现就按 `version="2"` 发布新契约 |
| **3D-2** probe_dispatch 附着已在跑的 SW 只能读、不能关——若用户此时又关 SW、probe 过程中的 Revision 调用可能 RPC 失败 | 低概率边缘场景 | 接受（捕 Exception → severity=fail） | 无（行为正确）|
| **SAR-1** probe_loadaddin 自行再 Dispatch 附着 | deep 模式总耗时 +2–5s（附着比冷启快）| 接受（签名清晰优先） | 可选：若性能问题，改为 probe_dispatch 通过 sidecar 单例传 app（破坏纯函数性，不推荐）|

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
8. `tools/cad_pipeline_agent_guide.md` / README / `docs/PARTS_LIBRARY.md` 文档更新

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
