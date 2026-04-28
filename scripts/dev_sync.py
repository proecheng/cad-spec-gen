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
import argparse
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


def _needs_file_sync(src: Path, dst: Path) -> bool:
    """返回 src 是否会更新 dst；不写文件。"""
    if not src.exists():
        return False
    return not dst.exists() or _md5(src) != _md5(dst)


def _sync_dir(src_dir: Path, dst_dir: Path) -> list[Path]:
    """递归同步目录，返回已更新文件列表。

    与 hatch_build.py 行为对齐：先同步所有源文件，再删除目标目录中
    源目录已不存在的陈旧文件（hatch_build 用 rmtree+copytree，
    这里用增量同步+陈旧清理，效果一致但更精确）。
    """
    updated: list[Path] = []
    if not src_dir.is_dir():
        return updated

    # 收集源文件的相对路径集合，用于后续陈旧检测
    src_rels: set[Path] = set()
    for src_file in sorted(src_dir.rglob("*")):
        if not src_file.is_file():
            continue
        if "__pycache__" in src_file.parts or src_file.suffix in (".pyc", ".pyo"):
            continue
        rel = src_file.relative_to(src_dir)
        src_rels.add(rel)
        dst_file = dst_dir / rel
        if _sync_file(src_file, dst_file):
            updated.append(dst_file)

    # 删除目标目录中源目录已不存在的陈旧文件
    if dst_dir.is_dir():
        for dst_file in sorted(dst_dir.rglob("*")):
            if not dst_file.is_file():
                continue
            if "__pycache__" in dst_file.parts or dst_file.suffix in (".pyc", ".pyo"):
                continue
            rel = dst_file.relative_to(dst_dir)
            if rel not in src_rels:
                dst_file.unlink()
                updated.append(dst_file)

    return updated


def _check_dir(src_dir: Path, dst_dir: Path) -> list[Path]:
    """递归检查目录同步漂移；返回会被更新/删除的目标文件。"""
    changed: list[Path] = []
    if not src_dir.is_dir():
        return changed

    src_rels: set[Path] = set()
    for src_file in sorted(src_dir.rglob("*")):
        if not src_file.is_file():
            continue
        if "__pycache__" in src_file.parts or src_file.suffix in (".pyc", ".pyo"):
            continue
        rel = src_file.relative_to(src_dir)
        src_rels.add(rel)
        dst_file = dst_dir / rel
        if _needs_file_sync(src_file, dst_file):
            changed.append(dst_file)

    if dst_dir.is_dir():
        for dst_file in sorted(dst_dir.rglob("*")):
            if not dst_file.is_file():
                continue
            if "__pycache__" in dst_file.parts or dst_file.suffix in (".pyc", ".pyo"):
                continue
            rel = dst_file.relative_to(dst_dir)
            if rel not in src_rels:
                changed.append(dst_file)

    return changed


# ─── AGENTS.md 生成（spec v4: 2026-04-19 skills-refactor）────────────────────────
# 从 data/skill.json 生成仓库根 AGENTS.md，给 Codex CLI 等非 Claude LLM 作项目指南。
# 确定性：纯函数 skill.json → 固定文本；无 timestamp / git rev / 任何 volatile 数据。

_AGENTS_TEMPLATE = """\
<!-- AUTO-GENERATED by scripts/dev_sync.py from src/cad_spec_gen/data/skill.json -->
<!-- 请勿手改；改 skill metadata 后跑 python scripts/dev_sync.py -->

# AGENTS.md — cad-spec-gen 代理指南

cad-spec-gen 是 6 阶段 CAD 混合渲染管线（设计文档 → Spec → CadQuery 代码 → 2D 图纸 → 3D 渲染 → AI 增强）。

- **仓库**：{homepage}
- **Python**：{python_req}
- **版本**：v{version}

## 可用 Skill（{skill_count} 个）

| Skill | Trigger | 说明 |
|---|---|---|
{skill_rows}

## 典型流程

```bash
# Phase 1: 从设计文档生成 Spec
python cad_pipeline.py spec --design-doc docs/design/04-*.md

# Phase 2: 从 Spec 生成代码
python cad_pipeline.py codegen --subsystem <名称>
```

Claude Code 用户可直接用 `/cad-spec`、`/cad-codegen` 等 slash command。

## 约定

- 测试：`.venv/Scripts/python.exe -m pytest`（Windows venv）
- commit：`<type>(<scope>): <中文描述>`
- 所有输出中文（代码标识符除外）

## 开发者

- Skill 内容在 `.claude/commands/<id>.md`（中文）和 `src/cad_spec_gen/data/commands/en/<id>.md`（英文）
- Metadata 在 `src/cad_spec_gen/data/skill.json`
- 改完跑 `python scripts/dev_sync.py` 同步；pre-commit 自动守护

---
_本文件自动生成。最后更新来源：skill.json v{version}_
"""


