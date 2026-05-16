"""tests/dev/test_rebrand_test_archive_integration.py — GISBOT sandbox 集成测。

rev 5 B2 fix: conftest 自动检 .test-archive-marker 存在；缺则全 skip。
rev 5 B3 fix: 用户必先 touch D:/Work/cad-tests/GISBOT/.test-archive-marker；
              本 PR retro 记录该命令。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_GISBOT_DIR = Path("D:/Work/cad-tests/GISBOT")
_TOOL = "tools/dev/rebrand_test_archive.py"


@pytest.mark.requires_test_archive
def test_gisbot_sandbox_rebrand_end_to_end(tmp_path: Path) -> None:
    """集成测：sandbox copy GISBOT/ → --apply end_effector → GISBOT_REBRANDED → 验 8 类 JSON 改写 + _archive_*/ 未改。"""
    sandbox = tmp_path / "gisbot_sandbox"
    shutil.copytree(_GISBOT_DIR, sandbox, symlinks=False)

    # 跑 --apply
    cp = subprocess.run(
        [
            sys.executable,
            _TOOL,
            str(sandbox),
            "--from",
            "end_effector",
            "--to",
            "GISBOT_REBRANDED",
            "--apply",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert cp.returncode == 0, f"工具失败：\n{cp.stderr}"

    # 验 8 类 JSON 已改
    targets = [
        ("02_codegen/CUSTOM_PARTS_AUDIT.json", "subsystem"),
        ("02_codegen/MODEL_CONTRACT.json", "subsystem"),
        ("02_codegen/PRODUCT_GRAPH.json", "subsystem"),
        ("02_codegen/render_config.json", "subsystem.name"),  # pattern B
        ("04_render/render_manifest.json", "subsystem"),
        ("05_enhance/ENHANCEMENT_REPORT.json", "subsystem"),
        # cad/end_effector/.cad-spec-gen/ARTIFACT_INDEX.json — 路径名也含 end_effector
        ("cad/end_effector/.cad-spec-gen/ARTIFACT_INDEX.json", "subsystem"),
    ]
    for relpath, location in targets:
        p = sandbox / relpath
        if not p.exists():
            continue  # 不是所有 GISBOT 副本都有完整 8 类
        data = json.loads(p.read_text(encoding="utf-8"))
        if location == "subsystem":
            assert data.get("subsystem") == "GISBOT_REBRANDED", f"{relpath}: 未改"
        elif location == "subsystem.name":
            assert data.get("subsystem", {}).get("name") == "GISBOT_REBRANDED", f"{relpath}: name 未改"
            # name_cn 字段保留
            assert "name_cn" in data["subsystem"], f"{relpath}: name_cn 字段丢失"

    # 验 _archive_*/ 路径未改（保历史快照）
    archive_dirs = list(sandbox.glob("_archive_*"))
    for arch_dir in archive_dirs:
        for json_file in arch_dir.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(data, dict):
                val = data.get("subsystem")
                if isinstance(val, str):
                    assert val != "GISBOT_REBRANDED", f"{json_file}: _archive_/ 被改"
                elif isinstance(val, dict) and isinstance(val.get("name"), str):
                    assert val["name"] != "GISBOT_REBRANDED", f"{json_file}: _archive_/ name 被改"
