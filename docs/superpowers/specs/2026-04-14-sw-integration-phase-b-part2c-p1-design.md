# SolidWorks Phase SW-B Part 2c P1 — 设计文档

> 日期：2026-04-14 · 分支：`feat/sw-b-part2c-p1` · 前置：PR #1（Part 2c P0）已 squash-合入 `main` at `0706e44`

## Goal

清理 Part 2b 最终 review 遗留的 **Important-1 / Important-3**（下称 I-1 / I-3）backlog，并落地三项"无 SolidWorks 依赖"的基建重构（含两条 Minor-级修整 M-4 / M-6），为未来 SW-B9 真实 COM 验收 + SW-B10 packaging 铺路。

**范围（5 项）**：

| # | 交付 | 来源 |
|---|---|---|
| T1 | `SwToolboxAdapter._find_sldprt` 升 public `find_sldprt`（硬重命名，无 alias） | Part 2b review M-4；下游 `tools/sw_warmup.py` 已跨模块调用该私有方法属架构异味 |
| T2 | `@pytest.mark.requires_solidworks` marker + 根级 `tests/conftest.py` 自动 skip 钩子 | Part 2c P0 plan §defer P2；SW-B9/B10 先决条件 |
| T3 | `tools/sw_warmup.py` acquire 首次 `msvcrt.locking` 前加 `fh.seek(0)` | Part 2b final review I-3 |
| T4 | `tools/sw_warmup.py` exit code 3 区分 "lock contention" 与 "部分失败" | Part 2b final review I-1 |
| T5 | `bom_parser.py` material 缺省字符串 9 条规范化 | Part 2b review M-6 + 2026-04-14 SW smoke 实测 BOM 匹配层污染 |

**范围外（defer）**：

- BOM length regex fix（`extract_size_from_name` 在 "GB/T 70.1 M6×20" 把 "70.1" 当长度）— 单测可写，但端到端复验需要真 SW smoke。推迟到下次 SW smoke 时同步做
- P2：`SINGLE_CONVERT_TIMEOUT_SEC` 30→20s 下调、packaging、`sw-inspect` 子命令 — 按用户明示排除

## 架构原则

**每 task 一个原子 commit，5 个独立 commit**。无跨 task 的隐式依赖，任意单个 commit 都可独立 review/revert；commit 顺序只为最小化 rebase 摩擦：

```
T1（跨文件重命名，早改早稳）
 ↓
T2（独立测试基建，无既有代码碰撞）
 ↓
T3（sw_warmup.py 锁 3 行最小修复）
 ↓
T4（同 sw_warmup.py，别行段，T3 后做避冲突）
 ↓
T5（独立 bom_parser.py 收尾）
```

**TDD 铁律**：每 task 先写失败测试，最小实现绿灯，再 refactor。见项目 `CLAUDE.md`。

## Task 细节

### T1：`_find_sldprt` → `find_sldprt`（硬重命名）

**Files（审查后精确清单，共 8 处文字改动）**:

- Modify: `adapters/parts/sw_toolbox_adapter.py:204` — `def _find_sldprt` → `def find_sldprt`；docstring 去掉"供 sw-warmup --bom 复用"的内部措辞，改为明确的公开契约
- Modify: `tools/sw_warmup.py:288` — `_resolve_bom_targets` docstring 中的 `"复用 SwToolboxAdapter._find_sldprt"` → `"复用 SwToolboxAdapter.find_sldprt"`
- Modify: `tools/sw_warmup.py:298` — 调用 `adapter._find_sldprt(q, spec)` → `adapter.find_sldprt(q, spec)`
- Modify: `tests/test_sw_toolbox_adapter.py:341` — class `TestFindSldprt` docstring 中 `_find_sldprt()` → `find_sldprt()`
- Modify: `tests/test_sw_toolbox_adapter.py:367` — `result = a._find_sldprt(...)` → `result = a.find_sldprt(...)`
- Modify: `tests/test_sw_toolbox_adapter.py:380` — 方法 docstring `"_find_sldprt 不应导入"` → `"find_sldprt 不应导入"`
- Modify: `tests/test_sw_toolbox_adapter.py:383` — 内部注释 `"证明 _find_sldprt 不依赖它"` → `"证明 find_sldprt 不依赖它"`
- Modify: `tests/test_sw_toolbox_adapter.py:395` — `result = a._find_sldprt(...)` → `result = a.find_sldprt(...)`
- Unchanged: `adapters/solidworks/sw_toolbox_catalog.py:448` 的历史注释 `"让下游 resolve/_find_sldprt/sw-warmup 可以直接信任 index"` — 注释里的历史名保留（blame 可溯源），不属 API 契约
- Unchanged: `docs/superpowers/specs/2026-04-13-*.md` 和 `docs/superpowers/plans/2026-04-13-*.md` — 历史快照文档，不改

