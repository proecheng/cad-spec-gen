"""v2.10 — dev_sync.py 正确性验证。

v2.9.2 的 test_data_dir_sync.py 检测 git-tracked mirror 文件的 drift。
v2.10 把 mirror 文件从 git tracking 移除（.gitignore），改由
scripts/dev_sync.py 同步。本测试验证 dev_sync.py 的同步结果：
跑一次 sync() 后，data/ 下的文件应与 root 字节一致。

实现要点：
- session-scope fixture 跑一次 sync()，所有参数化 case 共享结果
- 参数化逻辑沿用 ast.parse() 从 hatch_build.py 派生同步对
- MD5 一致性断言保持不变
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_DATA_DIR = _REPO_ROOT / "src" / "cad_spec_gen" / "data"

# 与 hatch_build.py / dev_sync.py 的 fallback 保持一致
_HATCH_SHARED_FALLBACK = [
    "drawing.py",
    "draw_three_view.py",
    "cq_to_dxf.py",
    "render_dxf.py",
    "render_config.py",
    "cad_spec_defaults.py",
]


def _hash_file(path: Path) -> str:
    """MD5 of a file's bytes; used only for sync verification, not security."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def _parse_hatch_build_constants():
    """Extract constants from hatch_build.py via ast (no hatchling dependency)."""
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

    Covers ALL hatch_build copy categories:
      1. Flat python_tools/ (PYTHON_TOOLS = _PIPELINE_TOOLS + _SHARED)
      2. Recursive COPY_DIRS (codegen/, config/, templates/)
      3. TOP_LEVEL_FILES (parts_library.default.yaml)
      4. commands/zh/ from .claude/commands/
      5. knowledge/*_zh.md
      6. system_prompt.md
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

    # 4. commands/zh/
    cmd_src = _REPO_ROOT / ".claude" / "commands"
    cmd_zh = _DATA_DIR / "commands" / "zh"
    if cmd_src.is_dir():
        for md in sorted(cmd_src.glob("*.md")):
            pairs.append(("commands_zh", md.name, md, cmd_zh / md.name))

    # 5. knowledge/*_zh.md
    knowledge_pairs = {
        "skill_cad_help.md": "knowledge/skill_cad_help_zh.md",
        "skill_mech_design.md": "knowledge/skill_mech_design_zh.md",
    }
    for src_name, dst_rel in knowledge_pairs.items():
        src = _REPO_ROOT / src_name
        dst = _DATA_DIR / dst_rel
        pairs.append(("knowledge_zh", src_name, src, dst))

    # 6. system_prompt.md
    pairs.append((
        "system_prompt",
        "system_prompt.md",
        _REPO_ROOT / "system_prompt.md",
        _DATA_DIR / "system_prompt.md",
    ))

    return pairs


# 模块导入时构造参数化数据
_SYNC_PAIRS = _collect_sync_pairs()
_SYNC_IDS = [f"{cat}/{name}" for cat, name, _, _ in _SYNC_PAIRS]


@pytest.fixture(scope="session", autouse=True)
def _run_dev_sync_once():
    """session-scope fixture：跑一次 dev_sync.sync()，所有 case 共享结果。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "dev_sync", _REPO_ROOT / "scripts" / "dev_sync.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.sync(_REPO_ROOT)


@pytest.mark.parametrize(
    ("category", "name", "src", "dst"),
    _SYNC_PAIRS,
    ids=_SYNC_IDS,
)
def test_data_dir_mirror_matches_root(category, name, src, dst):
    """dev_sync.py 正确性验证：sync() 后每个文件都必须字节一致。"""
    if not src.exists():
        pytest.skip(f"Root source {src.relative_to(_REPO_ROOT)} does not exist")

    assert dst.exists(), (
        f"\nMirror MISSING after sync: {dst.relative_to(_REPO_ROOT)}\n"
        f"dev_sync.py 未同步此文件。检查 scripts/dev_sync.py 的覆盖范围。\n"
        f"(category={category})"
    )

    src_hash = _hash_file(src)
    dst_hash = _hash_file(dst)
    assert src_hash == dst_hash, (
        f"\nMirror MISMATCH after sync: {dst.relative_to(_REPO_ROOT)}\n"
        f"  root ({src.relative_to(_REPO_ROOT)}) md5={src_hash}\n"
        f"  data ({dst.relative_to(_REPO_ROOT)}) md5={dst_hash}\n"
        f"dev_sync.py 同步逻辑有 bug。\n"
        f"(category={category})"
    )


def test_python_tools_has_no_stray_files():
    """data/python_tools/ 不应存在 _PIPELINE_TOOLS + _SHARED 列表外的 .py 文件。"""
    pipeline_tools, _, _ = _parse_hatch_build_constants()
    known = set(pipeline_tools) | set(_HATCH_SHARED_FALLBACK)

    tools_dir = _DATA_DIR / "python_tools"
    if not tools_dir.exists():
        pytest.skip("data/python_tools/ does not exist (run dev_sync first)")

    actual_py = {
        f.name
        for f in tools_dir.glob("*.py")
        if f.name != "__init__.py"
    }

    stray = actual_py - known
    assert not stray, (
        f"\ndata/python_tools/ 含未注册的 .py 文件: {sorted(stray)}\n"
        f"Fix: 把它们加进 hatch_build._PIPELINE_TOOLS 或从 data/ 删除"
    )


def test_sync_pair_count_is_nontrivial():
    """健康检查：_SYNC_PAIRS 不应为空或异常小。"""
    assert len(_SYNC_PAIRS) >= 20, (
        f"Only {len(_SYNC_PAIRS)} sync pairs — expected ≥20. "
        f"Check _parse_hatch_build_constants() and hatch_build.py layout."
    )
