# 设计文档：Part 2c P2 Packaging — solidworks extra + timeout 下调

**日期**: 2026-04-16
**状态**: 草案（待用户审查 → approve 后流转至 writing-plans）
**范围**: SW-B Part 2c P2 的 A + C 两件子任务（B 子任务 sw-inspect 另行独立处理）

---

## 背景

Part 2c 是 SolidWorks 集成的收尾阶段。P0 交付 subprocess-per-convert 模型治好了 hang 问题，P1 清理了 Part 2b backlog 并引入基建（`@requires_solidworks` marker、`WarmupLockContentionError`、`_MATERIAL_ABSENT_TOKENS` 等）。P2 是剩余的"便利性 + 调优"三件小事：

- **A.** `pyproject.toml` 新增 `solidworks` optional extra — 消除"需手动装 pywin32"的 friction
- **B.** `sw-inspect` 子命令 — 一次性看清 SW 环境/toolbox 索引/匹配率状态
- **C.** `SINGLE_CONVERT_TIMEOUT_SEC` 30→20s — 基于 Part 2c P0 真 SW smoke 实测冗余过保守

brainstorming 确认 **本轮只做 A + C**；B 因涉及新 CLI 面的独立设计（输出项/格式/错误分级），单独 brainstorming，不在本轮打包以免冲淡 packaging 焦点。

---

## 范围

### 本轮交付（两件）

- **A. `pyproject.toml [project.optional-dependencies]` 新增 solidworks extra**
- **C. `SINGLE_CONVERT_TIMEOUT_SEC` 30 → 20s 全链路同步**

### 明确排除

- **B.** `sw-inspect` 子命令 — 独立任务（涉及诊断输出项/格式/错误分级的新设计）
- **让 `SINGLE_CONVERT_TIMEOUT_SEC` 从 YAML 可配** — 否决理由：没有需求驱动"让用户可配"，加配置读取链路纯属增加工程复杂度
- **README / `cad-skill-check` 文档更新** — 独立任务（M-1 follow-up）
- **CI 新增 `pip install '.[solidworks]'` 集成验证** — 独立任务（成本高、contract test 已覆盖 toml 字段正确性）
- **YAML `single_convert_timeout_sec` 与代码常量的双 source of truth 彻底解决** — 独立任务（要么删 YAML 字段 + test 断言，要么走"YAML 可配"方案）

---

## 决策路径（brainstorming 汇总）

| 决策 | 选项 | 理由 |
|---|---|---|
| **scope** | A + C（B 推迟） | C 仅值替换，与 A 共享"让 SW 栈更省事"语义；B 是新 CLI 设计，需独立 brainstorming |
| **A. pywin32 平台 marker** | `sys_platform == "win32"` | 与项目 `@requires_solidworks` marker 已认可的"Linux 用户合法"态度一致；Linux 上 extra 装成 no-op 比 pip 硬 reject 的用户体验更柔和 |
| **A. `all` extra 是否加 pywin32** | 不加 | 保持 `all` 全平台可装；避免 marker 污染扩散 |
| **A. pywin32 版本下限** | `>=306` | 2023 年版本；项目 `requires-python >=3.10`，306 对 3.10+ 全支持；上限不设，避免过早约束 |
| **C. timeout 新值** | 20s | Part 2c P0 真 SW smoke 端到端均值 11.6s × 1.72x 冗余（见"事实口径"节） |
| **C. 收尾范围** | 5 处同步修改 | 运行时常量（sw_com_session.py:33）+ YAML 声明（parts_library.default.yaml:82）+ test 断言（test_sw_toolbox_adapter_registration.py:100）+ authoritative 设计文档（sw-com-session-threading-model.md:7,54） |
| **测试 approach** | β. 值替换 + 契约测试 | 与项目 `test_sw_toolbox_adapter_registration`（YAML 契约 test）风格一致；未来误删 pyproject 字段被 CI catch |

---

## 事实口径（来自 memory / 代码扫描的权威事实）