def _render_skill_row(skill: dict) -> str:
    """渲染单行 skill 表格。description 裁剪到 100 字以内，换行替换为空格。"""
    desc = skill.get("description", "").replace("\n", " ").strip()
    if len(desc) > 100:
        desc = desc[:100] + "..."
    return f"| {skill['name']} | `{skill['trigger']}` | {desc} |"


def _render_agents_md(data_dir: Path) -> str:
    """从 data_dir/skill.json 渲染 AGENTS.md 内容。"""
    import json
    skill_json = json.loads((data_dir / "skill.json").read_text(encoding="utf-8"))
    skill_rows = "\n".join(_render_skill_row(s) for s in skill_json["skills"])
    return _AGENTS_TEMPLATE.format(
        homepage=skill_json.get("homepage", "N/A"),
        python_req=skill_json.get("requires", {}).get("python", ">=3.10"),
        version=skill_json.get("version", "dev"),
        skill_count=len(skill_json["skills"]),
        skill_rows=skill_rows,
    )


def _sync_agents_md(root: Path, data_dir: Path) -> bool:
    """生成 AGENTS.md 到仓库根。若内容变化则写入，返回是否写入。"""
    agents_path = root / "AGENTS.md"
    new_content = _render_agents_md(data_dir)
    if agents_path.exists() and agents_path.read_text(encoding="utf-8") == new_content:
        return False
    agents_path.write_text(new_content, encoding="utf-8")
    return True


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

    # 7. AGENTS.md（顶层，跨 LLM 兜底；纯从 skill.json 生成）
    if _sync_agents_md(root, data_dir):
        updated.append(root / "AGENTS.md")

    return updated


def check(root: Path | None = None) -> list[Path]:
    """只检查同步漂移，不写文件。返回会被 sync() 更新的路径列表。"""
    root = root or _REPO_ROOT
    data_dir = root / "src" / "cad_spec_gen" / "data"
    changed: list[Path] = []

    pipeline_tools, copy_dirs, top_level_files = _parse_hatch_build_constants(root)
    all_python_tools = pipeline_tools + _HATCH_SHARED_FALLBACK

    tools_dir = data_dir / "python_tools"
    for fname in all_python_tools:
        dst = tools_dir / fname
        if _needs_file_sync(root / fname, dst):
            changed.append(dst)

    for src_name, dst_name in copy_dirs.items():
        changed.extend(_check_dir(root / src_name, data_dir / dst_name))

    cmd_src = root / _COMMAND_SOURCE
    cmd_zh = data_dir / "commands" / "zh"
    if cmd_src.is_dir():
        for md in sorted(cmd_src.glob("*.md")):
            dst = cmd_zh / md.name
            if _needs_file_sync(md, dst):
                changed.append(dst)

    for src_name, dst_rel in _KNOWLEDGE_PAIRS.items():
        dst = data_dir / dst_rel
        if _needs_file_sync(root / src_name, dst):
            changed.append(dst)

    dst = data_dir / "system_prompt.md"
    if _needs_file_sync(root / "system_prompt.md", dst):
        changed.append(dst)

    for src_name, dst_rel in top_level_files.items():
        dst = data_dir / dst_rel
        if _needs_file_sync(root / src_name, dst):
            changed.append(dst)

    agents_path = root / "AGENTS.md"
    new_agents = _render_agents_md(data_dir)
    if not agents_path.exists() or agents_path.read_text(encoding="utf-8") != new_agents:
        changed.append(agents_path)

    return changed


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    """CLI 入口。

    默认模式：有文件被更新返回 1（pre-commit 约定），无变更返回 0。
    --check：只检查不写；有漂移返回 1，CI 可直接 fail。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="check drift without writing")
    args = parser.parse_args(argv)

    root = root or _REPO_ROOT
    if args.check:
        changed = check(root)
        if changed:
            print(f"dev_sync: {len(changed)} file(s) out of date:")
            for p in changed:
                print(f"  {p.relative_to(root)}")
            return 1
        print("dev_sync: all mirrors up to date.")
        return 0

    changed = sync(root)
    if changed:
        print(f"dev_sync: {len(changed)} file(s) updated:")
        for p in changed:
            print(f"  {p.relative_to(root)}")
        return 1
    print("dev_sync: all mirrors up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
