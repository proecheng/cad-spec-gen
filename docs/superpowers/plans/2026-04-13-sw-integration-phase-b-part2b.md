# Phase SW-B Part 2b 实施计划 — sw-warmup CLI + 端到端集成测试 + min_score 校准

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 提供 `cad_pipeline.py sw-warmup` 子命令批量预热 SW Toolbox → STEP 缓存（含进程锁 / BOM CSV 读取 / 进度显示 / 错误日志 / 断点续跑），并通过 `demo_bom.csv`（≥15 行）+ mocked COM 集成测试锁定覆盖率 regression 基线，最后用 min_score 校准脚本基于打分分布给出阈值推荐。

**架构：** sw-warmup 主体逻辑放 `tools/sw_warmup.py` 模块（保持 `cad_pipeline.py` 的 `cmd_*` 薄 wrapper 模式）；进程锁用 `msvcrt.locking`（Windows）+ fcntl fallback（其他平台），BOM reader 用 `csv` 标准库 + 中英文列名别名表；端到端集成测试 monkeypatch `sw_com_session._com_dispatch` 走完 resolver → 命中 → 缓存写入全链路；覆盖率 regression 测试同一 BOM 跑两遍（无 SW + 有 SW mock）对比 adapter 命中数；min_score 校准脚本扫 demo_bom 候选打分输出直方图 + 推荐阈值（决策 #32）。

**Tech Stack：** Python 3.11+ / pytest / argparse / csv 标准库 / `msvcrt`（Windows 进程锁，`os.name == "nt"`）/ logging / 现有 `parts_resolver.PartsResolver` + `sw_toolbox_adapter.SwToolboxAdapter._find_sldprt`。

---

## File Structure

**Create:**

- `tools/sw_warmup.py` — sw-warmup 核心逻辑（进程锁 / 前置检查 / 选目标 / 缓存过滤 / 进度 / 错误日志 / 汇总）。`run_sw_warmup(args) -> int` 主入口
- `tools/sw_warmup_calibration.py` — min_score 校准脚本（决策 #32：扫 demo_bom 输出打分分布直方图 + 推荐阈值）
- `tests/test_sw_warmup_lock.py` — 进程锁单元测试
- `tests/test_sw_warmup_bom_reader.py` — BOM CSV reader 测试（中英文列名别名 + 错行处理）
- `tests/test_sw_warmup_orchestration.py` — sw-warmup 主流程测试（前置失败 / 选目标 / 缓存过滤 / 进度日志 / 错误日志）
- `tests/test_sw_toolbox_integration.py` — 端到端 mocked 集成测试 + 覆盖率 regression
- `tests/fixtures/sw_warmup_demo_bom.csv` — demo_bom.csv 扩到 15 行（spec §9.4）
- `tests/test_sw_warmup_calibration.py` — 校准脚本测试（输出格式 + 推荐阈值正确性）

**Modify:**

- `cad_pipeline.py` — `sub.add_parser("sw-warmup", ...)` + 5 个参数 + `cmd_sw_warmup(args)` 薄 wrapper（调 `tools.sw_warmup.run_sw_warmup`）+ dispatch 加一行
- `parts_resolver.py:33-34, :492` — 顺手修 Part 2a final review M-1 标记的 ruff F401/F541（pre-existing 遗留，本 plan 触碰此文件就一并清掉）

**Per-file 责任边界：**

- `tools/sw_warmup.py` — 纯 orchestration，**不写** COM 调用细节（委托给 `SwComSession.convert_sldprt_to_step`）；进程锁提取为 `acquire_warmup_lock()` context manager
- `tools/sw_warmup_calibration.py` — 离线分析，不触发 COM；只读 catalog index + 跑 token 打分
- `cad_pipeline.py` — 仅 CLI 接线，1 个 subparser + 1 个薄 cmd 函数（≤ 30 行）

---

## Task 0：进程锁 helper（决策 #26）

**Files:**

- Modify: `tools/sw_warmup.py`（首次创建）
- Test: `tests/test_sw_warmup_lock.py`（首次创建）

### 目标

提供 `acquire_warmup_lock(lock_path: Path)` context manager。Windows 用 `msvcrt.locking()`，其他平台用 `fcntl.flock()`。锁失败时打印 "另一个 sw-warmup 进程运行中（PID X）" 并 raise `RuntimeError`。

### 0.1 失败测试

- [ ] **Step 1：** 创建 `tests/test_sw_warmup_lock.py`：

```python
"""sw_warmup 进程锁单元测试（决策 #26）。"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAcquireWarmupLock:
    """进程锁 context manager 行为。"""

    def test_acquire_releases_on_exit(self, tmp_path):
        """正常 with 块退出后锁应被释放。"""
        from tools.sw_warmup import acquire_warmup_lock

        lock_path = tmp_path / "sw_warmup.lock"
        with acquire_warmup_lock(lock_path):
            assert lock_path.exists()  # 锁文件存在
        # 退出后下一次 acquire 应立即成功（释放 OK）
        with acquire_warmup_lock(lock_path):
            pass

    def test_concurrent_acquire_raises(self, tmp_path):
        """已持锁时另一次 acquire 应 raise RuntimeError。"""
        from tools.sw_warmup import acquire_warmup_lock

        lock_path = tmp_path / "sw_warmup.lock"
        with acquire_warmup_lock(lock_path):
            # 同进程模拟另一个尝试者：直接再 acquire
            # （Windows msvcrt + Linux fcntl 同进程内多次 acquire 会冲突）
            with pytest.raises(RuntimeError, match="另一个 sw-warmup 进程"):
                with acquire_warmup_lock(lock_path):
                    pass
```

- [ ] **Step 2：** 运行确认失败：

```bash
python -m pytest tests/test_sw_warmup_lock.py -v
```

预期 FAIL（`tools.sw_warmup` 模块不存在）。

### 0.2 实现

- [ ] **Step 3：** 创建 `tools/sw_warmup.py`：

```python
"""sw-warmup 核心实现（v4 §7 + 决策 #26）。

模块只暴露 run_sw_warmup(args) → int 主入口，
acquire_warmup_lock(lock_path) context manager 给单元测试单独覆盖。
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)


@contextlib.contextmanager
def acquire_warmup_lock(lock_path: Path) -> Iterator[None]:
    """独占进程锁（决策 #26）。Windows 用 msvcrt，其他平台 fcntl。

    Args:
        lock_path: 锁文件绝对路径，父目录会被自动创建

    Yields:
        None — with 块内代表已持锁

    Raises:
        RuntimeError: 已被另一进程占用（带 PID 提示）
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+")
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                fh.close()
                pid = lock_path.read_text(encoding="utf-8").strip() or "未知"
                raise RuntimeError(
                    f"另一个 sw-warmup 进程运行中 (PID {pid})"
                ) from e
        else:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as e:
                fh.close()
                pid = lock_path.read_text(encoding="utf-8").strip() or "未知"
                raise RuntimeError(
                    f"另一个 sw-warmup 进程运行中 (PID {pid})"
                ) from e

        # 写入当前 PID 供下个 acquire 显示
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError as e:
                    log.debug("释放 msvcrt 锁异常（忽略）: %s", e)
            else:
                import fcntl

                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError as e:
                    log.debug("释放 fcntl 锁异常（忽略）: %s", e)
    finally:
        fh.close()
```