- **冷启动 15s**：SW-B0 spike 早期实测，Dispatch + OpenDoc6 冷启。本轮不直接使用该数据。
- **端到端均值 11.6s/件**：**Part 2c P0 真 SW smoke**（2026-04-14，5 件 GB sldprt，全部成功）。subprocess-per-convert 模型下，每次都是独立冷启，所以 11.6s ≈ 冷启 + 短 convert + 关闭。本轮 timeout 20s 对齐的是**端到端**预算，不是单纯冷启预算。
- **Stage C 真跑**：8/8 全绿（2026-04-16，commit `0e8ddc7` 之后），step size 44 KB ~ 944 KB。但 Stage C 验收代码（`tools/sw_b9_acceptance.py:321-322`）**仅记录 step_size，不记录每件 convert 耗时**——因此生产大件（944 KB 级别）的**单件耗时未知**，是本轮风险评估的信息 gap。
- **CI 矩阵**：6 个 matrix test job（Windows/Ubuntu × Python 3.10/3.11/3.12）+ 1 个 regression job = 7 个 job。本轮契约 test 仅在 3.11+ 跑，6 个 matrix job 中有 2 个 Python 3.10 job skip，覆盖率 4/6 对"pyproject 解析"级 regression 足够。

---

## 变更清单（最终 8 项）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `pyproject.toml` `[project.optional-dependencies]` | 新增 `solidworks = ['pywin32>=306; sys_platform == "win32"']`。**不**加入 `all` extra |
| 2 | `adapters/solidworks/sw_com_session.py:33` | `SINGLE_CONVERT_TIMEOUT_SEC = 30` → `= 20` |
| 3 | `parts_library.default.yaml:82` | `single_convert_timeout_sec: 30` → `20`，同时更新该行旁注释，改为"基于 Part 2c P0 真 SW smoke 端到端均值 11.6s × 1.72x 冗余" |
| 4 | `tests/test_sw_toolbox_adapter_registration.py:100` | 断言 `== 30` → `== 20` |
| 5 | `docs/design/sw-com-session-threading-model.md` | line 7 `SINGLE_CONVERT_TIMEOUT_SEC = 30` → `= 20`；line 54 "推迟到 Part 2c 的 SW-B0 spike 补课时再定方案" → "P2 已决定：subprocess 隔离（P0 落地）+ 20s timeout（基于 Part 2c P0 真 SW smoke 5 件均值 11.6s × 1.72x 冗余）" |
| 6 | `tests/test_pyproject_contract.py`（新建） | `TestSolidworksExtra` 类 — 使用 `packaging.requirements.Requirement` 解析而非原生字符串比较（避免 PEP 508 语义等价但字符串不等导致的假阴性）；带 `@skipif(sys.version_info < (3, 11))`（stdlib tomllib 可用性） |
| 7 | 本 design doc § 风险节 | 标注"20s 基于 Part 2c P0 smoke 5 件均值，生产大件 outlier 未测；若 Stage C 真跑显示 timeout 命中率 > 10%，回退 25s 候选" |
| 8 | 本 design doc § Follow-up 节 | 列出 solidworks extra 装完后用户 UX 完整链路，标注后续独立任务 |

**总计**：4 处值替换 + 1 处文档同步 + 1 个新 test 文件 + 2 段 design doc 文字 ≈ 35-40 行改动

---

## 数据流一致性

`single_convert_timeout_sec` 的值散布在"声明层"与"运行时层"两条独立链路上，无代码层同步机制。本轮 30→20 必须 5 处同步，否则表面不一致。

