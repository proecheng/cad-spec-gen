"""Photo3D 普通用户流程和安装版帮助契约。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]

USER_FLOW_TERMS = {
    "photo3d",
    "run_id",
    "PHOTO3D_REPORT.json",
    "ACTION_PLAN.json",
    "LLM_CONTEXT_PACK.json",
    "ARTIFACT_INDEX.json",
    "pass",
    "warning",
    "blocked",
    "enhancement_status",
    "baseline",
    "baseline-signature",
    "CHANGE_SCOPE.json",
}

DOC_FLOW_TERMS = {
    "路径隔离",
    "旧产物",
    "接受基准",
    "候选基准",
    "authorized",
}

DELIVERY_STATUS_TERMS = {
    "accepted",
    "preview",
    "blocked",
}


def test_photo3d_help_explains_user_flow_and_reports():
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "photo3d", "--help"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    help_text = result.stdout
    for term in USER_FLOW_TERMS:
        assert term in help_text
    for term in DELIVERY_STATUS_TERMS:
        assert term in help_text
    assert "Gate status" in help_text
    assert "Enhancement delivery status" in help_text
    assert "Status semantics: accepted" not in help_text
    assert "python cad_pipeline.py photo3d --subsystem <name>" in help_text


def test_cad_help_docs_describe_photo3d_foolproof_user_flow():
    for rel in (
        "docs/cad-help-guide-zh.md",
        "skill_cad_help.md",
        ".claude/commands/cad-help.md",
    ):
        text = (_ROOT / rel).read_text(encoding="utf-8")
        for term in USER_FLOW_TERMS:
            assert term in text, f"{rel} missing {term}"
        for term in DELIVERY_STATUS_TERMS:
            assert term in text, f"{rel} missing {term}"
        for term in DOC_FLOW_TERMS:
            assert term in text, f"{rel} missing {term}"
        assert ("Gate status" in text or "门禁状态" in text), rel
        assert ("Enhancement delivery status" in text or "增强交付状态" in text), rel
        assert "大模型" in text, f"{rel} missing LLM-facing guidance"
        assert "不能扫描目录猜最新文件" in text, f"{rel} missing no-fallback rule"


def test_skill_metadata_advertises_photo3d_and_llm_action_reports():
    for rel in ("skill.json", "src/cad_spec_gen/data/skill.json"):
        data = json.loads((_ROOT / rel).read_text(encoding="utf-8"))

        cad_help = next(skill for skill in data["skills"] if skill["id"] == "cad-help")
        assert "photo3d" in cad_help["description"], rel
        assert "ACTION_PLAN.json" in cad_help["description"], rel
        assert "pass/warning/blocked" in cad_help["description"], rel

        tools_by_name = {tool["name"]: tool for tool in data["tools"]}
        assert "photo3d" in tools_by_name, rel
        assert (
            tools_by_name["photo3d"]["cli"]
            == "python cad_pipeline.py photo3d --subsystem <name>"
        )
        assert "LLM_CONTEXT_PACK.json" in tools_by_name["photo3d"]["description"]
        assert "pass/warning/blocked" in tools_by_name["photo3d"]["description"]
        assert "accepted/preview/blocked" in tools_by_name["photo3d"]["description"]