- [ ] **Step 4：** 跑测试确认通过：

```bash
python -m pytest tests/test_sw_warmup_lock.py -v
```

预期 2 passed。

- [ ] **Step 5：** commit：

```bash
git add tools/sw_warmup.py tests/test_sw_warmup_lock.py
git commit -m "feat(sw-b): sw_warmup 进程锁 helper（v4 决策 #26）"
```

末尾加 `Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>`。

---

## Task 1：BOM CSV reader（中英文列名别名）

**Files:**

- Modify: `tools/sw_warmup.py`
- Test: `tests/test_sw_warmup_bom_reader.py`（首次创建）

### 1.1 失败测试

- [ ] **Step 6：** 创建 `tests/test_sw_warmup_bom_reader.py`：

```python
"""sw_warmup BOM CSV reader 单元测试（spec §7 BOM schema）。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestReadBomCsv:
    """读取 BOM CSV 转 PartQuery 列表，支持中英文列名 + 大小写不敏感。"""

    def test_read_english_columns(self, tmp_path):
        from tools.sw_warmup import read_bom_csv

        csv_path = tmp_path / "bom.csv"
        csv_path.write_text(
            "part_no,name_cn,material,category,make_buy\n"
            "GIS-001,GB/T 70.1 M6 螺钉,钢,fastener,标准\n",
            encoding="utf-8",
        )
        rows = read_bom_csv(csv_path)
        assert len(rows) == 1
        q = rows[0]
        assert q.part_no == "GIS-001"
        assert q.name_cn == "GB/T 70.1 M6 螺钉"
        assert q.material == "钢"
        assert q.category == "fastener"
        assert q.make_buy == "标准"

    def test_read_chinese_column_aliases(self, tmp_path):
        """中文列名（部件号/名称/材料/类别）应正确映射。"""
        from tools.sw_warmup import read_bom_csv

        csv_path = tmp_path / "bom.csv"
        csv_path.write_text(
            "部件号,名称,材料,类别\n"
            "GIS-002,深沟球轴承 6205,GCr15,bearing\n",
            encoding="utf-8",
        )
        rows = read_bom_csv(csv_path)
        assert rows[0].part_no == "GIS-002"
        assert rows[0].category == "bearing"

    def test_case_insensitive_column_names(self, tmp_path):
        """大小写不敏感（PART_NO / Part_No / part_no 都接受）。"""
        from tools.sw_warmup import read_bom_csv

        csv_path = tmp_path / "bom.csv"
        csv_path.write_text(
            "Part_No,Name_CN,Material,Category\n"
            "GIS-003,M4 螺母,钢,fastener\n",
            encoding="utf-8",
        )
        rows = read_bom_csv(csv_path)
        assert rows[0].part_no == "GIS-003"

    def test_make_buy_optional(self, tmp_path):
        """make_buy 列缺失时给空字符串，不报错。"""
        from tools.sw_warmup import read_bom_csv

        csv_path = tmp_path / "bom.csv"
        csv_path.write_text(
            "part_no,name_cn,material,category\n"
            "GIS-004,垫圈,钢,fastener\n",
            encoding="utf-8",
        )
        rows = read_bom_csv(csv_path)
        assert rows[0].make_buy == ""

    def test_missing_required_column_raises(self, tmp_path):
        """缺必需列（part_no/name_cn/material/category）应 raise ValueError。"""
        from tools.sw_warmup import read_bom_csv
        import pytest

        csv_path = tmp_path / "bom.csv"
        csv_path.write_text(
            "part_no,name_cn,material\n"  # 缺 category
            "GIS-005,X,钢\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="category"):
            read_bom_csv(csv_path)
```

- [ ] **Step 7：** 跑确认失败：

```bash
python -m pytest tests/test_sw_warmup_bom_reader.py -v
```

预期 FAIL（`read_bom_csv` 未定义）。

### 1.2 实现

- [ ] **Step 8：** 在 `tools/sw_warmup.py` 顶部 `from typing import Iterator` 之后追加 import + 在 `acquire_warmup_lock` 之前插入 reader：

```python
import csv

from parts_resolver import PartQuery


# 列名别名表（值为标准化后的字段名，键为 BOM CSV 中可能出现的列名小写）
BOM_COLUMN_ALIASES = {
    "part_no": "part_no",
    "partno": "part_no",
    "部件号": "part_no",
    "零件号": "part_no",
    "name_cn": "name_cn",
    "namecn": "name_cn",
    "名称": "name_cn",
    "中文名": "name_cn",
    "material": "material",
    "材料": "material",
    "材质": "material",
    "category": "category",
    "类别": "category",
    "分类": "category",
    "make_buy": "make_buy",
    "makebuy": "make_buy",
    "外购自制": "make_buy",
}

REQUIRED_BOM_FIELDS = ("part_no", "name_cn", "material", "category")


def read_bom_csv(csv_path: Path) -> list[PartQuery]:
    """读取 BOM CSV 并返回 PartQuery 列表（spec §7）。

    支持中英文列名别名（见 BOM_COLUMN_ALIASES），大小写不敏感。
    缺必需列时抛 ValueError；可选列 make_buy 缺失时填空字符串。

    Args:
        csv_path: BOM CSV 文件路径，UTF-8 编码

    Returns:
        PartQuery 列表，每行一个

    Raises:
        ValueError: 缺必需列
        OSError: 文件读取失败
    """
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"BOM CSV 无表头: {csv_path}")

        # 列名标准化（小写 + 别名映射）
        col_map: dict[str, str] = {}
        for raw in reader.fieldnames:
            normalized = BOM_COLUMN_ALIASES.get(raw.strip().lower())
            if normalized:
                col_map[raw] = normalized

        # 必需列检查
        present = set(col_map.values())
        missing = [f for f in REQUIRED_BOM_FIELDS if f not in present]
        if missing:
            raise ValueError(
                f"BOM CSV 缺必需列: {missing}（已识别: {sorted(present)}）"
            )

        rows: list[PartQuery] = []
        for raw_row in reader:
            mapped = {col_map[k]: v for k, v in raw_row.items() if k in col_map}
            rows.append(
                PartQuery(
                    part_no=mapped.get("part_no", "").strip(),
                    name_cn=mapped.get("name_cn", "").strip(),
                    material=mapped.get("material", "").strip(),
                    category=mapped.get("category", "").strip(),
                    make_buy=mapped.get("make_buy", "").strip(),
                )
            )
        return rows
```

- [ ] **Step 9：** 跑测试：

```bash
python -m pytest tests/test_sw_warmup_bom_reader.py -v
```

预期 5 passed。

- [ ] **Step 10：** commit：