```
┌────────────────────────────────────────────────────────────┐
│ 层 1: 声明层（契约）                                       │
├────────────────────────────────────────────────────────────┤
│  parts_library.default.yaml:82  single_convert_timeout_sec │
│       └──锁定契约──▶  test_sw_toolbox_adapter_registration │
│                       .py:100  assert == 30                │
│                                                            │
│  pyproject.toml[optional-deps].solidworks  (本轮新增)       │
│       └──锁定契约──▶  tests/test_pyproject_contract.py     │
│                       (本轮新增)                           │
├────────────────────────────────────────────────────────────┤
│ 层 2: 运行时层（真调用）                                   │
├────────────────────────────────────────────────────────────┤
│  sw_com_session.py:33  SINGLE_CONVERT_TIMEOUT_SEC = 30     │
│       │                                                    │
│       ├──▶ line 127  subprocess.run(timeout=...)           │
│       ├──▶ line 137  log.warning f"timeout {SEC}s"         │
│       └──▶ test_sw_com_session_real_subprocess.py:34       │
│             monkeypatch → 2 (短超时强制，对默认值变动不敏感) │
├────────────────────────────────────────────────────────────┤
│ 层 3: 文档层                                               │
├────────────────────────────────────────────────────────────┤
│  docs/design/sw-com-session-threading-model.md:7    = 30   │
│  docs/design/sw-com-session-threading-model.md:54   "推迟" │
└────────────────────────────────────────────────────────────┘
```

### 一致性处置表（所有引用点）

| 位置 | 当前值 | 处置 | 理由 |
|---|---|---|---|
| `adapters/solidworks/sw_com_session.py:33`（定义） | `= 30` | **改 20** | 运行时常量单点 |
| `adapters/solidworks/sw_com_session.py:127`（调用） | `timeout=SEC` | 不改 | 引用常量自动跟随 |
| `adapters/solidworks/sw_com_session.py:137`（log） | f-string | 不改 | 引用常量自动跟随 |
| `parts_library.default.yaml:82` | `30` | **改 20** | 声明契约 |
| `tests/test_sw_toolbox_adapter_registration.py:100` | `== 30` | **改 20** | 契约断言 |
| `docs/design/sw-com-session-threading-model.md:7` | `= 30` | **改 20** | authoritative 设计文档，扫描发现的原设计遗漏 |
| `docs/design/sw-com-session-threading-model.md:54` | "推迟" | **重写状态** | P2 已闭环 |
| `tests/test_sw_com_session_real_subprocess.py:34` | `monkeypatch 2` | 不改 | 测试用 monkeypatch 强制 2s，对默认值变动不敏感 |
| `tests/fixtures/sw_convert_worker_stub_sleep.py:15` | `sleep 120` | 不改 | stub 固定 sleep，与常量无关 |
| `docs/superpowers/specs\|plans/**/*.md`（历史） | 各种 30 | 不改 | 历史快照 |
| `scripts/sw_spike_*.py` | — | 不改 | Spike 历史脚本 |

---

## 函数调用一致性

`SINGLE_CONVERT_TIMEOUT_SEC` 是 `sw_com_session` 模块的内部常量，**仅** 该模块内部使用；无外部模块 import。因此常量值变更只影响 `_do_convert` 单个 subprocess.run，无跨模块涟漪。

```
SwComSession.convert_sldprt_to_step(sldprt, step_out)  [public API]
  └─▶ SwComSession._do_convert(sldprt, step_out)  [读 TIMEOUT_SEC]
        ├─▶ subprocess.run(..., timeout=SINGLE_CONVERT_TIMEOUT_SEC)  [line 127]
        │     └─▶ 若 20s 内未完成 → TimeoutExpired
        ├─▶ except TimeoutExpired: log.warning  [line 137]
        │     └─▶ self._consecutive_failures += 1
        │     └─▶ if >= CIRCUIT_BREAKER_THRESHOLD (=3): self._unhealthy = True
        └─▶ last_convert_diagnostics 记录 ("timeout" 分类)  [Stage C 可观测性, commit 0e8ddc7]
```

**一致性结论**：
- 常量值变更与熔断器语义正交（熔断依赖"失败计数 >= 3"，不依赖具体 timeout 数值）
- Stage C 可观测性自动把 20s 下的 timeout 事件记录到 `last_convert_diagnostics`，与 30s 无差别

---

## 管线流程融合

