# Part 2c P2 Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实施 Part 2c P2（A + C）——pyproject 新增 solidworks optional extra + `SINGLE_CONVERT_TIMEOUT_SEC` 30→20s + 3 处 UX 提示同步，让 extra 从"影子功能"变成用户可发现的真实集成路径。

**Architecture:** 纯配置 / 值替换 / 文档更新，无新模块或架构变更。A 子任务的价值**依赖**UX 3 处提示同步（否则 extra 无人发现）；C 子任务的调优**依赖** Follow-up F-4a/F-4b/F-7 数据链路（不在本 plan，spec 已标注）。严格 TDD：改生产 YAML 先让现有契约 test fail，再同步断言；pyproject 改动先写 contract test fail，再加 extra pass。

**Tech Stack:** pyproject.toml / Python 3.11+ (tomllib) / `packaging.requirements` / pytest / YAML / markdown

**Spec:** `docs/superpowers/specs/2026-04-16-part2c-p2-packaging-design.md`（已 approve）

---

## File Structure

| 文件 | 类型 | 责任 |
|---|---|---|
| `pyproject.toml` | Modify | `[project.optional-dependencies]` 新增 solidworks extra |
| `adapters/solidworks/sw_com_session.py` | Modify | 常量 `SINGLE_CONVERT_TIMEOUT_SEC` 30→20 |
| `parts_library.default.yaml` | Modify | `single_convert_timeout_sec: 20` + 注释补 1.72x 冗余依据 |
| `tests/test_sw_toolbox_adapter_registration.py` | Modify | 断言 `== 20` |
| `tests/test_pyproject_contract.py` | Create | Contract test：solidworks extra 字段 / all extra 不含 pywin32 |
| `docs/design/sw-com-session-threading-model.md` | Modify | line 7 常量值同步；line 54 "推迟方案"→"P2 已落地" |
| `tools/sw_warmup.py` | Modify | `_check_preflight` pywin32 缺失提示指向 extra |
| `scripts/sw_spike_diagnose.py` | Modify | 诊断结论指向 extra |
| `tools/hybrid_render/check_env.py` | Modify | 加平台区分 + 提示 extra |
| `docs/superpowers/decisions.md` | Modify | 追加 `## #36` `## #37` |

---

## Tasks

### Task 1: C — YAML 值 + 注释 + 现有契约 test 断言同步

**Files:**
- Modify: `parts_library.default.yaml`（行 76-83 附近 `com:` 段）
- Modify: `tests/test_sw_toolbox_adapter_registration.py:100`

- [ ] **Step 1: 改 YAML 值 + 补注释**

Edit `parts_library.default.yaml`，找到：

```yaml
  # COM subprocess 超时 + 熔断（Part 2c P0 后配置瘦身）
  # cold_start / restart / idle_shutdown 在 subprocess-per-convert 模型下
  # 已不存在——每次 convert 是独立冷启，父进程不持久 COM 状态。
  com:
    single_convert_timeout_sec: 30
    circuit_breaker_threshold: 3
```

替换为：

```yaml
  # COM subprocess 超时 + 熔断（Part 2c P0 后配置瘦身）
  # cold_start / restart / idle_shutdown 在 subprocess-per-convert 模型下
  # 已不存在——每次 convert 是独立冷启，父进程不持久 COM 状态。
  # single_convert_timeout_sec: 20s 基于 Part 2c P0 真 SW smoke 端到端
  # 均值 11.6s × 1.72x 冗余（2026-04-16 决策 #36）；回退判定依据见
  # Follow-up F-4a/F-4b/F-7
  com:
    single_convert_timeout_sec: 20
    circuit_breaker_threshold: 3
```

- [ ] **Step 2: 跑现有契约 test，预期 fail（证明守门生效）**

Run: `.venv/Scripts/pytest.exe tests/test_sw_toolbox_adapter_registration.py::TestDefaultYamlConfig::test_default_yaml_provides_solidworks_toolbox_section -v`