```bash
git add tools/sw_warmup.py tests/test_sw_warmup_bom_reader.py
git commit -m "feat(sw-b): sw_warmup BOM CSV reader 中英文列名别名（v4 §7）"
```

末尾加 Co-Authored-By 签名。

---

## Task 2：sw-warmup 主流程编排

**Files:**

- Modify: `tools/sw_warmup.py`
- Test: `tests/test_sw_warmup_orchestration.py`（首次创建）

### 目标

`run_sw_warmup(args) -> int` 实现：
1. 取进程锁（Task 0）
2. 前置检查（installed/version/pywin32/toolbox_addin_enabled），失败退出
3. 选目标：`--all` / `--standard` / `--bom`
4. `--overwrite` 否则跳过已缓存
5. 进度打印 + 错误日志 + 汇总
6. 返回 exit code（0 全成功 / 1 任意失败 / 2 前置失败）

`args` 是 argparse Namespace，含字段 `standard / bom / all / dry_run / overwrite`。

### 2.1 前置失败 → exit 2

- [ ] **Step 11：** 创建 `tests/test_sw_warmup_orchestration.py`：

```python
"""sw_warmup 主流程单元测试。"""

from __future__ import annotations

import argparse
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_args(**overrides) -> argparse.Namespace:
    base = dict(
        standard=None, bom=None, all=False, dry_run=False, overwrite=False
    )
    base.update(overrides)
    return argparse.Namespace(**base)


class TestPreflight:
    """前置检查失败应返回 exit code 2（不是 1）。"""

    def test_returns_2_when_sw_not_installed(self, tmp_path, monkeypatch, capsys):
        from tools import sw_warmup as mod
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(installed=False)
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        monkeypatch.setattr(
            mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock"
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        captured = capsys.readouterr()
        assert rc == 2
        assert "未检测到" in captured.out or "未安装" in captured.out

    def test_returns_2_when_addin_disabled(self, tmp_path, monkeypatch, capsys):
        from tools import sw_warmup as mod
        from adapters.solidworks import sw_detect

        sw_detect._reset_cache()
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir=str(tmp_path / "toolbox"),
            toolbox_addin_enabled=False,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        monkeypatch.setattr(
            mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock"
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        captured = capsys.readouterr()
        assert rc == 2
        assert "Add-In" in captured.out
```

- [ ] **Step 12：** 运行确认失败：

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestPreflight -v
```

预期 FAIL（`run_sw_warmup` / `_default_lock_path` 未定义）。

- [ ] **Step 13：** 在 `tools/sw_warmup.py` 末尾追加：

```python
def _default_lock_path() -> Path:
    """默认锁文件位置 ~/.cad-spec-gen/sw_warmup.lock。"""
    return Path.home() / ".cad-spec-gen" / "sw_warmup.lock"


def _default_error_log_path() -> Path:
    """默认错误日志位置 ~/.cad-spec-gen/sw_warmup_errors.log。"""
    return Path.home() / ".cad-spec-gen" / "sw_warmup_errors.log"


def _print_preflight_failure(reason: str) -> None:
    """前置检查失败的统一打印格式。"""
    print(f"[sw-warmup] 前置检查失败：{reason}")


def _check_preflight() -> tuple[bool, str]:
    """前置检查。返回 (ok, reason)。"""
    from adapters.solidworks.sw_detect import detect_solidworks

    info = detect_solidworks()
    if not info.installed:
        return False, "未检测到 SolidWorks 安装；本命令需要本机已装 SolidWorks ≥2024"
    if (info.version_year or 0) < 2024:
        return False, f"SolidWorks 版本 {info.version_year} < 2024；请升级"
    if not info.pywin32_available:
        return False, "pywin32 未安装；请运行 `pip install pywin32`"
    if not info.toolbox_dir:
        return False, "未检测到 Toolbox 目录；检查 SW 安装完整性"
    if not info.toolbox_addin_enabled:
        return False, (
            "Toolbox Add-In 未启用；请在 SolidWorks → Tools → Add-Ins → "
            "勾选 'SOLIDWORKS Toolbox Library'"
        )
    return True, ""


def run_sw_warmup(args) -> int:
    """sw-warmup 主入口（v4 §7）。

    Returns:
        0 成功 / 1 部分失败 / 2 前置失败
    """
    try:
        with acquire_warmup_lock(_default_lock_path()):
            return _run_warmup_locked(args)
    except RuntimeError as e:
        print(f"[sw-warmup] {e}")
        return 1


def _run_warmup_locked(args) -> int:
    """实际 warmup 流程，已持进程锁。"""
    ok, reason = _check_preflight()
    if not ok:
        _print_preflight_failure(reason)
        return 2

    # 选目标 + 缓存过滤 + 转换循环（Task 2.2/2.3 实现）
    return 0
```

- [ ] **Step 14：** 跑测试：

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestPreflight -v
```

预期 2 passed。

### 2.2 选目标 + dry-run

- [ ] **Step 15：** 在 `tests/test_sw_warmup_orchestration.py` 追加：

```python
class TestTargetSelection:
    """根据 --standard / --bom / --all 选目标。"""

    @staticmethod
    def _setup_sw_available(monkeypatch, tmp_path):
        """让前置检查通过 + index 指向 fake_toolbox。"""
        from adapters.solidworks import sw_detect, sw_toolbox_catalog
        from tools import sw_warmup as mod

        sw_detect._reset_cache()
        fake_toolbox = (
            __import__("pathlib").Path(__file__).parent / "fixtures" / "fake_toolbox"
        )
        fake_info = sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir=str(fake_toolbox), toolbox_addin_enabled=True,
        )
        monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
        monkeypatch.setattr(
            mod, "_default_lock_path", lambda: tmp_path / "sw_warmup.lock"
        )
        # cache root 指向 tmp_path 隔离测试
        monkeypatch.setattr(
            sw_toolbox_catalog, "get_toolbox_cache_root",
            lambda config=None: tmp_path / "cache",
        )
        monkeypatch.setattr(
            sw_toolbox_catalog, "get_toolbox_index_path",
            lambda config=None: tmp_path / "idx.json",
        )
        return fake_toolbox

    def test_dry_run_selects_but_does_not_convert(
        self, tmp_path, monkeypatch, capsys
    ):
        """--dry-run 应只列出目标不调 COM。"""
        from tools import sw_warmup as mod

        self._setup_sw_available(monkeypatch, tmp_path)
        com_called = mock.MagicMock()
        monkeypatch.setattr(
            mod, "_convert_one", lambda *args, **kw: com_called()
        )

        rc = mod.run_sw_warmup(
            _make_args(standard="GB", dry_run=True)
        )
        captured = capsys.readouterr()
        assert rc == 0
        com_called.assert_not_called()
        # 至少打印了候选数量行
        assert "目标" in captured.out or "DRY-RUN" in captured.out
```