**验收**：

- `rg "_find_sldprt" adapters tools tests` 命中数为 0（文档目录除外）
- 既有 `tests/test_sw_toolbox_adapter.py::TestFindSldprt` 的 2 个测试方法改调用名后全绿

**无新测试** — 重命名属 refactor，现有测试改调用名即覆盖。

---

### T2：`@requires_solidworks` marker + conftest 自动 skip

**Files**:

- Modify: `pyproject.toml:76` — `markers` 列表追加：
  ```toml
  "requires_solidworks: 需真实 SolidWorks + pywin32；缺任一自动 skip（不报 fail）",
  ```
- **Modify（不是 Create）**: `tests/conftest.py` — **本仓库已有 72 行 conftest**（含 `isolate_cad_spec_gen_home` autouse fixture + `sys.path` insert 逻辑），审查时验证过。追加 `pytest_collection_modifyitems` 钩子到文件末尾，不触碰既有 fixture / sys.path 代码：
  ```python
  # ─── requires_solidworks marker 自动 skip 钩子（Part 2c P1 T2） ───

  def pytest_collection_modifyitems(config, items):
      """为 @pytest.mark.requires_solidworks 的 item 按需加 skip 标记。

      触发 skip 条件（任一满足，优先级从高到低）：
        1. sys.platform != "win32"（COM 是 Windows 独占）
        2. pywin32 (import win32com) 不可用
        3. adapters.solidworks.sw_detect.detect_solidworks().installed == False

      2 和 3 由运行时唯一事实源 sw_detect 统一回答（非 Windows 平台上
      detect_solidworks() 也返回 installed=False, pywin32_available=False，
      但显式检查 sys.platform 让 skip reason 更精确）。
      异常不吞：sw_detect 导入失败 → collection 失败，不 silent skip。
      """
      import sys

      needs_sw = [it for it in items if it.get_closest_marker("requires_solidworks")]
      if not needs_sw:
          return

      if sys.platform != "win32":
          reason = "requires_solidworks：非 Windows 平台"
      else:
          try:
              from adapters.solidworks.sw_detect import detect_solidworks
              info = detect_solidworks()
          except ImportError as exc:
              raise pytest.UsageError(f"sw_detect 导入失败：{exc}") from exc

          if info.pywin32_available and info.installed:
              return  # 真装了 SW，保留原样跑
          reason = "requires_solidworks：" + (
              "pywin32 缺" if not info.pywin32_available else "SolidWorks 未安装"
          )

      skip = pytest.mark.skip(reason=reason)
      for it in needs_sw:
          it.add_marker(skip)
  ```
- Create: `tests/test_requires_solidworks_marker.py` — 用 pytester fixture 内联跑**参数化 3 类情形**（QA Q1）：
  1. 无 marker 的用例照常跑（基线）
  2. 有 marker 且当前环境满足（Windows + pywin32 + SW）→ 照常跑
  3. 有 marker 且当前环境不满足 → skip，且 `-rs` 输出里 reason 精确包含 "非 Windows 平台" / "pywin32 缺" / "SolidWorks 未安装" 之一
  测试通过 monkeypatch 切换 `sys.platform` 与 `detect_solidworks` 返回值模拟 3 种环境，不依赖真 SW

**验收**：