### A（solidworks extra）融合路径

```
pip install 'cad-spec-gen[solidworks]'  (Windows)
  └─▶ pywin32 装上
        └─▶ sw_detect.py::_check_pywin32() = True
              └─▶ SwDetectInfo.pywin32_available = True
                    └─▶ SwToolboxAdapter.is_available() 6 项 gate 中此项通过
                          └─▶ parts_resolver 按 mapping 顺序路由到
                              SwToolboxAdapter (GB/ISO/DIN 命中)
```

在 Linux/macOS 上 `pip install 'cad-spec-gen[solidworks]'` 成功但 pywin32 被 marker 跳过，`SwDetectInfo.pywin32_available=False` → `SwToolboxAdapter.is_available()=False` → resolver 回落到下一级 adapter（bd_warehouse → jinja_primitive）。**零新融合代码**，全链路由现有 sw_detect 检测链自动完成。

### C（timeout 30→20s）融合路径

```
tools/sw_b9_acceptance.py::stage_c_session_restart(matched)
  └─▶ SwComSession().convert_sldprt_to_step(sldprt, step_path)
        └─▶ _do_convert()  [20s timeout]
              └─▶ last_convert_diagnostics 记录 (commit 0e8ddc7)
        └─▶ per_target 记录 (step_size + failed + diag)
```

Stage C 可观测性已由 commit `0e8ddc7` 提供，timeout 事件自动进入 `per_target.diag`。**零新融合代码**。

---

## 测试策略（approach β）

### 新增契约测试

**位置**：`tests/test_pyproject_contract.py`（新建；未来其他 pyproject 契约 test 同文件扩展）

**关键设计决策**：使用 `packaging.requirements.Requirement` 解析而非原生字符串比较。

**为什么**：pyproject.toml 的 `'pywin32>=306; sys_platform == "win32"'` 写法有多种 PEP 508 等价形式（空格/引号/marker 顺序）。字符串 `==` 断言对这些等价改动敏感，会产生**假阴性**（test fail 而 pyproject 实际语义正确）。用 `Requirement` 解析后基于 name/specifier/marker 的语义字段比对，更健壮。

```python
# 核心骨架（实际由 plan 细化）
from packaging.requirements import Requirement

def test_solidworks_extra_has_pywin32_with_windows_marker():
    deps = _load_pyproject_optional_deps()
    assert "solidworks" in deps

    reqs = [Requirement(s) for s in deps["solidworks"]]
    pywin32 = next((r for r in reqs if r.name == "pywin32"), None)
    assert pywin32 is not None
    # specifier 语义断言：容许 >=306, >=306.0 等等价写法
    assert pywin32.specifier.contains("306")
    # marker 语义断言：PEP 508 marker 解析后语义 == win32-only
    assert pywin32.marker is not None
    assert pywin32.marker.evaluate({"sys_platform": "win32"}) is True
    assert pywin32.marker.evaluate({"sys_platform": "linux"}) is False

def test_all_extra_does_not_contain_pywin32():
    deps = _load_pyproject_optional_deps()
    reqs = [Requirement(s) for s in deps.get("all", [])]
    assert all(r.name != "pywin32" for r in reqs), "all extra 不应含 pywin32（D1 决策）"
```

### Python 版本兼容

```python
import sys
import pytest

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="tomllib 仅 Python 3.11+ 可用；3.10 job 的 regression 由 3.11/3.12 的 4 个 job 兜底"
)
```

`packaging` 是 pip 自带依赖，通常已在环境里；若 CI 环境意外没有可改为 `pytest.importorskip("packaging")`。

### 现有测试更新

- `tests/test_sw_toolbox_adapter_registration.py:100` 断言 `com_cfg.get("single_convert_timeout_sec") == 30` → `== 20`

### 不做的测试

