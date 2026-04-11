"""v2.9.2 Item 4 Path B — src/cad_spec_gen/data/ mirror drift 安全网。

`hatch_build.py::CustomBuildHook.initialize()` 会在 wheel build 时把 root 级
的源文件（`cad_pipeline.py` 等）、子目录（`codegen/` / `config/` / `templates/`）
以及 `.claude/commands/*.md`、`skill_*.md`、`system_prompt.md`、
`parts_library.default.yaml` 复制到 `src/cad_spec_gen/data/`，作为 wheel 打包
的资源载荷。

这些打包副本是 git-tracked 的构建产物 —— 两套位置、两个真相源，是个明知
风险的过渡态。历史证据：v2.9.0 期间 root 的 `cad_pipeline.py` 更新了好几次
都没同步到 data/ mirror，直到 v2.9.1 走 real-doc 端到端测试才被发现。

本测试是 **v2.9.2 的即时止血**：每次 CI 都会比对 root 与 data/ 的字节一致
性，若 drift 检测到，测试 fail 并给出 `cp ... && git add ...` 修复命令。
**v2.10 的正式方案**是把 `data/python_tools/**` 和 `data/codegen/**` 加进
gitignore + `pip install -e .` 时触发 build hook 生成，从结构上消除这份
双副本（见 RELEASE_v2.9.2.md "Item 4 长期计划"）。

实现要点：
- 用 `ast.parse()` 解析 `hatch_build.py`，从中动态提取 `_PIPELINE_TOOLS`、
  `COPY_DIRS`、`TOP_LEVEL_FILES` 三个常量 —— 不 import hatch_build（那会
  触发 `from hatchling ...` 的 ImportError），只读源码
- `SHARED_TOOL_FILES` 的 fallback 列表在 hatch_build 里是硬编码（因为
  `cad_paths.SHARED_TOOL_FILES` 不存在，try/except 的 ImportError 分支始终
  命中），本测试同步使用该硬编码列表
- 每个同步对参数化为独立 case，pytest 报错时精确定位问题文件
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_DATA_DIR = _REPO_ROOT / "src" / "cad_spec_gen" / "data"

# 与 hatch_build.py::_SHARED fallback 保持一致。该列表来自
# cad_paths.SHARED_TOOL_FILES（理论上），但该常量实际不存在于 cad_paths.py，
# 所以 hatch_build 始终走 except 分支用硬编码。本测试复制同一份硬编码。
_HATCH_SHARED_FALLBACK = [
    "drawing.py",
    "draw_three_view.py",
    "cq_to_dxf.py",
    "render_dxf.py",
    "render_config.py",
    "cad_spec_defaults.py",
]


def _hash_file(path: Path) -> str:
    """MD5 of a file's bytes; used only for drift detection, not security."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def _parse_hatch_build_constants():
    """Extract `_PIPELINE_TOOLS`, `COPY_DIRS`, `TOP_LEVEL_FILES` from hatch_build.py.

    Uses `ast` so we don't need to import hatch_build (which would require
    hatchling installed in the test environment).
    """
    hatch_src = (_REPO_ROOT / "hatch_build.py").read_text(encoding="utf-8")
    tree = ast.parse(hatch_src)

    pipeline_tools: list[str] = []
    copy_dirs: dict[str, str] = {}
    top_level_files: dict[str, str] = {}

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue

        if target.id == "_PIPELINE_TOOLS" and isinstance(node.value, ast.List):
            pipeline_tools = [
                el.value for el in node.value.elts if isinstance(el, ast.Constant)
            ]
        elif target.id == "COPY_DIRS" and isinstance(node.value, ast.Dict):
            copy_dirs = {
                k.value: v.value
                for k, v in zip(node.value.keys, node.value.values)
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
            }
        elif target.id == "TOP_LEVEL_FILES" and isinstance(node.value, ast.Dict):
            top_level_files = {
                k.value: v.value
                for k, v in zip(node.value.keys, node.value.values)
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
            }

    return pipeline_tools, copy_dirs, top_level_files