- Linux CI 全套 `-rs` 能看到打了 marker 的用例被 skip，reason 枚举完整；P1 本身 **不** backfill 到既有测试（现无测试真需要 SW；marker 留给 SW-B9）
- Windows 本地装了 SW 的机器跑 `pytest tests/test_requires_solidworks_marker.py`，skip/pass 正常
- **QA Q5 新增**：`pytest tests/ --collect-only 2>&1 | grep -c "PytestUnknownMarkWarning.*requires_solidworks"` 结果为 0（确认 pyproject.toml 注册成功）

**Why 不吞异常**：`CLAUDE.md` 明禁 silent failure。sw_detect 模块在未来如果炸了，collection 应爆而非静默 skip 所有真跑测试——那样真 bug 会被 ok 数掩盖。

---

### T3：msvcrt.locking 首次 acquire 前 `fh.seek(0)`

**Files**:

- Modify: `tools/sw_warmup.py` 顶部模块常量区（现有 `_held_locks` 附近，line 20-21）追加：
  ```python
  # 锁定的字节范围常量 — acquire 与 release 必须对齐同一 range，
  # 否则 msvcrt release 成 no-op 导致句柄泄漏（Part 2b review I-3）。
  _LOCK_OFFSET = 0
  _LOCK_NBYTES = 1
  ```
- Modify: `tools/sw_warmup.py:137-143` — 只在 **Windows msvcrt 分支**加 `fh.seek(...)` 并把字面量 `1` 换成常量：
  ```python
  # msvcrt.locking 锁的是"从当前位置起 N 字节"。"a+" 模式 open 后 file position
  # 默认在 EOF，锁会落在未知 offset；而释放路径（第 180 行）已 seek(0) 锁到
  # offset 0。acquire 与 release 必须对齐同一 byte range，否则 release 成 no-op
  # 导致锁句柄泄漏。修 Part 2b final review I-3。
  fh.seek(_LOCK_OFFSET)
  msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, _LOCK_NBYTES)
  ```
- Modify: `tools/sw_warmup.py:178-180` — release 路径同步用常量（既有字面量 `1` → `_LOCK_NBYTES`；`fh.seek(0)` → `fh.seek(_LOCK_OFFSET)`）。这是配对性修改，**必须与 acquire 处同一 commit 进行**
- **不改**：POSIX `fcntl.flock` 分支（line 149-156 + line 184-188）。`fcntl.flock` 锁整个文件（不看 file position），不需要 seek/常量；贸然加会增加认知负担且无实际效果

**验收**：

- 新单测 `tests/test_sw_warmup_lock.py::test_acquire_seeks_to_zero_before_locking` — mock `msvcrt.locking`，断 mock 被调时 `fh.tell() == _LOCK_OFFSET` 且 `mock.call_args[0][2] == _LOCK_NBYTES`（第 3 个位置参数即字节数）
- 本地连开两个 sw_warmup（真文件锁），第二个被挡住（现在也会挡——但修之前 release 是 no-op 会让孤儿句柄泄漏到第 3 轮才暴露）
- 验收脚本 `rg "msvcrt.locking\(" tools/sw_warmup.py` 的结果中**不再出现**整数字面量 `1` 作为第 3 参数（只出现 `_LOCK_NBYTES`）

---

### T4：exit code 3 区分 lock contention

**Files**:

- Modify: `tools/sw_warmup.py` 顶部加**带结构化 PID 属性**的专用异常（架构审查 A1 + A4）：
  ```python
  class WarmupLockContentionError(RuntimeError):
      """另一 sw-warmup 进程持有锁；调用方应返回 exit 3 而非 1。

      PID 作为结构化属性暴露，未来 sw-inspect 子命令（P2）可以直接
      `exc.pid` 读取，无需 `re.match(r"PID (\\d+)", str(exc))` 反解字符串。
      """

      _MSG_FMT = "另一个 sw-warmup 进程运行中 (PID {pid})"

      def __init__(self, pid: str):
          super().__init__(self._MSG_FMT.format(pid=pid))
          self.pid: str = pid
  ```
  消息模板下沉为类属性 `_MSG_FMT`，外部不再需要单独的 `_LOCK_CONTENTION_MSG_FMT` 模块常量（更自洽）