Expected: `FAILED` with `AssertionError`（断言 `== 30` 与 YAML 实际 20 不匹配；契约失守即刻报警）

- [ ] **Step 3: 同步 test 断言**

Edit `tests/test_sw_toolbox_adapter_registration.py:100`。找到：

```python
        assert com_cfg.get("single_convert_timeout_sec") == 30
```

替换为：

```python
        assert com_cfg.get("single_convert_timeout_sec") == 20
```

- [ ] **Step 4: 再跑 test 验证 pass**

Run: `.venv/Scripts/pytest.exe tests/test_sw_toolbox_adapter_registration.py::TestDefaultYamlConfig::test_default_yaml_provides_solidworks_toolbox_section -v`

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add parts_library.default.yaml tests/test_sw_toolbox_adapter_registration.py
git commit -m "feat(sw-b-part2c-p2): YAML single_convert_timeout_sec 30→20s

契约切换：先改 YAML → 现有 test fail 证明守门生效 → 同步断言 pass。
补注释标注 11.6s × 1.72x 冗余依据（决策 #36）。"
```

---

### Task 2: C — 代码常量 `SINGLE_CONVERT_TIMEOUT_SEC` 30→20

**Files:**
- Modify: `adapters/solidworks/sw_com_session.py:33`

- [ ] **Step 1: 改常量定义**

Edit `adapters/solidworks/sw_com_session.py`，找到第 33 行：

```python
SINGLE_CONVERT_TIMEOUT_SEC = 30
```

替换为：

```python
SINGLE_CONVERT_TIMEOUT_SEC = 20
```

- [ ] **Step 2: 跑 SW 会话相关测试不应回归**

Run: `.venv/Scripts/pytest.exe tests/test_sw_com_session_subprocess.py tests/test_sw_com_session_real_subprocess.py -v`

Expected: All PASSED

（`test_sw_com_session_real_subprocess.py:34` 用 monkeypatch 强制 2s 短超时，对默认值变动不敏感；subprocess mock 测试不依赖具体 timeout 数值。）

- [ ] **Step 3: Commit**

```bash
git add adapters/solidworks/sw_com_session.py
git commit -m "feat(sw-b-part2c-p2): SINGLE_CONVERT_TIMEOUT_SEC 常量 30→20s

与 YAML 声明对齐；熔断器语义不变（3 次失败仍 open）。"
```

---

### Task 3: C — 设计文档 `sw-com-session-threading-model.md` 同步

**Files:**
- Modify: `docs/design/sw-com-session-threading-model.md`（line 7 + line 54）

- [ ] **Step 1: 改 line 7 的常量值**

Edit `docs/design/sw-com-session-threading-model.md`，找到：

```
关键常量（定义在 `adapters/solidworks/sw_com_session.py` 顶部）：`RESTART_EVERY_N_CONVERTS = 50`（决策 #11），`IDLE_SHUTDOWN_SEC = 300`（5 分钟），`COLD_START_TIMEOUT_SEC = 90`，`SINGLE_CONVERT_TIMEOUT_SEC = 30`，`CIRCUIT_BREAKER_THRESHOLD = 3`。
```

替换为：

```
关键常量（定义在 `adapters/solidworks/sw_com_session.py` 顶部）：`RESTART_EVERY_N_CONVERTS = 50`（决策 #11），`IDLE_SHUTDOWN_SEC = 300`（5 分钟），`COLD_START_TIMEOUT_SEC = 90`，`SINGLE_CONVERT_TIMEOUT_SEC = 20`（决策 #36，2026-04-16 由 30 下调），`CIRCUIT_BREAKER_THRESHOLD = 3`。
```

（注意：前三个常量 `RESTART_EVERY_N_CONVERTS / IDLE_SHUTDOWN_SEC / COLD_START_TIMEOUT_SEC` 在 Part 2c P0 后已废弃，但本 plan 不扩 scope 清理它们——这属于 F-2 彻底重构范畴。只改 `SINGLE_CONVERT_TIMEOUT_SEC` 一处。）

- [ ] **Step 2: 改 line 54 的"推迟"状态**

找到：

```
本模型**不使用** Timer 或后台线程。理由同上。`SINGLE_CONVERT_TIMEOUT_SEC` 的超时保护推迟到 Part 2c 的 SW-B0 spike 补课时再定方案（可能方向：subprocess 隔离 / ctypes.wintypes.WAIT_TIMEOUT / SW API 自带的 cancel）。
```

替换为：

```
本模型**不使用** Timer 或后台线程。理由同上。`SINGLE_CONVERT_TIMEOUT_SEC` 的超时保护已在 Part 2c P0 落地——**subprocess-per-convert 隔离**（每次 convert 独立进程，subprocess.run 守 timeout）+ 20s timeout 值（决策 #36，基于 Part 2c P0 真 SW smoke 5 件均值 11.6s × 1.72x 冗余）。
```

- [ ] **Step 3: Commit**

```bash
git add docs/design/sw-com-session-threading-model.md
git commit -m "docs(sw-b-part2c-p2): threading-model 同步 timeout = 20s (决策 #36)

