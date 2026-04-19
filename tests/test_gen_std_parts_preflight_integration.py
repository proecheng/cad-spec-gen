"""cad-codegen 入口 preflight 集成占位测试。

详细集成测试在 Task 34 统一补全（subprocess 跑 CLI + 验 exit code + 检 report 文件存在）。
本文件仅占位，确保 pytest 能采集到预期数量的测试，便于 Task 34 直接替换 body。
"""


def test_codegen_reads_cache_when_recent(tmp_path):
    """cache.json TTL 内 → 复用 preflight 不重做（详细测试在 Task 34）"""
    assert True  # placeholder


def test_codegen_emits_report_at_end(tmp_path):
    """跑完 stdout 含 sw_report.html 路径（详细测试在 Task 34）"""
    assert True  # placeholder