- Modify: `acquire_warmup_lock` 内 **两处** `raise RuntimeError(...)` 都要改：
  - 第 147 行 Windows msvcrt 分支（`OSError` 捕获后）
  - 第 156 行 POSIX fcntl 分支（`OSError, BlockingIOError` 捕获后）
  
  两处都改为：
  ```python
  raise WarmupLockContentionError(pid=pid) from e
  ```
- Modify: `run_sw_warmup`（233 行）：
  ```python
  def run_sw_warmup(args) -> int:
      """sw-warmup 主入口。

      Returns:
          0 成功 / 1 部分失败 / 2 前置失败 / 3 锁争用（另一实例在运行）
      """
      try:
          with acquire_warmup_lock(_default_lock_path()):
              return _run_warmup_locked(args)
      except WarmupLockContentionError as e:
          print(f"[sw-warmup] {e}")
          return 3
      except RuntimeError as e:
          # 其它 RuntimeError 仍按"部分失败"处理，保持既有行为
          print(f"[sw-warmup] {e}")
          return 1
  ```
- **已审查下游调用链**（无需改）：
  - `cad_pipeline.py:2492-2494` — `cmd_sw_warmup` 对 `run_sw_warmup` 的 exit code 透传，无硬编码 `rc == N` 判断 ✅
  - `tests/test_sw_warmup_orchestration.py:178, 201` — 两处 `assert rc == 1` 都是"部分/全部 convert 失败"路径，与 lock contention 语义不同 ✅
  - `tests/test_sw_warmup_lock.py:35` — 现有 `pytest.raises(RuntimeError, match="另一个 sw-warmup 进程")` 因 `WarmupLockContentionError(RuntimeError)` 子类关系仍 PASS，但本 task **应顺手升级**为 `pytest.raises(WarmupLockContentionError)` 以匹配新精确类型（T4 自带的小型回归保护）

**验收**：

- 新单测 `tests/test_sw_warmup_orchestration.py::test_run_sw_warmup_returns_3_on_lock_contention` — mock `acquire_warmup_lock` 抛 `WarmupLockContentionError("1234")`，断 return 值 == 3
- 新单测 `test_run_sw_warmup_returns_1_on_generic_runtimeerror` — mock 锁正常取得，但 `_run_warmup_locked` 抛裸 `RuntimeError`，断 return == 1（回归保护）
- **新单测 `test_WarmupLockContentionError_exposes_pid_attribute`** — QA Q2 + 架构 A1 保护：`exc = WarmupLockContentionError("9999"); assert exc.pid == "9999" and "9999" in str(exc)`
- 既有 `test_sw_warmup_lock.py::test_concurrent_acquire_raises` 升级为 `pytest.raises(WarmupLockContentionError) as ei; assert ei.value.pid == str(os.getpid())`，结构化断言 PID 属性
- **新 POSIX fcntl 分支专用测试**（QA Q2）：`@pytest.mark.skipif(os.name == "nt", reason="POSIX only")` 的 `test_concurrent_acquire_raises_on_posix`——既有测试在 Windows runner 上跑，fcntl 路径无覆盖；Linux CI 补齐
- 既有 return 0 / 1 / 2 路径测试不回归

**Why 专用异常子类**：沿用 Python 标准做法。用 `isinstance(e, str)` 或字符串匹配区分异常类型是反模式；子类是语言层语义，不依赖字符串内容的稳定性。

---

### T5：bom_parser material 9 条缺省规范化

**Files**:

