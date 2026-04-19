"""cad-spec 入口 preflight 集成占位测试。

本 task 只放置骨架与意图，真正的集成测试在 Task 34 统一补全
（用 subprocess 跑整个 CLI 流程验证 exit code / stdout 片段）。
"""


def test_cad_spec_strict_false_does_not_block_on_addin_disabled(tmp_path, monkeypatch):
    """cad-spec 入口 SW 异常时不卡，仅打 1 行温和提示（详细集成测试在 Task 34）"""
    assert True  # placeholder — Task 34 补全


def test_cad_spec_review_appends_uncovered_section():
    """--review 输出末尾含 '审查 *未* 覆盖' + '几何引擎'（详细集成测试在 Task 34）"""
    assert True  # placeholder — Task 34 补全