line 7 常量值；line 54 从\"推迟方案\"更新为\"P2 P0 已落地 subprocess 隔离 + 20s\"。
前三个过时常量（RESTART/IDLE/COLD_START）保留不动，留给 F-2 彻底重构。"
```

---

### Task 4: A — 新建 pyproject contract test（test 先于实现）

**Files:**
- Create: `tests/test_pyproject_contract.py`

- [ ] **Step 1: 写 test 文件**

Create `tests/test_pyproject_contract.py` with this exact content:

```python
"""pyproject.toml 字段契约测试（Part 2c P2 决策 #37）。

保护 `[project.optional-dependencies]` 等字段契约不被意外破坏。
未来若新增其他 extras，同文件扩展 TestXxxExtra 类。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# tomllib 仅 Python 3.11+；3.10 的 CI job 跳过
# 3.11/3.12 × Windows/Ubuntu = 4 个 job 覆盖 pyproject 解析级 regression 足够
pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="tomllib 仅 Python 3.11+ 可用；3.10 job 由 3.11/3.12 的 4 个 job 兜底",
)

# 强制 importorskip 而非假设"packaging 通常已在"——本项目 uv 环境已知有
# partcad vs bd-warehouse 依赖冲突风险，健壮性优先
pytest.importorskip("packaging")

from packaging.requirements import Requirement  # noqa: E402

PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _load_pyproject_optional_deps() -> dict[str, list[str]]:
    """解析 pyproject.toml 返回 optional-dependencies 段。"""
    import tomllib
    with PYPROJECT_PATH.open("rb") as f:
        data = tomllib.load(f)
    return data.get("project", {}).get("optional-dependencies", {})


class TestSolidworksExtra:
    """决策 #37：pyproject.toml 新增 solidworks optional extra。"""

    def test_solidworks_extra_has_pywin32_with_windows_marker(self):
        deps = _load_pyproject_optional_deps()
        assert "solidworks" in deps, "必须有 solidworks extra（决策 #37）"

        reqs = [Requirement(s) for s in deps["solidworks"]]
        pywin32 = next((r for r in reqs if r.name == "pywin32"), None)
        assert pywin32 is not None, "solidworks extra 必须含 pywin32"

        # specifier 语义断言：显式检查 operator + version
        # 不用 .contains("306")——它对 ==306（锁死版本）和 >=306（下限）
        # 都返回 True，但两者语义完全不同，必须区分
        specs = list(pywin32.specifier)
        assert len(specs) == 1, "pywin32 应只有一个 specifier"
        assert specs[0].operator == ">=", \
            f"operator 必须是 >=（下限），实际: {specs[0].operator}"
        assert specs[0].version == "306"

        # marker 语义断言：PEP 508 marker 解析后语义 == win32-only
        assert pywin32.marker is not None, "pywin32 必须有 sys_platform marker"
        assert pywin32.marker.evaluate({"sys_platform": "win32"}) is True
        assert pywin32.marker.evaluate({"sys_platform": "linux"}) is False
        assert pywin32.marker.evaluate({"sys_platform": "darwin"}) is False

    def test_all_extra_does_not_contain_pywin32(self):
        """D1 决策：`all` extra 不含 pywin32（保持 all 全平台可装）。"""
        deps = _load_pyproject_optional_deps()
        reqs = [Requirement(s) for s in deps.get("all", [])]
        assert all(r.name != "pywin32" for r in reqs), \
            "all extra 不应含 pywin32（D1 决策：避免 marker 污染扩散）"