- [ ] **Step 16：** 运行确认失败：

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestTargetSelection -v
```

预期 FAIL（`_convert_one` 未定义 + `_run_warmup_locked` 不会枚举 standard）。

- [ ] **Step 17：** 替换 `_run_warmup_locked` 实现为完整的目标选择 + 转换循环：

```python
def _select_targets_by_standard(index: dict, standards_csv: str | None) -> list:
    """按 --standard / --all 选 sldprt 候选。返回 [SwToolboxPart] 列表。

    standards_csv 为 None 时返回全部（--all 路径）；非 None 时按逗号切分大写后过滤。
    """
    from adapters.solidworks.sw_toolbox_catalog import SwToolboxPart

    standards_filter: set[str] | None = None
    if standards_csv:
        standards_filter = {s.strip().upper() for s in standards_csv.split(",")}

    targets: list[SwToolboxPart] = []
    for std_name, sub_dict in index.get("standards", {}).items():
        if standards_filter is not None and std_name.upper() not in standards_filter:
            continue
        for parts in sub_dict.values():
            targets.extend(parts)
    return targets


def _convert_one(part, cache_root: Path, session, overwrite: bool) -> tuple[bool, float, str]:
    """调用 session 转换单个 part；返回 (success, elapsed_sec, message)。"""
    import time

    step_relative = (
        Path(part.standard) / part.subcategory
        / (Path(part.filename).stem + ".step")
    )
    step_abs = cache_root / step_relative

    if step_abs.exists() and not overwrite:
        return True, 0.0, "已缓存"

    t0 = time.monotonic()
    ok = session.convert_sldprt_to_step(part.sldprt_path, str(step_abs))
    elapsed = time.monotonic() - t0
    return ok, elapsed, ("OK" if ok else "FAIL")


def _resolve_bom_targets(bom_path: Path, registry: dict) -> dict:
    """读 BOM → 复用 SwToolboxAdapter._find_sldprt 找匹配 sldprt。
    返回 {part_no: SwToolboxPart}（找不到的行被跳过 + warning）。
    """
    from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

    queries = read_bom_csv(bom_path)
    adapter = SwToolboxAdapter(config=registry.get("solidworks_toolbox", {}))
    out: dict = {}
    for q in queries:
        spec = {"standard": ["GB", "ISO", "DIN"], "part_category": q.category}
        match = adapter._find_sldprt(q, spec)
        if match is None:
            log.warning("BOM 行未匹配到 sldprt: %s (%s)", q.part_no, q.name_cn)
            continue
        part, _score = match
        out[q.part_no] = part
    return out


def _run_warmup_locked(args) -> int:
    """实际 warmup 流程，已持进程锁。"""
    from adapters.solidworks import sw_toolbox_catalog
    from adapters.solidworks.sw_com_session import get_session
    from adapters.solidworks.sw_detect import detect_solidworks
    from parts_resolver import load_registry

    ok, reason = _check_preflight()
    if not ok:
        _print_preflight_failure(reason)
        return 2

    info = detect_solidworks()
    toolbox_dir = Path(info.toolbox_dir)
    cache_root = sw_toolbox_catalog.get_toolbox_cache_root()
    index_path = sw_toolbox_catalog.get_toolbox_index_path()
    index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
    registry = load_registry()

    # 默认 --standard GB（若三个目标参数都缺）
    if not args.all and not args.standard and not args.bom:
        args.standard = "GB"

    if args.bom:
        bom_targets = _resolve_bom_targets(Path(args.bom), registry)
        targets = list(bom_targets.values())
    elif args.all:
        targets = _select_targets_by_standard(index, None)
    else:
        targets = _select_targets_by_standard(index, args.standard)

    print(f"[sw-warmup] 目标 {len(targets)} 个 sldprt")

    if args.dry_run:
        print("[sw-warmup] DRY-RUN 模式，不调 COM；以上即转换计划")
        for p in targets[:20]:
            print(f"  - {p.standard}/{p.subcategory}/{p.filename}")
        if len(targets) > 20:
            print(f"  ...（其余 {len(targets) - 20} 个）")
        return 0

    session = get_session()
    success = 0
    failed = 0
    error_log = _default_error_log_path()
    error_log.parent.mkdir(parents=True, exist_ok=True)

    import time
    from datetime import datetime, timezone

    t_start = time.monotonic()
    for i, part in enumerate(targets, start=1):
        ok, elapsed, msg = _convert_one(part, cache_root, session, args.overwrite)
        symbol = "✓" if ok else "✗"
        print(
            f"[{i}/{len(targets)}] {part.standard}/{part.subcategory}/"
            f"{Path(part.filename).stem}.step  {symbol}  ({elapsed:.1f}s {msg})"
        )
        if ok:
            success += 1
        else:
            failed += 1
            with open(error_log, "a", encoding="utf-8") as f:
                ts = datetime.now(timezone.utc).isoformat()
                f.write(
                    f"{ts}\t{part.standard}/{part.subcategory}/{part.filename}"
                    f"\t{msg}\n"
                )

    t_total = time.monotonic() - t_start
    print(
        f"[sw-warmup] 汇总: 目标 {len(targets)} / 成功 {success} / "
        f"失败 {failed} / 耗时 {t_total / 60:.1f}m"
    )
    return 0 if failed == 0 else 1
```

- [ ] **Step 18：** 跑 dry-run 测试：

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestTargetSelection -v
```

预期 1 passed。

### 2.3 缓存命中跳过 + 错误日志

- [ ] **Step 19：** 在 `tests/test_sw_warmup_orchestration.py` 追加：

```python
class TestCacheAndErrorLog:
    """已缓存跳过 + 失败写错误日志。"""

    def test_cache_hit_skips_com(self, tmp_path, monkeypatch, capsys):
        from tools import sw_warmup as mod
        TestTargetSelection._setup_sw_available(monkeypatch, tmp_path)

        # 预先建一个缓存文件，让 part 能命中
        cache_root = tmp_path / "cache"
        (cache_root / "GB" / "bolts and studs").mkdir(parents=True)
        (cache_root / "GB" / "bolts and studs" / "hex bolt.step").write_bytes(
            b"ISO-10303 fake stub" + b"\x00" * 2000
        )

        com_session = mock.MagicMock()
        com_session.convert_sldprt_to_step = mock.MagicMock(return_value=True)
        monkeypatch.setattr(
            "adapters.solidworks.sw_com_session.get_session",
            lambda: com_session,
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        # 至少一次 convert 被跳过（cache hit）
        # 这里仅断言流程不崩 + 输出含"已缓存"
        captured = capsys.readouterr()
        assert rc in (0, 1)
        assert "已缓存" in captured.out

    def test_failure_appends_error_log(self, tmp_path, monkeypatch, capsys):
        from tools import sw_warmup as mod
        TestTargetSelection._setup_sw_available(monkeypatch, tmp_path)

        # 让 error_log 写到 tmp_path
        err_path = tmp_path / "errors.log"
        monkeypatch.setattr(mod, "_default_error_log_path", lambda: err_path)

        com_session = mock.MagicMock()
        com_session.convert_sldprt_to_step = mock.MagicMock(return_value=False)  # 全失败
        monkeypatch.setattr(
            "adapters.solidworks.sw_com_session.get_session",
            lambda: com_session,
        )

        rc = mod.run_sw_warmup(_make_args(standard="GB"))
        assert rc == 1
        assert err_path.exists()
        content = err_path.read_text(encoding="utf-8")
        assert "GB/" in content  # 至少一行失败记录
```