def _collect_sync_pairs():
    """Build the authoritative list of (category, name, root, data) sync pairs.

    Covers 3 of the 6 hatch_build copy categories:
      1. Flat python_tools/ (PYTHON_TOOLS = _PIPELINE_TOOLS + _SHARED)
      2. Recursive COPY_DIRS (codegen/, config/, templates/)
      3. TOP_LEVEL_FILES (parts_library.default.yaml)

    Skipped for now (low drift risk, can be added if needed):
      - `.claude/commands/*.md` → data/commands/zh/
      - `skill_cad_help.md` / `skill_mech_design.md` → data/knowledge/*_zh.md
      - `system_prompt.md` → data/system_prompt.md
    """
    pipeline_tools, copy_dirs, top_level_files = _parse_hatch_build_constants()
    all_python_tools = pipeline_tools + _HATCH_SHARED_FALLBACK

    pairs: list[tuple[str, str, Path, Path]] = []

    # 1. Flat python_tools/
    for fname in all_python_tools:
        src = _REPO_ROOT / fname
        dst = _DATA_DIR / "python_tools" / fname
        pairs.append(("python_tools", fname, src, dst))

    # 2. Recursive COPY_DIRS
    for src_name, dst_name in copy_dirs.items():
        src_dir = _REPO_ROOT / src_name
        dst_dir = _DATA_DIR / dst_name
        if not src_dir.is_dir():
            continue
        for src_file in sorted(src_dir.rglob("*")):
            if not src_file.is_file():
                continue
            if "__pycache__" in src_file.parts:
                continue
            if src_file.suffix in (".pyc",):
                continue
            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel
            pairs.append((f"dir:{src_name}", rel.as_posix(), src_file, dst_file))

    # 3. TOP_LEVEL_FILES
    for src_name, dst_rel in top_level_files.items():
        src = _REPO_ROOT / src_name
        dst = _DATA_DIR / dst_rel
        pairs.append(("top_level", src_name, src, dst))

    return pairs


# 模块导入时就构造参数化数据，让 pytest collect 阶段就能显示全量 case 列表
_SYNC_PAIRS = _collect_sync_pairs()
_SYNC_IDS = [f"{cat}/{name}" for cat, name, _, _ in _SYNC_PAIRS]


@pytest.mark.parametrize(
    ("category", "name", "src", "dst"),
    _SYNC_PAIRS,
    ids=_SYNC_IDS,
)
def test_data_dir_mirror_matches_root(category, name, src, dst):
    """Path B drift 检测：每一个 hatch_build 会同步的文件都必须字节一致。

    若本测试 fail，说明 root 源文件更新了但 `src/cad_spec_gen/data/` 下
    的打包副本没跟着更新。修复方式见 assert message 中的 cp 命令。
    """
    if not src.exists():
        # Root source absent — 可能是新环境刚 clone 还没生成某些文件，跳过
        pytest.skip(f"Root source {src.relative_to(_REPO_ROOT)} does not exist")

    assert dst.exists(), (
        f"\nPackaged mirror MISSING: {dst.relative_to(_REPO_ROOT)}\n"
        f"Fix: cp '{src}' '{dst}' && git add '{dst}'\n"
        f"(category={category})"
    )

    src_hash = _hash_file(src)
    dst_hash = _hash_file(dst)
    assert src_hash == dst_hash, (
        f"\nMirror DRIFT detected: {dst.relative_to(_REPO_ROOT)}\n"
        f"  root ({src.relative_to(_REPO_ROOT)}) md5={src_hash}\n"
        f"  data ({dst.relative_to(_REPO_ROOT)}) md5={dst_hash}\n"
        f"Fix: cp '{src}' '{dst}' && git add '{dst}'\n"
        f"(category={category})"
    )


def test_python_tools_has_no_stray_files():
    """data/python_tools/ 不应存在 _PIPELINE_TOOLS + _SHARED 列表外的 .py 文件。

    Stray 文件意味着开发者在 root 加了新脚本但忘了注册到
    `hatch_build._PIPELINE_TOOLS` 就手动复制到了 data/，导致 wheel 打包路径
    和 test 可见性不同步。本测试是反向哨兵。
    """
    pipeline_tools, _, _ = _parse_hatch_build_constants()
    known = set(pipeline_tools) | set(_HATCH_SHARED_FALLBACK)

    actual_py = {
        f.name
        for f in (_DATA_DIR / "python_tools").glob("*.py")
        if f.name != "__init__.py"
    }

    stray = actual_py - known
    assert not stray, (
        f"\ndata/python_tools/ 含未注册的 .py 文件: {sorted(stray)}\n"
        f"Fix 之一：\n"
        f"  (a) 把它们加进 hatch_build._PIPELINE_TOOLS\n"
        f"  (b) 或者从 data/python_tools/ 删除（若是误提交的本地文件）"
    )


def test_sync_pair_count_is_nontrivial():
    """健康检查：_SYNC_PAIRS 不应为空或异常小，否则说明 ast 解析失败、
    hatch_build.py 被重构、或 cwd 搞错了。"""
    assert len(_SYNC_PAIRS) >= 20, (
        f"Only {len(_SYNC_PAIRS)} sync pairs discovered — "
        f"expected ≥20 (PYTHON_TOOLS has ~20, codegen has 5, templates has many). "
        f"Check _parse_hatch_build_constants() and hatch_build.py layout."
    )