- Modify: `bom_parser.py` 顶部加模块常量 + 辅助函数：
  ```python
  # 注意字符选择：所有 em dash 都是 U+2014。"——" 是两 em dash 连写（Excel 里
  # 输入 `--` 再被自动替换后的常见形态），不是 U+2500 BOX DRAWINGS。
  # 机械设计师审查 D1：加 "na"（英制 BOM 无斜杠变体，与 "n/a" 并列为常见写法）。
  _MATERIAL_ABSENT_TOKENS = frozenset({"", "-", "—", "——", "/", "n/a", "na", "无", "无材质"})

  def _normalize_material(raw: str | None) -> str:
      """把 BOM 里的"无材质"惯用写法统一为空字符串。

      Why：Excel 导出的 BOM 常见 "—"（U+2014 全角破折号，`--` 自动替换）/
      "N/A"/"无"等表示"无指定材质"。字面值传到下游：
        - classify_part(line 47) 的 substring keyword match 会走 "other"（行为
          等效，但消耗一次字符串 upper）
        - cad_pipeline.py:664 的 material keyword preset match 会全 miss，走
          默认 preset（行为等效）
        - 未来 sw_material_bridge 若加 by-name lookup 会 100% miss
      统一归一为 ""，让"缺省"在数据流里是显式状态，日志与观察一致。

      架构一致性：本仓库 bom_parser.py:70 的 parse_price 已有 ("—", "-", "N/A")
      的缺省集合先例（prior art）；T5 把 material 域的同类逻辑抽成显式辅助
      函数并扩展 CJK 写法。两者域不同（price / material）暂不合并——若未来
      第三个消费者出现，届时再抽通用 `_normalize_empty_strings(raw, tokens)`。

      不区分大小写（"N/A" / "n/a" 等价）；strip 两端空白再比较。
      非缺省值（如 "Q235B"）只做 strip，返回原字符串。
      """
      if raw is None:
          return ""
      stripped = raw.strip()
      return "" if stripped.lower() in _MATERIAL_ABSENT_TOKENS else stripped
  ```
- Modify: `bom_parser.py:196` 读 material 单元格后用 `_normalize_material(...)` 包一层
- **不改** `classify_part(name, material)`（line 47）入口——它只做 substring+upper 比较，`material=""` / `material="—"` 行为等效，改会是无必要改动；下游数据清洁由 bom_parser.py:196 单点规范化保证，符合"一处规范化"原则

**验收**：

- 新 `tests/test_bom_parser_material_normalization.py`，**参数化单测矩阵**：
  - 9 个缺省串正例：`""`, `"-"`, `"—"` (U+2014), `"——"` (U+2014×2), `"/"`, `"N/A"`（+`"n/a"`大小写变体）, `"NA"`（+`"na"`大小写变体）, `"无"`, `"无材质"`
  - 3 个边界正例（QA Q3）：`"   "`（纯空白）, `None`（非 str），`"\tN/A\n"`（两端空白）
  - 5 条真值反例：`"Q235B"` / `"45#"` / `"7075-T6铝合金"` / `"Al 6061-T6  硬质阳极氧化≥25μm"` / `"S355JR"`（确保不被误杀）
- 既有 `tests/test_bom_parser*` 全绿，无 classify 逻辑回归

---

## 错误处理、回归防护、测试集成

- **T2 marker skip 钩子**：`detect_solidworks()` 抛异常 → 用 `pytest.UsageError` 让 collection 失败，**不** silent skip
- **T4 WarmupLockContentionError**：异常子类而非字符串匹配；通用 `RuntimeError` 仍走 exit 1 回归安全
- **T5 material 规范化**：只信任 `str | None` 契约；`pandas.NaN` 等非 str 类型由上游保证
- **测试套件规模**：Part 2c P0 合并后基线 ~156 个 SW 相关 + bom_parser 若干；P1 预计 +10~15 单测，全跑 <30s
- **CI 期望**：Part 2c P0 刚修的 7 job CI 矩阵无变化；`@requires_solidworks` marker 在 Linux runner 上自动 skip，零时间影响

## 验收命令（每 task 完成后本地跑）

```bash
# 针对性
uv run pytest tests/test_sw_toolbox_adapter.py tests/test_sw_warmup*.py tests/test_bom_parser*.py tests/test_requires_solidworks_marker.py -v

# 全量 SW 套件
uv run pytest tests/ -v -k "sw_ or bom_parser or requires_solidworks"

# Ruff
uv run ruff check . && uv run ruff format --check .
```

## Commit message 规范（CLAUDE.md 强制）

```
T1: refactor(sw-b): SwToolboxAdapter._find_sldprt 升 public find_sldprt（Part 2b M-4）
T2: test(sw-b): @requires_solidworks pytest marker + conftest 自动 skip
T3: fix(sw-b): sw_warmup 首次 msvcrt.locking 前 fh.seek(0)（Part 2b I-3）
T4: feat(sw-b): sw_warmup exit code 3 区分 lock contention（Part 2b I-1）
T5: fix(sw-b): bom_parser material 9 条缺省字符串规范化（Part 2b M-6 + smoke 2026-04-14 实证）
```

