from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "sw_b9_mock_artifacts"


class TestAcceptanceSummary:
    def test_builds_top_level_pass(self):
        from tools.sw_b9_report_builder import build_acceptance_summary

        summary = build_acceptance_summary(FIXTURES)
        assert summary["schema_version"] == 1
        assert summary["pass"] is True
        assert summary["stages"]["stage_d"]["skipped"] is True

    def test_fail_if_stage_a_below_target(self, tmp_path):
        from tools.sw_b9_report_builder import build_acceptance_summary

        # 复制 fixtures 到 tmp，改 stage_a 为 fail
        import shutil
        work = tmp_path / "artifacts"
        shutil.copytree(FIXTURES, work)
        stage_a = json.loads((work / "stage_a.json").read_text())
        stage_a["pass"] = False
        (work / "stage_a.json").write_text(json.dumps(stage_a))

        summary = build_acceptance_summary(work)
        assert summary["pass"] is False


class TestMarkdownReport:
    def test_produces_markdown_with_sections(self):
        from tools.sw_b9_report_builder import render_markdown_report

        md = render_markdown_report(FIXTURES, report_date="2026-04-14")
        assert "# SW-B9 真跑验收报告 — 2026-04-14" in md
        assert "## 顶层结论" in md
        assert "决策 #34" in md
        assert "GISBOT" in md  # 样本不足声明
        assert "## Stage 汇总表" in md

    def test_conditional_label_when_d_skipped(self):
        from tools.sw_b9_report_builder import render_markdown_report

        md = render_markdown_report(FIXTURES, report_date="2026-04-14")
        # D 被 skip 时状态应显示 CONDITIONAL 而非 PASS
        assert "CONDITIONAL" in md