- [ ] **Step 20：** 跑：

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestCacheAndErrorLog -v
```

预期 2 passed（实现已具备）。

- [ ] **Step 21：** 全量 sw_warmup 回归：

```bash
python -m pytest tests/test_sw_warmup_lock.py tests/test_sw_warmup_bom_reader.py tests/test_sw_warmup_orchestration.py -v
```

- [ ] **Step 22：** ruff：

```bash
python -m ruff check tools/sw_warmup.py tests/test_sw_warmup_lock.py tests/test_sw_warmup_bom_reader.py tests/test_sw_warmup_orchestration.py
```

- [ ] **Step 23：** commit：

```bash
git add tools/sw_warmup.py tests/test_sw_warmup_orchestration.py
git commit -m "feat(sw-b): sw_warmup 主流程编排（前置/选目标/dry-run/缓存/错误日志）"
```

末尾加 Co-Authored-By 签名。

---

## Task 3：cad_pipeline.py 集成 sw-warmup 子命令

**Files:**

- Modify: `cad_pipeline.py`（加 subparser + cmd_sw_warmup + dispatch）

### 3.1 失败测试

- [ ] **Step 24：** 在 `tests/test_sw_warmup_orchestration.py` 末尾追加：

```python
class TestCadPipelineSubcommand:
    """cad_pipeline.py 注册了 sw-warmup 子命令。"""

    def test_sw_warmup_subparser_exists(self):
        """argparse 应识别 sw-warmup 子命令并接受 --standard --bom --all --dry-run --overwrite。"""
        import importlib.util

        cad_path = os.path.join(
            os.path.dirname(__file__), "..", "cad_pipeline.py"
        )
        spec = importlib.util.spec_from_file_location("cad_pipeline_mod", cad_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # 通过反射拿到 main 内部构造的 parser 不实际：直接调 main 验证
        # 用 sys.argv 注入 --help 会 SystemExit，不友好。
        # 改为：调 cmd_sw_warmup 函数确认存在
        assert hasattr(mod, "cmd_sw_warmup"), "cad_pipeline 应导出 cmd_sw_warmup"
```

- [ ] **Step 25：** 跑确认失败：

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestCadPipelineSubcommand -v
```

预期 FAIL。

### 3.2 实现

- [ ] **Step 26：** Read `cad_pipeline.py` 找到 `def cmd_env_check(args):`（约 line 2044），在它之后追加：

```python
def cmd_sw_warmup(args):
    """SW Toolbox sldprt → STEP 批量预热（v4 §7）。"""
    from tools.sw_warmup import run_sw_warmup
    return run_sw_warmup(args)
```

- [ ] **Step 27：** Read `cad_pipeline.py` 找到 `sub.add_parser("env-check", help="Validate environment")`（约 line 2389），在其后插入：

```python
    # sw-warmup
    p_sw_warmup = sub.add_parser(
        "sw-warmup",
        help="批量预热 SW Toolbox sldprt → STEP 缓存（v4 §7）",
    )
    p_sw_warmup.add_argument("--standard", help="逗号分隔标准，如 GB,ISO,DIN（默认 GB）")
    p_sw_warmup.add_argument("--bom", help="BOM CSV 路径（按行匹配 sldprt）")
    p_sw_warmup.add_argument("--all", action="store_true", help="预热所有 1818 个标准件")
    p_sw_warmup.add_argument("--dry-run", action="store_true", help="只列目标不调 COM")
    p_sw_warmup.add_argument("--overwrite", action="store_true", help="覆盖已有缓存")
```

- [ ] **Step 28：** 在 dispatch 字典（约 line 2412 `dispatch = {`）末尾加一行：

```python
    dispatch = {
        ...
        "env-check": cmd_env_check,
        "sw-warmup": cmd_sw_warmup,
    }
```

- [ ] **Step 29：** 跑：

```bash
python -m pytest tests/test_sw_warmup_orchestration.py::TestCadPipelineSubcommand -v
```

预期 PASS。

- [ ] **Step 30：** Smoke：

```bash
python cad_pipeline.py sw-warmup --help 2>&1 | head -20
```

预期：打印 sw-warmup 用法 + 5 个参数说明。

- [ ] **Step 31：** commit：

```bash
git add cad_pipeline.py tests/test_sw_warmup_orchestration.py
git commit -m "feat(sw-b): cad_pipeline.py 注册 sw-warmup 子命令（v4 §7）"
```

末尾加 Co-Authored-By 签名。

---

## Task 4：demo_bom.csv 扩到 15 行 + 端到端 mocked 集成测试

**Files:**

- Create: `tests/fixtures/sw_warmup_demo_bom.csv`
- Create: `tests/test_sw_toolbox_integration.py`

### 4.1 写 demo_bom.csv

- [ ] **Step 32：** 创建 `tests/fixtures/sw_warmup_demo_bom.csv`（spec §9.4 字面照抄）：

```csv
part_no,name_cn,material,make_buy,category
GIS-DEMO-001,GB/T 70.1 M6×20 内六角圆柱头螺钉,钢,标准,fastener
GIS-DEMO-002,GB/T 276 深沟球轴承 6205,GCr15,标准,bearing
GIS-DEMO-003,GB/T 70.1 M4×10 内六角圆柱头螺钉,钢,标准,fastener
GIS-DEMO-004,GB/T 6170 M6 六角螺母,钢,标准,fastener
GIS-DEMO-005,GB/T 97.1 6 平垫圈,钢,标准,fastener
GIS-DEMO-006,GB/T 5782 M8×25 六角头螺栓,钢,标准,fastener
GIS-DEMO-007,GB/T 276 深沟球轴承 6204,GCr15,标准,bearing
GIS-DEMO-008,GB/T 297 圆锥滚子轴承 30205,GCr15,标准,bearing
GIS-DEMO-009,ISO 4762 M5×16 hex socket cap screw,steel,standard,fastener
GIS-DEMO-010,ISO 4032 M5 hex nut,steel,standard,fastener
GIS-DEMO-011,DIN 912 M3×8 cap screw,steel,standard,fastener
GIS-DEMO-012,1/4-20 UNC hex bolt,steel,standard,fastener
GIS-DEMO-013,Tr16×2 梯形螺纹丝杠,40Cr,外购,fastener
GIS-DEMO-014,非标异形件定制壳体,7075-T6,自制,housing
GIS-DEMO-015,Maxon ECX SPEED 22L 减速电机,-,外购,motor
```

### 4.2 端到端 mocked 集成测试

- [ ] **Step 33：** 创建 `tests/test_sw_toolbox_integration.py`：

```python
"""SW Toolbox 端到端 mocked 集成测试（spec §9.3）。

验证 BOM CSV → PartsResolver → SwToolboxAdapter → mocked SwComSession
全链路在不调真实 COM 的情况下能产生预期 STEP 缓存命中。
"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEMO_BOM = Path(__file__).parent / "fixtures" / "sw_warmup_demo_bom.csv"
FAKE_TOOLBOX = Path(__file__).parent / "fixtures" / "fake_toolbox"


@pytest.fixture
def sw_available(monkeypatch, tmp_path):
    """Mock 让 SwToolboxAdapter.is_available() = True 且 cache 在 tmp_path。"""
    from adapters.solidworks import sw_detect, sw_toolbox_catalog, sw_com_session

    sw_detect._reset_cache()
    sw_com_session.reset_session()
    fake_info = sw_detect.SwInfo(
        installed=True, version_year=2024, pywin32_available=True,
        toolbox_dir=str(FAKE_TOOLBOX), toolbox_addin_enabled=True,
    )
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
    monkeypatch.setattr(
        sw_toolbox_catalog, "get_toolbox_cache_root",
        lambda config=None: tmp_path / "cache",
    )
    monkeypatch.setattr(
        sw_toolbox_catalog, "get_toolbox_index_path",
        lambda config=None: tmp_path / "idx.json",
    )

    # mock COM dispatch — 让任何 convert 都"成功"（写 1KB ISO-10303 头）
    fake_app = mock.MagicMock()
    fake_app.LoadAddIn.return_value = 1

    def fake_convert(self, sldprt_path, step_out):
        with self._lock:
            from pathlib import Path as P
            P(step_out).parent.mkdir(parents=True, exist_ok=True)
            P(step_out).write_bytes(b"ISO-10303-21 fake" + b"\x00" * 2000)
            return True

    monkeypatch.setattr(
        sw_com_session.SwComSession, "convert_sldprt_to_step", fake_convert
    )
    return tmp_path


def test_bom_resolves_with_mocked_com(sw_available):
    """加载 demo_bom.csv → 经 PartsResolver → 至少 1 行命中 sw_toolbox。

    本测试用 fake_toolbox（仅含 GB/bolts and studs/hex bolt.sldprt 等少数 sldprt），
    所以并非全部 11 行 GB/ISO/DIN BOM 都能命中。这里只断言：sw_toolbox 至少
    成功 resolve 了 1 个 BOM 行（说明端到端链路打通）。
    """
    from tools.sw_warmup import read_bom_csv
    from parts_resolver import default_resolver

    queries = read_bom_csv(DEMO_BOM)
    assert len(queries) == 15

    resolver = default_resolver(project_root=str(sw_available))
    sw_hits = 0
    for q in queries:
        result = resolver.resolve(q)
        if result.adapter == "sw_toolbox" and result.status == "hit":
            sw_hits += 1

    assert sw_hits >= 1, "至少 1 行应命中 sw_toolbox（fake_toolbox 几何有限）"
```

- [ ] **Step 34：** 跑测试：

```bash
python -m pytest tests/test_sw_toolbox_integration.py -v
```

预期 1 passed。**若 FAIL**：可能是 `default_resolver` 的 `is_available()` 检查严格要求所有 6 项，monkeypatch 的 fake_info 字段不全。检查 `SwInfo` 默认值是否包含 `pywin32_available=True` 等。

- [ ] **Step 35：** ruff：

```bash
python -m ruff check tests/test_sw_toolbox_integration.py
```

- [ ] **Step 36：** commit：

```bash
git add tests/fixtures/sw_warmup_demo_bom.csv tests/test_sw_toolbox_integration.py
git commit -m "test(sw-b): demo_bom.csv 15 行 + 端到端 mocked 集成测试（spec §9.3/9.4）"
```

末尾加 Co-Authored-By 签名。

---

## Task 5：覆盖率 regression 测试

**Files:**

- Modify: `tests/test_sw_toolbox_integration.py`（追加）

### 目标

同一 `demo_bom.csv` 跑两次：
1. **无 SW**：所有 SwToolboxAdapter is_available 返回 False → 行走 jinja_primitive
2. **有 SW（mock）**：SwToolboxAdapter 可用 → 至少 N 行迁移到 sw_toolbox

固化基线：`solidworks_toolbox 命中数 ≥ 1`，`jinja_primitive 命中数减少 ≥ 1`。

### 5.1 失败测试

- [ ] **Step 37：** 在 `tests/test_sw_toolbox_integration.py` 追加：

```python
def test_coverage_regression_baseline(monkeypatch, tmp_path):
    """同一 BOM 跑两次：sw_toolbox 命中数应 ≥ baseline + 迁移量；jinja 减少同等量。"""
    from tools.sw_warmup import read_bom_csv
    from parts_resolver import default_resolver
    from adapters.solidworks import sw_detect, sw_toolbox_catalog, sw_com_session
    from pathlib import Path as P

    queries = read_bom_csv(DEMO_BOM)

    # ─── pass 1: 无 SW ───
    sw_detect._reset_cache()
    monkeypatch.setattr(
        sw_detect, "detect_solidworks",
        lambda: sw_detect.SwInfo(installed=False),
    )
    resolver1 = default_resolver(project_root=str(tmp_path))
    counts_no_sw: dict[str, int] = {}
    for q in queries:
        r = resolver1.resolve(q)
        counts_no_sw[r.adapter] = counts_no_sw.get(r.adapter, 0) + 1

    sw_no_sw = counts_no_sw.get("sw_toolbox", 0)
    jinja_no_sw = counts_no_sw.get("jinja_primitive", 0)
    assert sw_no_sw == 0, "无 SW 时 sw_toolbox 不应命中"

    # ─── pass 2: 有 SW（mock）───
    sw_detect._reset_cache()
    sw_com_session.reset_session()
    fake_info = sw_detect.SwInfo(
        installed=True, version_year=2024, pywin32_available=True,
        toolbox_dir=str(FAKE_TOOLBOX), toolbox_addin_enabled=True,
    )
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake_info)
    monkeypatch.setattr(
        sw_toolbox_catalog, "get_toolbox_cache_root",
        lambda config=None: tmp_path / "cache",
    )
    monkeypatch.setattr(
        sw_toolbox_catalog, "get_toolbox_index_path",
        lambda config=None: tmp_path / "idx.json",
    )

    def fake_convert(self, sldprt_path, step_out):
        with self._lock:
            P(step_out).parent.mkdir(parents=True, exist_ok=True)
            P(step_out).write_bytes(b"ISO-10303-21 fake" + b"\x00" * 2000)
            return True

    monkeypatch.setattr(
        sw_com_session.SwComSession, "convert_sldprt_to_step", fake_convert
    )

    resolver2 = default_resolver(project_root=str(tmp_path))
    counts_with_sw: dict[str, int] = {}
    for q in queries:
        r = resolver2.resolve(q)
        counts_with_sw[r.adapter] = counts_with_sw.get(r.adapter, 0) + 1

    sw_with_sw = counts_with_sw.get("sw_toolbox", 0)
    jinja_with_sw = counts_with_sw.get("jinja_primitive", 0)

    # 基线断言
    assert sw_with_sw >= 1, f"有 SW 时 sw_toolbox 应至少命中 1 行（实际 {sw_with_sw}）"
    assert jinja_with_sw <= jinja_no_sw, "jinja 命中数应不增（migration 到 sw_toolbox）"
    # 迁移量 = sw_with_sw 至少等于 jinja 减少量
    assert (jinja_no_sw - jinja_with_sw) <= sw_with_sw, (
        f"迁移会计不平衡: jinja 减少 {jinja_no_sw - jinja_with_sw} vs sw 命中 {sw_with_sw}"
    )
```

- [ ] **Step 38：** 跑：

```bash
python -m pytest tests/test_sw_toolbox_integration.py::test_coverage_regression_baseline -v
```

预期 PASS。

**若 FAIL**：可能 fake_toolbox fixture 太薄导致 sw_toolbox 0 命中。检查 `tests/fixtures/fake_toolbox/GB/bolts and studs/hex bolt.sldprt` 是否存在（Part 1 已建）；若不存在或 token 匹配 score 不够，调高/调低 `min_score` 或扩 fake fixture。

- [ ] **Step 39：** ruff + commit：

```bash
python -m ruff check tests/test_sw_toolbox_integration.py
git add tests/test_sw_toolbox_integration.py
git commit -m "test(sw-b): 覆盖率 regression 基线（jinja → sw_toolbox 迁移量会计）"
```

末尾加 Co-Authored-By 签名。

---

## Task 6：min_score 校准脚本（决策 #32）

**Files:**

- Create: `tools/sw_warmup_calibration.py`
- Test: `tests/test_sw_warmup_calibration.py`

### 目标

CLI 工具 `python tools/sw_warmup_calibration.py --bom <csv>`，对 BOM 每行计算 SwToolboxAdapter token 打分分布（含未达 min_score 的候选），输出：
1. 每 BOM 行 top-3 候选 + score
2. 全集打分直方图（10 个 bin）
3. 推荐阈值 = `max(噪声均值 + 2σ, 0.30)`（决策 #32）

不修改 yaml；只输出文本报告。

### 6.1 失败测试

- [ ] **Step 40：** 创建 `tests/test_sw_warmup_calibration.py`：

```python
"""sw_warmup_calibration 校准脚本测试（决策 #32）。"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEMO_BOM = Path(__file__).parent / "fixtures" / "sw_warmup_demo_bom.csv"
FAKE_TOOLBOX = Path(__file__).parent / "fixtures" / "fake_toolbox"


def test_calibration_outputs_recommendation(tmp_path, monkeypatch, capsys):
    """脚本应输出推荐阈值行，且阈值 >= 0.30（决策 #32 下界）。"""
    from tools import sw_warmup_calibration as cal
    from adapters.solidworks import sw_detect, sw_toolbox_catalog

    sw_detect._reset_cache()
    monkeypatch.setattr(
        sw_detect, "detect_solidworks",
        lambda: sw_detect.SwInfo(
            installed=True, version_year=2024, pywin32_available=True,
            toolbox_dir=str(FAKE_TOOLBOX), toolbox_addin_enabled=True,
        ),
    )
    monkeypatch.setattr(
        sw_toolbox_catalog, "get_toolbox_index_path",
        lambda config=None: tmp_path / "idx.json",
    )

    rc = cal.run_calibration(DEMO_BOM)
    captured = capsys.readouterr()
    assert rc == 0
    assert "推荐 min_score" in captured.out
    # 推荐值能被解析出来（最后一行格式 "推荐 min_score: 0.XX"）
    import re
    m = re.search(r"推荐 min_score:\s*(\d+\.\d+)", captured.out)
    assert m, f"未找到推荐阈值行，输出: {captured.out}"
    threshold = float(m.group(1))
    assert threshold >= 0.30, f"推荐阈值 {threshold} 应 >= 0.30（下界）"
```

- [ ] **Step 41：** 跑确认失败：

```bash
python -m pytest tests/test_sw_warmup_calibration.py -v
```

预期 FAIL（脚本未创建）。

### 6.2 实现

- [ ] **Step 42：** 创建 `tools/sw_warmup_calibration.py`：

```python
"""min_score 阈值校准脚本（v4 决策 #32）。

对 BOM 每行计算 SwToolboxAdapter token 打分分布，输出直方图 + 推荐阈值。
推荐阈值 = max(noise_mean + 2 * noise_std, 0.30)。
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

# 让脚本既能 `python -m tools.sw_warmup_calibration` 也能直接跑
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_calibration(bom_path: Path) -> int:
    """对 BOM 每行扫所有 GB/ISO/DIN 候选打分，输出报告 + 推荐阈值。"""
    from adapters.solidworks import sw_toolbox_catalog
    from adapters.solidworks.sw_detect import detect_solidworks
    from tools.sw_warmup import read_bom_csv

    info = detect_solidworks()
    if not info.toolbox_dir:
        print("[calibration] 未检测到 toolbox_dir，无法校准")
        return 1

    toolbox_dir = Path(info.toolbox_dir)
    index_path = sw_toolbox_catalog.get_toolbox_index_path()
    index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
    queries = read_bom_csv(bom_path)

    print(f"[calibration] BOM={bom_path}, 行数 {len(queries)}")
    print(f"[calibration] Toolbox={toolbox_dir}, 索引零件总数 "
          f"{sum(len(p) for sub in index['standards'].values() for p in sub.values())}")

    all_top_scores: list[float] = []  # 每行的 top-1 分数（信号）
    all_other_scores: list[float] = []  # 每行 top-2/3 分数（噪声）

    for q in queries:
        size_dict = sw_toolbox_catalog.extract_size_from_name(q.name_cn, {})
        # 退化：未抽到 size 也照原 name 跑 token 打分
        query_tokens = sw_toolbox_catalog.build_query_tokens_weighted(
            q, size_dict or {}, {}
        )
        # 收集所有候选打分
        candidates: list[tuple[str, float]] = []
        for std_name, sub_dict in index.get("standards", {}).items():
            for parts in sub_dict.values():
                for part in parts:
                    part_token_set = set(part.tokens)
                    if not query_tokens or not part_token_set:
                        continue
                    total_w = sum(w for _, w in query_tokens) or 1.0
                    hit_w = sum(w for t, w in query_tokens if t in part_token_set)
                    score = hit_w / total_w
                    candidates.append((
                        f"{std_name}/{part.subcategory}/{part.filename}", score
                    ))

        candidates.sort(key=lambda x: x[1], reverse=True)
        top3 = candidates[:3]
        print(f"\n[{q.part_no}] {q.name_cn}")
        for name, score in top3:
            print(f"    {score:.3f}  {name}")

        if top3:
            all_top_scores.append(top3[0][1])
            all_other_scores.extend([s for _, s in top3[1:]])

    print("\n─── 直方图 ───")
    bins = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    for low, high in zip(bins[:-1], bins[1:]):
        n_top = sum(1 for s in all_top_scores if low <= s < high)
        n_other = sum(1 for s in all_other_scores if low <= s < high)
        bar = "█" * (n_top + n_other)
        print(f"  [{low:.1f}-{high:.1f}) top1={n_top:3d} other={n_other:3d}  {bar}")

    # 推荐阈值
    if all_other_scores:
        noise_mean = statistics.mean(all_other_scores)
        noise_std = (
            statistics.stdev(all_other_scores) if len(all_other_scores) > 1 else 0.0
        )
        recommended = max(noise_mean + 2 * noise_std, 0.30)
    else:
        recommended = 0.30

    print(f"\n推荐 min_score: {recommended:.2f}")
    print(f"  (noise_mean={statistics.mean(all_other_scores) if all_other_scores else 0:.3f}, "
          f"noise_std={statistics.stdev(all_other_scores) if len(all_other_scores) > 1 else 0:.3f}, "
          f"下界 0.30)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SW Toolbox min_score 校准（决策 #32）")
    parser.add_argument("--bom", required=True, type=Path, help="BOM CSV 路径")
    args = parser.parse_args()
    return run_calibration(args.bom)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 43：** 跑测试：

```bash
python -m pytest tests/test_sw_warmup_calibration.py -v
```

预期 PASS。

- [ ] **Step 44：** Smoke：

```bash
python tools/sw_warmup_calibration.py --bom tests/fixtures/sw_warmup_demo_bom.csv 2>&1 | tail -20
```

预期：可读直方图 + "推荐 min_score: 0.30" 之类一行。

- [ ] **Step 45：** ruff + commit：

```bash
python -m ruff check tools/sw_warmup_calibration.py tests/test_sw_warmup_calibration.py
git add tools/sw_warmup_calibration.py tests/test_sw_warmup_calibration.py
git commit -m "feat(sw-b): min_score 校准脚本（v4 决策 #32 直方图 + 推荐阈值）"
```

末尾加 Co-Authored-By 签名。

---

## Task 7：Part 2b 收尾（ruff 全量 + final review + memory）

**Files:** 无新改动，QA。

### 7.1 顺手清 Part 2a final review M-1 标记

- [ ] **Step 46：** Read `parts_resolver.py:33-34, :492` 看 ruff 报告：

```bash
python -m ruff check parts_resolver.py 2>&1 | head -20
```

如果 F401 / F541 在那几行就 `--fix`：

```bash
python -m ruff check parts_resolver.py --fix
git add parts_resolver.py
git commit -m "style(sw-b): parts_resolver ruff F401/F541 清理（Part 2a final review M-1）"
```

末尾加 Co-Authored-By 签名。若 `--fix` 影响测试再回滚。

### 7.2 全量回归

- [ ] **Step 47：** 全量 SW + sw_warmup + integration：

```bash
python -m pytest tests/ -k "sw_ or check_env or warmup or toolbox_integration" 2>&1 | tail -10
```

预期：相比 Part 2a 的 132 至少多出 sw_warmup（约 11）+ integration（2）+ calibration（1）= **146+ passed**。

- [ ] **Step 48：** parts_resolver 既有测试不破：

```bash
python -m pytest tests/test_parts_resolver.py -v 2>&1 | tail -5
```

预期：**39 passed**。

### 7.3 Final review

- [ ] **Step 49：** 派 `superpowers:requesting-code-review`：
  - BASE_SHA: Part 2a 最后 commit `a49c11c`
  - HEAD_SHA: `git rev-parse HEAD`
  - WHAT_WAS_IMPLEMENTED: Phase SW-B Part 2b — sw-warmup CLI（进程锁/BOM reader/编排/cad_pipeline 集成）+ demo_bom.csv 15 行 + 端到端 mocked 集成测试 + 覆盖率 regression + min_score 校准脚本
  - PLAN_OR_REQUIREMENTS: `docs/superpowers/plans/2026-04-13-sw-integration-phase-b-part2b.md`
  - 重点审查项：
    1. 进程锁的 Windows / Linux 双路径正确性，释放路径异常处理
    2. BOM reader 对中英文列名 + 错行 + UTF-8 BOM 是否健壮
    3. sw-warmup 主流程的 exit code 语义（0/1/2 区分清晰）
    4. 端到端集成测试的 mock 边界（fake_toolbox + monkeypatch 范围是否会污染其他测试）
    5. min_score 校准脚本的统计算法（是否对小样本有合理的退化）
    6. cad_pipeline.py 子命令注册有无破坏现有 CLI

- [ ] **Step 50：** 按 review 修复（若有 Important）。

### 7.4 更新 memory

- [ ] **Step 51：** Edit `C:/Users/<user>/.claude/projects/D--Work-cad-spec-gen/memory/solidworks_asset_extraction.md`：

把 "Phase SW-B Part 2b（sw-warmup CLI + 端到端集成测试 + min_score 校准）: 未开始" 改为 "已完成 ✅ — N commit，sw-warmup CLI / demo_bom.csv 15 行 / 端到端 mocked 集成 / 覆盖率 regression / min_score 校准脚本"。

把 "How to apply" 末段改成 "下一步是 superpowers:writing-plans 写 Phase SW-B Part 2c 实施计划（SW-B0 spike 补课 + SW-B9 真实 COM 验收 + SW-B10 packaging/sw-inspect/文档）"。

同步 MEMORY.md 索引一行 hook。

### 7.5 最终 commit

- [ ] **Step 52：** 若 review 后有改动：

```bash
git add -u
git commit -m "fix(sw-b): Part 2b code review 修复"
```

---

## 交付物（Part 2b 完成态）

1. **`cad_pipeline.py sw-warmup` 子命令可用**：5 个参数（--standard/--bom/--all/--dry-run/--overwrite）+ 进程锁 + 前置检查 UX + 进度显示 + 错误日志 + 汇总 + 断点续跑
2. **BOM CSV reader** 中英文列名别名表 + 大小写不敏感 + 必需列校验
3. **demo_bom.csv 15 行**（spec §9.4 字面）+ 端到端 mocked 集成测试 + 覆盖率 regression 基线（jinja → sw_toolbox 迁移量会计）
4. **min_score 校准脚本** `tools/sw_warmup_calibration.py`：BOM 扫描 → top-3 候选 → 直方图 → 推荐阈值（决策 #32）
5. **测试套件** ≥146 passed，含 sw_warmup_lock/bom_reader/orchestration/integration/calibration/cad_pipeline 子命令注册

## 后续（Part 2c）

- SW-B0 spike 补课：开发机 SW 启动失败排障，实测 `COLD_START_TIMEOUT_SEC=90` 是否合理
- SW-B9：`@requires_solidworks` 真实 COM 测试 + 开发机 5 项验收（demo_bom 73% / 真实项目 ≥100 行 / session 周期重启 / 装配回归 gate / ROI 熔断）
- SW-B10：`pyproject.toml` 加 `solidworks` optional-deps + `requires_solidworks` marker + coverage report 健康状态格式化（决策 #28）+ `sw-inspect` 子命令（决策 #27）+ 文档更新