每个 commit 末尾附 `Co-Authored-By` trailer。

## 终态（合 PR 后）

- Part 2b final review 遗留 I-1 / I-3 完全 closed
- `SwToolboxAdapter.find_sldprt` 成为官方 public API
- `@requires_solidworks` 就绪，SW-B9 真实 COM 验收测试可以开始落地
- `bom_parser` material 层对常见 Excel BOM 写法鲁棒

## 第一轮审查：管道融合（2026-04-14）

用户要求"保证与现有管道流程融合 / 数据流一致 / 函数调用一致性 / 方法通用性"后，针对 5 个 task 的实际代码路径做了一次审查，关键发现与对应的 spec 修订：

| 审查项 | 发现 | spec 修订 |
|---|---|---|
| T1 所有调用点 | 初版只列 "2 条 test 改调用"，实际散布在 **8 处**（含 `sw_warmup.py:288` docstring 与 test file 的多处引用） | 已扩展到精确 8 处清单 |
| T2 conftest.py 是否存在 | **已存在** 72 行（`isolate_cad_spec_gen_home` + sys.path setup），初版错写为 "Create" | 改为 "Modify 追加钩子到末尾，不触碰既有 fixture" |
| T2 skip reason 优先级 | `detect_solidworks()` 在非 Windows 上返回 `installed=False, pywin32_available=False`，原 reason 文案会误报"pywin32 缺"而真实原因是"非 Windows 平台" | 加 `sys.platform != "win32"` 第一级判断，reason 更精确 |
| T3 POSIX 分支 | `fcntl.flock` 不看 file position，不需要 seek(0)；原 spec 未明确说不改 fcntl 分支 | 明确标注"不改 POSIX fcntl 分支" |
| T4 raise 位置 | `acquire_warmup_lock` 有两处 RuntimeError raise（msvcrt + fcntl 分支），两处都要改 | 明确给出行号 147 / 156 双修点 |
| T4 既有测试兼容 | `test_sw_warmup_lock.py:35` 的 `pytest.raises(RuntimeError)` 因子类关系仍 PASS，但**应顺手升级**为 `pytest.raises(WarmupLockContentionError)` | 加进 T4 验收项 |
| T4 下游 `rc == 1` | `cad_pipeline.py:2492-2494` 透传 exit code，`test_sw_warmup_orchestration.py:178/201` 的 `rc == 1` 都是"部分失败"路径不是 lock contention | 明确标注"无需改" |
| T5 prior art | `bom_parser.py:70 parse_price` 已有 `("—", "-", "N/A")` 缺省集合先例（em dash 只用 U+2014，没有 U+2015） | docstring 增加 cross-ref + U+2014 标注 |
| T5 下游数据流 | `classify_part` / `cad_pipeline.py:664` material keyword match 都是 substring+upper，规范化前后行为等效（`""` 和 `"—"` 都不匹配任何 keyword）；`sw_material_bridge` 目前无 by-name lookup，零影响 | 明确"规范化不破坏任何既有行为，仅让缺省状态显式" |
| T5 classify_part 是否也规范化 | 无必要（同上行为等效分析）；"一处规范化"更符合 single source of truth 原则 | spec 加"不改 classify_part" 说明 |
| 方法通用性（`_normalize_material` vs `parse_price`）| 两者域不同（material / price）暂不合并，避免过早抽象 | docstring 写明 "未来第三个消费者出现再抽通用" 的 YAGNI 判据 |

## 第二轮审查：硬编码与变量一致性（2026-04-14）

用户要求 "保证无硬编码 + 变量一致性" 后再做一轮，专审 T3/T4/T5 代码级细节：

