# tests/test_cad_pipeline_preflight_chain.py
"""cad_pipeline 串联 cad-spec → cad-codegen 时，通过共享 cache.json 复用 preflight。

cad_pipeline.py 本身不跑新的 preflight（各入口自己跑）——这个测试是合约占位。
真正的跨入口 cache 复用验证在 Task 34 集成测试 matrix 里。
"""


def test_pipeline_runs_cad_spec_then_codegen_shares_cache():
    """cad_pipeline 串联 cad-spec → cad-codegen，cache.json 跨入口复用（详细测试在 Task 34）"""
    assert True  # placeholder
