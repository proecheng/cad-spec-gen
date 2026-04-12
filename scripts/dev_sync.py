#!/usr/bin/env python3
"""dev_sync.py — 将 root 源文件同步到 src/cad_spec_gen/data/。

与 hatch_build.py::CustomBuildHook.initialize() 产出一致，但不依赖
hatchling。用 ast.parse() 从 hatch_build.py 提取常量列表。

用法：
    python scripts/dev_sync.py          # CLI：有变更 exit 1，无变更 exit 0
    from scripts.dev_sync import sync   # API：返回已更新文件列表
"""

from __future__ import annotations

import ast
import hashlib
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _REPO_ROOT / "src" / "cad_spec_gen" / "data"

# 与 hatch_build.py 的 fallback 保持一致：cad_paths.SHARED_TOOL_FILES 实际不存在，
# hatch_build 始终走 except 分支用这份硬编码列表。
_HATCH_SHARED_FALLBACK = [
    "drawing.py",
    "draw_three_view.py",
    "cq_to_dxf.py",
    "render_dxf.py",
    "render_config.py",
    "cad_spec_defaults.py",
]

# hatch_build.py 中写死的额外同步项（commands、knowledge、system_prompt）
_COMMAND_SOURCE = ".claude/commands"
_KNOWLEDGE_PAIRS = {
    "skill_cad_help.md": "knowledge/skill_cad_help_zh.md",
    "skill_mech_design.md": "knowledge/skill_mech_design_zh.md",
}


def _md5(path: Path) -> str:
    """文件的 MD5 摘要，仅用于变更检测。"""
    return hashlib.md5(path.read_bytes()).hexdigest()


def _parse_hatch_build_constants(
    repo_root: Path,
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """用 ast.parse() 提取 hatch_build.py 的 _PIPELINE_TOOLS、COPY_DIRS、TOP_LEVEL_FILES。"""
    hatch_src = (repo_root / "hatch_build.py").read_text(encoding="utf-8")
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


def _sync_file(src: Path, dst: Path) -> bool:
    """若 src 存在且与 dst 内容不同，则复制。返回是否实际写入。"""
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and _md5(src) == _md5(dst):
        return False
    shutil.copy2(src, dst)
    return True


def _sync_dir(src_dir: Path, dst_dir: Path) -> list[Path]:
    """递归同步目录，返回已更新文件列表。"""
    updated: list[Path] = []
    if not src_dir.is_dir():
        return updated
    for src_file in sorted(src_dir.rglob("*")):
        if not src_file.is_file():
            continue
        if "__pycache__" in src_file.parts or src_file.suffix in (".pyc", ".pyo"):
            continue
        rel = src_file.relative_to(src_dir)
        dst_file = dst_dir / rel
        if _sync_file(src_file, dst_file):
            updated.append(dst_file)
    return updated


def sync(root: Path | None = None) -> list[Path]:
    """将 root 源文件同步到 data/，返回实际更新的文件路径列表。

    与 hatch_build.py::CustomBuildHook.initialize() 覆盖范围完全一致。
    """
    root = root or _REPO_ROOT
    data_dir = root / "src" / "cad_spec_gen" / "data"
    updated: list[Path] = []

    pipeline_tools, copy_dirs, top_level_files = _parse_hatch_build_constants(root)
    all_python_tools = pipeline_tools + _HATCH_SHARED_FALLBACK

    # 1. python_tools/ — 平铺 .py 文件
    tools_dir = data_dir / "python_tools"
    for fname in all_python_tools:
        if _sync_file(root / fname, tools_dir / fname):
            updated.append(tools_dir / fname)

    # 2. COPY_DIRS — codegen/, config/, templates/ 递归复制
    for src_name, dst_name in copy_dirs.items():
        updated.extend(_sync_dir(root / src_name, data_dir / dst_name))

    # 3. commands/zh/ — 从 .claude/commands/*.md
    cmd_src = root / _COMMAND_SOURCE
    cmd_zh = data_dir / "commands" / "zh"
    if cmd_src.is_dir():
        for md in sorted(cmd_src.glob("*.md")):
            if _sync_file(md, cmd_zh / md.name):
                updated.append(cmd_zh / md.name)

    # 4. knowledge/*_zh.md
    for src_name, dst_rel in _KNOWLEDGE_PAIRS.items():
        src = root / src_name
        dst = data_dir / dst_rel
        if _sync_file(src, dst):
            updated.append(dst)

    # 5. system_prompt.md
    if _sync_file(root / "system_prompt.md", data_dir / "system_prompt.md"):
        updated.append(data_dir / "system_prompt.md")

    # 6. TOP_LEVEL_FILES
    for src_name, dst_rel in top_level_files.items():
        dst = data_dir / dst_rel
        if _sync_file(root / src_name, dst):
            updated.append(dst)

    return updated


def main() -> int:
    """CLI 入口。有文件被更新返回 1（pre-commit 约定），无变更返回 0。"""
    changed = sync()
    if changed:
        print(f"dev_sync: {len(changed)} file(s) updated:")
        for p in changed:
            print(f"  {p.relative_to(_REPO_ROOT)}")
        return 1
    print("dev_sync: all mirrors up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