| # | 类别 | 问题 | spec 修订 |
|---|---|---|---|
| H1 | 硬编码 | `msvcrt.locking(..., 1)` 字节数 `1` 在 acquire + release 双份；现有 release 路径已含字面量，与 acquire 必须对齐 | 抽模块常量 `_LOCK_OFFSET = 0` / `_LOCK_NBYTES = 1`，**T3 同一 commit 同步改 release 路径** |
| H2 | 硬编码 | lock contention 错误消息模板 msvcrt / fcntl 两分支重复（既有 bug，T4 顺手治理） | 抽 `_LOCK_CONTENTION_MSG_FMT = "另一个 sw-warmup 进程运行中 (PID {pid})"` |
| H3 | 硬编码 | exit code `0/1/2/3` 整数字面量 | **不动**：既有代码 `return 0/1/2` 都是裸字面量，仅命名 `3` 会破坏风格一致；要抽要一起抽，P1 scope 外 |
| H4 | 硬编码 | `"requires_solidworks"` marker 字面量 6+ 处 | **不动**：`@pytest.mark.XXX` 就是查字符串，抽常量破坏 pytest API 惯例 |
| V1 | 一致性 | 若采纳 H1，T3 spec code block 与实际代码必须一致用常量 | 已同步 spec 展示 `_LOCK_OFFSET` / `_LOCK_NBYTES` |
| V2 | 一致性 | 既有 `run_sw_warmup` docstring 只写 0/1/2，T4 的 exit code 3 必须同步更新 docstring | T4 spec 已覆盖 ✅ |
| V3 | 一致性 | T5 `_MATERIAL_ABSENT_TOKENS` 里 `"──"` 实际是 U+2500 BOX DRAWINGS × 2，**不是** em dash；Excel 不会产生此字符 | 改为 `"——"`（U+2014 × 2），加注释说明字符选择；测试反例清单同步更新 |
| V4 | 一致性 | `acquire` / `release` 两条路径的 seek offset + 字节数必须对称 | H1 常量抽取后天然对齐 ✅ |

## 第三轮审查：五角色视角（2026-04-14）

系统分析员 / 架构师 / 3D 建模师 / 机械设计师 / QA 工程师五视角再审，精选修订：

| # | 角色 | 发现 | 处置 |
|---|---|---|---|
| A1 | 架构师 | `WarmupLockContentionError` 只携带 str 消息，PID 信息靠字符串反解，P2 sw-inspect 子命令消费反模式 | PID 作为结构化属性；消息模板下沉为类属性 `_MSG_FMT`（消除 A4 的外部模块常量，更自洽） |
| D1 | 机械设计师 | `_MATERIAL_ABSENT_TOKENS` 缺 `"NA"`（英制 BOM 无斜杠变体，工程实测常见） | 扩至 9 个 token（加 `"na"`，`.lower()` 匹配涵盖 "NA"/"na"） |
| Q1 | QA | T2 新单测只覆盖 1 种 skip reason | 改 parametrize 3 类情形（无 marker / 满足 / 3 种不满足 reason 枚举） |
| Q2 | QA | T4 POSIX fcntl 分支 raise 子类无覆盖 | 补 `@skipif(os.name=='nt')` 的 `test_concurrent_acquire_raises_on_posix` 和 `exc.pid` 结构化断言 |
| Q3 | QA | T5 缺纯空白/None/前后空白 edge case | 单测矩阵加 3 条边界：`"   "` / `None` / `"\tN/A\n"` |
| Q5 | QA | marker 注册失败的静默 warning | 加 `grep -c "PytestUnknownMarkWarning.*requires_solidworks" == 0` 验收 |
| M3 | 3D 建模师 | Spec 全 code-level，无 user-facing impact | 见下方 "Stakeholder Impact" 段 |
| F1 | 系统分析员 | 缺 Risk & Rollback | 见下方 "风险与回滚" 段 |
| A2, A3, M1, M2, D2, D3, Q4, Q6 | 多角色 | 评估后判定无需改 / 风险可接受 | 见 Rollback 表的风险备注栏 |

## Stakeholder Impact（user-facing 影响）