- **pip install 实际可跑**：交由 hatch build + CI 中 `pip install -e .[all]` 隐式验证
- **`SINGLE_CONVERT_TIMEOUT_SEC = 20` 在 `_do_convert` 被真用到**：现有 `test_sw_com_session_subprocess.py` 已 mock 覆盖
- **Linux 下 extra 装成 no-op**：需实际 pip install，成本过高；contract test 已验证 marker 语义

---

## 风险与缓解

### R-1 timeout 20s 对生产大件 outlier 可能不够

**事实**：
- 支持 20s 的正面数据：Part 2c P0 真 SW smoke 5 件均值 11.6s，20 / 11.6 = **1.72x 冗余**
- 信息 gap：5 件 smoke 样本过小（n=5），**无方差数据**；Stage C 真跑 8/8 只记 step_size 不记耗时（`tools/sw_b9_acceptance.py:321-322`），最大 944 KB 件的单件耗时未知；生产 BOM 可能含非标准件大几何，单件耗时可能超出 smoke 样本范围

**正确的叙述**（不是"纯粹安全"也不是"纯粹风险"）：
> 均值上 1.72x 冗余充足；但 smoke 样本 n=5 无方差数据，生产 BOM 可能含 >20s outlier（特别是非标准件大几何）。

**缓解**：
- **熔断器兜底**（`CIRCUIT_BREAKER_THRESHOLD = 3`）：连续 3 次失败 → `_unhealthy=True` → 后续 convert 被跳过 → resolver 回落到下一级 adapter（sw_toolbox → bd_warehouse → jinja_primitive），最终装配产出不受影响
- **Stage C 可观测性**（commit `0e8ddc7`）：timeout 事件被 `last_convert_diagnostics` 捕获，后续 Stage C 真跑可按 `per_target.diag` 统计 timeout 命中率
- **回退阈值**：若后续 Stage C 真跑显示 timeout 命中率 > **10%**（经验阈值），回退 25s 候选；若 > 25%，考虑回退 30s 或重新评估

### R-2 双 source of truth 同步成本（S-1）

**事实**：YAML 声明 `single_convert_timeout_sec: 20` 与代码常量 `SINGLE_CONVERT_TIMEOUT_SEC = 20` 是两条独立数字，无代码层同步机制。本轮需要 5 处人工同步。

**缓解**：本轮不彻底解决（要么走 YAML 可配，要么删 YAML 字段 + 断言）——两种方案都超出 P2 packaging scope。作为 Follow-up F-2 标注。

### R-3 pywin32 `>=306` 下限宽松

**事实**：pywin32 306 是 2023 年版本；2026 年主流环境 pip 安装会拉到 311+。下限在**新环境**里几乎不发挥作用；仅对**已锁 pywin32 的老环境**起防护（避免挑到 306 之前版本）。

**缓解**：无需本轮处理；若未来 pywin32 出现 breaking change，再评估是否加 upper bound。

### R-4 contract test 仅在 3.11+ 跑

**事实**：`tomllib` 仅 Python 3.11+ 可用。CI 6 个 matrix test job 中，2 个 Python 3.10 job（Windows + Ubuntu）skip 该 test；3.11/3.12 的 4 个 job 跑，覆盖 4/6。

**缓解**：接受。pyproject 解析级 regression 被 4/6 job 覆盖足够；真要补 3.10 覆盖，需引入 `tomli` 依赖或 `pytest.importorskip`，性价比低。

---

## Follow-up

本设计明确排除但将来需独立处理的任务：