```

- [ ] **Step 2: 跑 test，预期 fail（solidworks key 不存在）**

Run: `.venv/Scripts/pytest.exe tests/test_pyproject_contract.py -v`

Expected:
```
tests/test_pyproject_contract.py::TestSolidworksExtra::test_solidworks_extra_has_pywin32_with_windows_marker FAILED
AssertionError: 必须有 solidworks extra（决策 #37）
```

`test_all_extra_does_not_contain_pywin32` 应 PASS（实现前已满足）。

- [ ] **Step 3: Commit（test 先提交，下一 task 提交实现）**

```bash
git add tests/test_pyproject_contract.py
git commit -m "test(sw-b-part2c-p2): 添加 pyproject contract test (solidworks extra)

test 先于实现。跑后预期 FAILED（solidworks key 不存在），下一 task
加 pyproject 字段让 test pass。

关键设计：用 packaging.requirements.Requirement 解析，显式检查
operator == '>='（避免 .contains('306') 对 ==306/>=306 无法区分）。
强制 pytest.importorskip('packaging') 应对 uv 环境依赖冲突。"
```

---

### Task 5: A — pyproject.toml 新增 solidworks extra

**Files:**
- Modify: `pyproject.toml`（`[project.optional-dependencies]` 段）

- [ ] **Step 1: Edit pyproject.toml**

Edit `pyproject.toml`，找到：

```toml
parts_library_pc = ["PyYAML>=6.0", "partcad>=0.7.0"]
all = [
    "cadquery>=2.0",
    "ezdxf>=0.18",
    "matplotlib>=3.5",
    "Pillow>=9.0",
    "PyYAML>=6.0",
]
```

替换为（在 `parts_library_pc` 行后、`all` 前插入 solidworks 定义，`all` 内容不变）：

```toml
parts_library_pc = ["PyYAML>=6.0", "partcad>=0.7.0"]
# SolidWorks 集成（Windows only，决策 #37 2026-04-16）。Linux/macOS 上
# sys_platform marker 让 pywin32 被 pip 跳过，extra 装成 no-op（sw_detect
# 运行时会通过 UX 提示告知平台限制，见 tools/hybrid_render/check_env.py）
solidworks = ['pywin32>=306; sys_platform == "win32"']
all = [
    "cadquery>=2.0",
    "ezdxf>=0.18",
    "matplotlib>=3.5",
    "Pillow>=9.0",
    "PyYAML>=6.0",
]
```

**重要：** `all` extra **不**加入 `pywin32`——这是 D1 决策，contract test `test_all_extra_does_not_contain_pywin32` 会守门。

- [ ] **Step 2: 跑 contract test 验证 pass**

Run: `.venv/Scripts/pytest.exe tests/test_pyproject_contract.py -v`

Expected:
```
tests/test_pyproject_contract.py::TestSolidworksExtra::test_solidworks_extra_has_pywin32_with_windows_marker PASSED
tests/test_pyproject_contract.py::TestSolidworksExtra::test_all_extra_does_not_contain_pywin32 PASSED
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat(sw-b-part2c-p2): 新增 solidworks optional extra (决策 #37)

pywin32>=306 带 sys_platform == 'win32' marker；Linux/macOS 装成 no-op。
all extra 刻意不含 pywin32（D1 决策），避免 marker 污染扩散。

注意：本改动单独落地只是 pyproject 声明改动，还不具实用价值——用户
不知道 extra 存在。下三个 task（#6-8）同步 3 处 UX 提示指向这个 extra，
extra 的价值才真正兑现。"
```

---

### Task 6: UX — `tools/sw_warmup.py` 提示指向 extra

**Files:**
- Modify: `tools/sw_warmup.py:252`

- [ ] **Step 1: Edit 提示文案**

Edit `tools/sw_warmup.py`，找到第 252 行（在 `_check_preflight` 函数内）：

```python
    if not info.pywin32_available:
        return False, "pywin32 未安装；请运行 `pip install pywin32`"
```

替换为：

```python
    if not info.pywin32_available:
        return False, (
            "pywin32 未安装；请运行 "
            "`pip install 'cad-spec-gen[solidworks]'`（Windows only）"
        )
```

- [ ] **Step 2: 验证模块可导入（无语法错误）**

Run: `.venv/Scripts/python.exe -c "from tools import sw_warmup; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add tools/sw_warmup.py
git commit -m "feat(sw-b-part2c-p2): sw_warmup 提示指向 solidworks extra

原: pip install pywin32（用户不知道 extra 存在）
新: pip install 'cad-spec-gen[solidworks]'（Windows only）

A 子任务价值兑现的必要条件之一（spec § 变更清单 #7）。"
```

---

### Task 7: UX — `scripts/sw_spike_diagnose.py` 提示指向 extra

**Files:**
- Modify: `scripts/sw_spike_diagnose.py:44`

- [ ] **Step 1: Edit 诊断结论文案**

Edit `scripts/sw_spike_diagnose.py`，找到第 44 行：

```python
        print("\n诊断结论：pywin32 未安装或不兼容当前 Python。跑 `pip install pywin32` 再试。")
```

替换为：

```python
        print(
            "\n诊断结论：pywin32 未安装或不兼容当前 Python。"
            "跑 `pip install 'cad-spec-gen[solidworks]'` 再试（Windows only）。"
        )
```

- [ ] **Step 2: 验证脚本语法**

Run: `.venv/Scripts/python.exe -c "import ast; ast.parse(open('scripts/sw_spike_diagnose.py', encoding='utf-8').read())"`

Expected: 无输出，无 error

- [ ] **Step 3: Commit**

```bash
git add scripts/sw_spike_diagnose.py
git commit -m "feat(sw-b-part2c-p2): sw_spike_diagnose 提示指向 solidworks extra

A 子任务价值兑现的必要条件之一（spec § 变更清单 #8）。"
```

---

### Task 8: UX — `tools/hybrid_render/check_env.py` 加平台区分

**Files:**
- Modify: `tools/hybrid_render/check_env.py`（line 286 附近 else 分支）

- [ ] **Step 1: 确认文件已 import sys**

Run: `.venv/Scripts/python.exe -c "import re, pathlib; src = pathlib.Path('tools/hybrid_render/check_env.py').read_text(encoding='utf-8'); print('has import sys:', bool(re.search(r'^import sys', src, re.M)))"`

Expected: `has import sys: True`

如果输出 `False`，则在 Step 2 之前在文件顶部 import 区追加 `import sys`。

- [ ] **Step 2: Edit else 分支加平台区分**

Edit `tools/hybrid_render/check_env.py`，找到第 285-286 行附近：

```python
        else:
            path_b = "Toolbox ✗ (pywin32 未安装)"
```

替换为：

```python
        elif sys.platform != "win32":
            # Windows only——Linux/macOS 合法跳过，非错误（D1-2 决策：
            # sys_platform marker 让 extra 在非 Windows 平台装成 no-op）
            path_b = "Toolbox — (此功能 Windows only，当前平台跳过)"
        else:
            path_b = (
                "Toolbox ✗ (pywin32 未安装；"
                "运行 `pip install 'cad-spec-gen[solidworks]'`)"
            )
```

- [ ] **Step 3: 验证模块可导入**

Run: `.venv/Scripts/python.exe -c "from tools.hybrid_render import check_env; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add tools/hybrid_render/check_env.py
git commit -m "feat(sw-b-part2c-p2): check_env 加平台区分 + 提示 extra

- Windows 上: 提示 pip install 'cad-spec-gen[solidworks]'
- Linux/macOS 上: 标为 \"Windows only, 当前平台跳过\"（非错误）

同时解决 D1-1（extra 提示）+ D1-2（Linux UX 盲区）两个审查发现。
A 子任务价值兑现的必要条件之一（spec § 变更清单 #9）。"
```

---

### Task 9: decisions.md 追加 #36 + #37

**Files:**
- Modify: `docs/superpowers/decisions.md`（末尾追加）

- [ ] **Step 1: 确认当前最大编号为 #35**

Run: `.venv/Scripts/python.exe -c "import re, pathlib; src = pathlib.Path('docs/superpowers/decisions.md').read_text(encoding='utf-8'); nums = [int(m) for m in re.findall(r'^## #(\d+)', src, re.M)]; print('max decision number:', max(nums) if nums else 'none')"`

Expected: `max decision number: 35`

如果不是 35，说明 decisions.md 在本 plan 写作后有人加过新决策——暂停，向 plan 维护者反馈冲突。

- [ ] **Step 2: 末尾追加两条决策**

Edit `docs/superpowers/decisions.md`，在文件末尾追加：

```markdown

---

## #36 SINGLE_CONVERT_TIMEOUT_SEC 30→20s（2026-04-16）

**决定**：`adapters/solidworks/sw_com_session.py` 的 `SINGLE_CONVERT_TIMEOUT_SEC` 从 30 下调为 20。`parts_library.default.yaml` 的声明同步更新；`docs/design/sw-com-session-threading-model.md` 线程模型文档同步。

**依据**：Part 2c P0 真 SW smoke（2026-04-14，5 件 GB sldprt 全部成功）subprocess 模型端到端均值 11.6s/件；20 / 11.6 = 1.72x 冗余。

**已知信息 gap**：Stage C 验收代码只记 `step_size` 不记 `elapsed_sec`，大件 outlier 耗时未测；5 件 smoke 无方差数据。

**兜底与回退**：
- **兜底**：熔断器（3 次连续失败 → `_unhealthy`）+ Stage C 可观测性（commit `0e8ddc7` 的 `last_convert_diagnostics`）+ resolver 回落链路（sw_toolbox → bd_warehouse → jinja_primitive）
- **回退通道**：Follow-up F-4a（临时把 timeout 放大到 120s 测真实 `elapsed_sec` 分布，避免 20s 下的上限截断陷阱）+ F-4b（`stage_c.json` 追加 `timeout_rate` 字段）+ F-7（基于 F-4a p95 和 F-4b 命中率同时决策是否回退 25s/30s）

**spec**: `docs/superpowers/specs/2026-04-16-part2c-p2-packaging-design.md`

---

## #37 pyproject.toml solidworks optional extra（2026-04-16）

**决定**：`pyproject.toml [project.optional-dependencies]` 新增 `solidworks = ['pywin32>=306; sys_platform == "win32"']`；`all` extra 不含 pywin32。

**依据**：消除"用户需手动装 pywin32"的 friction；`sys_platform` marker 让 Linux/macOS 上 extra 装成 no-op 而非 pip 硬 reject，与项目 `@requires_solidworks` marker 的"Linux 用户合法"态度一致。

**UX 闭环**：本决策依赖 3 处代码提示同步（`tools/sw_warmup.py:252` / `scripts/sw_spike_diagnose.py:44` / `tools/hybrid_render/check_env.py:286`），否则 extra 成"影子功能"无人使用。这 3 处同步本 plan 已一并完成（Task 6-8）。

**契约守门**：`tests/test_pyproject_contract.py::TestSolidworksExtra` 用 `packaging.requirements.Requirement` 解析并显式检查 operator、version、marker 三个字段，避免字符串 `==` 断言对 PEP 508 等价写法假阴性。

**spec**: `docs/superpowers/specs/2026-04-16-part2c-p2-packaging-design.md`
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/decisions.md
git commit -m "docs(decisions): 追加 #36 timeout 20s + #37 solidworks extra

#36: SINGLE_CONVERT_TIMEOUT_SEC 30→20 + F-4a/F-4b/F-7 回退通道
#37: pyproject solidworks extra + 3 处 UX 提示闭环"
```

---

### Task 10: 整体回归 + ruff + 可选 push

**Files:** （无修改；仅验证）

- [ ] **Step 1: 跑全量 SW 相关测试 + contract test**

Run: `.venv/Scripts/pytest.exe tests/test_sw_*.py tests/test_pyproject_contract.py -v --tb=short`

Expected: All PASSED（约 190+ test）。无任何 FAILED。若有意外 fail，先定位根因，不要为了让 test 通过而回退本 plan 的改动。

- [ ] **Step 2: ruff check 本 plan 修改的 Python 文件**

Run:
```
.venv/Scripts/ruff.exe check tests/test_pyproject_contract.py tools/sw_warmup.py scripts/sw_spike_diagnose.py tools/hybrid_render/check_env.py adapters/solidworks/sw_com_session.py
```

Expected: `All checks passed!`

- [ ] **Step 3: git log 核对本 plan 产生的 commit**

Run: `git log --oneline -10`

Expected: 看到本 plan 产生的 9 个 commit（对应 Task 1-9，每 task 一个），分支干净（`git status` 应 clean）。

- [ ] **Step 4: (可选)推送到 origin 触发 CI**

按 CLAUDE.md "DO NOT push unless explicitly asked"——需问用户确认后才 push。

若确认 push：

```bash
git push origin main
```

Expected: push 成功；GitHub Actions `tests` workflow 自动触发。若 CI 失败，定位后修复（不要 revert 本 plan）。

---

## Follow-up 引用（不在本 plan，spec 已标注）

- **F-1** `sw-inspect` 子命令 — 独立 brainstorming
- **F-2** 双 source of truth 彻底解决 — 下次调 timeout 时
- **F-3** README / `cad-help` skill 知识库更新 — 本轮变更 #7-9 已覆盖代码内 UX；此 Follow-up 是 skill 知识层（README 面向用户 / `cad-help` 面向 AI）延伸
- **F-4a** 临时放大 timeout 到 120s，跑真实 Stage C 测未截断的 `elapsed_sec` 分布
- **F-4b** `stage_c.json` 追加 `timeout_rate` 字段
- **F-5** contract test 扩展其他 extras
- **F-6** CI 新增 `pip install '.[solidworks]'` 集成 job
- **F-7** timeout 回退 watch（基于 F-4a + F-4b 决策）

---

## Plan 摘要

- 10 个 Task，每个 2-5 min 粒度，每个一个 commit
- 总改动 ~60-80 行，跨 10 个文件
- 严格 TDD：Task 1 改 YAML 先让现有 test fail → 同步断言；Task 4-5 新 test 先 fail → 改 pyproject pass
- A 子任务（pyproject extra）+ UX 3 处提示（Task 5-8）形成闭环，缺一则 extra 成"影子功能"
- C 子任务（timeout 20s，Task 1-3）依赖 F-4a/F-4b/F-7 数据链路完成调优闭环（Follow-up）
- Task 10 回归验证，可选 push