| 角色 | P1 合 PR 后得到的改善 |
|---|---|
| 3D 建模师 | material 空值从"字符串'—'污染下游" → 显式 `""` 归一；`find_sldprt` 成为官方 public API，建模脚本可直接 `SwToolboxAdapter().find_sldprt(query, spec)` 做批量命中率查询 |
| 机械设计师 | BOM 写 "NA"/"-"/"无" 都统一归一（之前 "N/A" 有 `.lower()` 但 "NA" 无处理）；sw-warmup 被占用时 exit code 3 可用于 CI/脚本判别"不重试"vs"可重试" |
| 开发 / CI 运维 | `@requires_solidworks` marker 让 Linux CI 预留真跑测试接口（SW-B9 直接可用）；锁争用不再污染"部分失败"的告警通道 |

## 风险与回滚

| Task | 失败模式 | 回滚动作 | 检出时机 |
|---|---|---|---|
| T1 | 遗漏 callsite（外部插件依赖旧名） | `git revert` 本 commit；grep 验收漏了 | CI 或本地 pytest 未绿 |
| T2 | conftest hook 影响既有 autouse fixture | 只需删除末尾追加段，保留 `isolate_cad_spec_gen_home` 不动 | pytest collection 报 fixture 错 |
| T3 | seek(0) 影响 "a+" 模式下一次 `fh.write(pid)` 的写入位置 | `git revert` 本 commit（同时回退 `_LOCK_OFFSET`/`_LOCK_NBYTES` 常量抽取） | 预先排查：line 164 后既有 `seek(0)+truncate+write(pid)` 逻辑已做 seek(0)，风险为零 ✅ |
| T4 | **Q6 第三方 catch bare RuntimeError** 消费 lock contention 现在失配 | `except RuntimeError` 捕获范围不变（WarmupLockContentionError 是 RuntimeError 子类），反向兼容 ✅ | 理论风险为零 |
| T5 | 新 token 误杀真值（如材料名里含 `"-"` 作为连字符） | 只归一**等值**比较，非 substring —— `"7075-T6铝合金".strip() == "-"` 不成立 ✅ | 测试反例清单覆盖 |

## 未决问题

无。三轮审查累计发现 28 条（第一轮 11 条管道融合点 / 第二轮 8 条硬编码与一致性点 / 第三轮 9 条五角色要点），全部或修订落地、或评估后给出保留论据。

## 第四轮审查：文字表述与衔接（2026-04-14）

用户专审 "文字准确性 + 章节衔接流畅性" 后修订：

| # | 类别 | 问题 | 处置 |
|---|---|---|---|
| A1 | 准确 | T5 token 数 "8" 未随 D1 修订同步为 "9"（Goal 表 / T5 标题 / commit message 三处） | 全量同步为 9 |
| A2 | 准确 | T5 来源漏引 Part 2b review M-6 编号 | Goal 表补 "M-6" 追溯 |
| A3 | 准确 | T1 commit message 误写 "I-M4"，应为 Minor-4 编号 "M-4" | 改 `M-4` |
| A4 | 准确 | T1 验收写 "8 条（如有）或 2 条" 错估 TestFindSldprt 下测试方法数 | 改为精确 "2 条" |
| A5 | 准确 | Rollback 表 T3 行的"回滚动作"栏填入排查结论（语义错位） | 拆两栏：动作填 `git revert`，结论挪到"检出时机"栏加 "预先排查：...风险为零" |
| A6 | 准确 | "5 × 3 = 15" 不实（实际 28 条） | 改为三轮累计 11 + 8 + 9 = 28 的实诚表述 |
| S1 | 衔接 | Goal 段首次出现 "I-1 / I-3" 前无 gloss，读者要到后文才理解前缀 | Goal 段首次 gloss "Important-1/Important-3"，T1 Minor-4/Minor-6 一并解释 |
| S2 | 衔接 | 三次审查章节副标题格式不一（"落盘后补做" vs "第二轮" vs "第三轮"） | 统一为 "第一轮审查：xxx" / "第二轮审查：xxx" / "第三轮审查：xxx"（本段为 "第四轮审查"） |
| S3 | 衔接 | T3 验收的 `nbytes == _LOCK_NBYTES` 用伪变量名而非 mock API 精确表达 | 改为 `mock.call_args[0][2] == _LOCK_NBYTES`（第 3 位置参数） |