| # | 任务 | 触发时机 |
|---|---|---|
| F-1 | **`sw-inspect` 子命令** — 一次性展示 SW 环境 / toolbox 索引 / 匹配率样本 / 熔断状态 | 用户首次报"SW 集成为什么没生效"时 |
| F-2 | **双 source of truth 彻底解决**：要么 YAML 可配（需 config 读取链路 + 注入 `SwComSession.__init__`），要么删 YAML 字段 + `test_sw_toolbox_adapter_registration.py` 对应断言（单一 source of truth = 代码常量） | 下次调整 timeout 时 |
| F-3 | **README / `cad-skill-check` 文档更新** — 说明 `pip install 'cad-spec-gen[solidworks]'` 装完后的启用条件（SW 本身已装 / toolbox 索引 build / 自动检测） | Part 2c 收尾或 Phase SW-D 启动时 |
| F-4 | **Stage C 耗时记录** — `tools/sw_b9_acceptance.py` 给每件 convert 加 `elapsed_sec` 记录，为将来 timeout 调优提供方差数据 | 下次 Stage C 真跑（或手动补一次） |
| F-5 | **pyproject contract test 扩展** — 若加入 F-3 的 README / check 或其他 extras，扩展 `test_pyproject_contract.py` 覆盖 | F-3 同步 |
| F-6 | **CI 新增 `pip install '.[solidworks]'` 集成 job** — 实际验证 extra 可装 | 若 F-5 发现 contract test 有盲区时 |

### solidworks extra 装完后用户 UX 完整链路

```
pip install 'cad-spec-gen[solidworks]'
    ↓
Windows + SolidWorks 已装
    ↓
首次使用：sw_detect 自动检测路径 + toolbox 位置
    ↓
按需：SwToolboxAdapter.is_available() 首次调用 → 自动 build toolbox 索引（耗时）
    ↓
真 BOM 查询：sw_toolbox → bd_warehouse → jinja_primitive 路由
    ↓
若 convert 失败：熔断器 open → 整会话回落到下级 adapter
```

用户在**缺失任一前置条件**时会遇到的体验：

| 缺失项 | 现象 | 需要的文档/工具 |
|---|---|---|
| pywin32 未装（Linux/macOS 或 Windows 未装 extra） | `SwDetectInfo.pywin32_available=False`，自动跳过 SW 路径，无报错 | README 说明 `pip install '...[solidworks]'` 仅 Windows 有效（F-3） |
| pywin32 已装但 SW 软件未装 | `SwDetectInfo.solidworks_installed=False` | `cad-skill-check` 报告 SW 未装（F-3 补） |
| SW 已装但 toolbox 未初始化 | 首次匹配时触发 build，耗时 | `sw-inspect` 主动触发 + 可视化状态（F-1） |
| toolbox 已初始化但匹配率低 | 静默回落到 bd_warehouse | `sw-inspect` 显示匹配率样本（F-1） |

---

## 决策记录（历史链）

| 决策 | 时间 | 指向 |
|---|---|---|
| 决策 #10 | 2026-04-13 | SINGLE_CONVERT_TIMEOUT_SEC = 30（初始值，保守） |
| 决策 #11 | 2026-04-13 | RESTART_EVERY_N_CONVERTS = 50（session 模型）— Part 2c P0 后废弃 |
| **决策 #36**（本设计） | **2026-04-16** | **SINGLE_CONVERT_TIMEOUT_SEC 30 → 20s**。依据 Part 2c P0 真 SW smoke 端到端均值 11.6s × 1.72x 冗余。回退阈值：Stage C 真跑 timeout 命中率 > 10% → 候选 25s |
| **决策 #37**（本设计） | **2026-04-16** | **`pyproject.toml [project.optional-dependencies] solidworks = ['pywin32>=306; sys_platform == "win32"']`**，`all` extra 不含 pywin32 |

---

## 实施顺序建议（供 writing-plans 参考）

1. **先做 C（timeout 30→20）**：5 处同步 + 1 处断言更新，纯值替换，范围清晰，TDD 直接：`test_sw_toolbox_adapter_registration.py:100` 改 20 → 运行 fail → 改 YAML + 代码常量 → pass → 补文档
2. **再做 A（pyproject solidworks extra）**：TDD：先写 `test_pyproject_contract.py` → fail（solidworks key 不存在）→ 改 pyproject → pass
3. **最后补文档**：`docs/design/sw-com-session-threading-model.md` 两处同步（变更 #5）

两段独立可并行，但顺序 C → A 更能保证每段代码 change 伴随 test change，避免"一次大 commit 后补 test"的反模式。
