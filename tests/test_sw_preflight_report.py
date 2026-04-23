# tests/test_sw_preflight_report.py
# Task 28 — emit_report 生成 HTML + JSON，且术语去技术化（主体不含 ROT 字面）
from pathlib import Path
from unittest.mock import MagicMock
from sw_preflight.types import (PreflightResult, BomDryRunResult, RowOutcome,
                                  PartCategory, FixRecord)


def test_emit_report_generates_html_and_json(tmp_path):
    pre = PreflightResult(passed=True, sw_info=MagicMock(edition='professional', version_year=2024),
                          fixes_applied=[FixRecord(action='rot_orphan_release',
                                                    before_state='unhealthy',
                                                    after_state='healthy', elapsed_ms=1200)],
                          diagnosis=None, per_step_ms={'detect': 12.3})
    dry = BomDryRunResult(total_rows=2, hit_rows=[], stand_in_rows=[], missing_rows=[])
    from sw_preflight.report import emit_report
    out = emit_report([], dry, pre, output_dir=tmp_path)
    assert out.exists()
    assert (tmp_path / 'sw_report.html').exists()
    assert (tmp_path / 'sw_report_data.json').exists()
    html = (tmp_path / 'sw_report.html').read_text(encoding='utf-8')
    assert '程序残留清理' in html  # ROT 僵死 → 用户友好术语
    assert 'ROT' not in html.split('<details>')[0]  # 主体不含 ROT 字面值（折叠区可有）
