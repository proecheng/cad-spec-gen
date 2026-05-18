"""L5 e2e smoke (manual, requires GEMINI_API_KEY + 花钱)。

跑前条件：
- 环境变量 GEMINI_API_KEY 已设
- v2.36.0 main GISBOT 归档 / jiehuo 归档 已存在于 D:\\Work\\cad-tests\\
- 跑命令：python -m pytest tests/jury_loop/test_matches_spec_e2e_smoke.py -m requires_jury_loop_e2e
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_jury_loop_e2e


def test_e2e_matches_spec_pass_on_v2_36_1_main_end_effector() -> None:
    """v2.36.1 main GISBOT 归档 / 法兰 4 臂已画 → matches_spec PASS。

    Acceptance #6 (F6 fixed): features >=3 含 anchor flange_arms_4。

    手动跑步骤：
    1. cd D:/Work/cad-tests/GISBOT/04_render + 05_enhance fixture 路径
    2. python cad_pipeline.py enhance-check --subsystem end_effector --spec-md ... --design-doc ...
    3. 看 cad/end_effector/.cad-spec-gen/matches_spec_features.json：
       - features_count >= 3
       - "flange_arms_4" in [f["feature_id"] for f in features]
    4. 看 cad/end_effector/.cad-spec-gen/runs/<run_id>/PHOTO3D_JURY_REPORT.json：
       - matches_spec_status == "pass"
       - overall_matches_spec is True
    """
    pytest.skip("manual e2e — requires GEMINI_API_KEY + 已存在的 GISBOT 归档")


def test_e2e_matches_spec_fail_when_arms_removed() -> None:
    """反向：故意 break ee_001_01.py 删 4 臂 union -> matches_spec FAIL with missing flange_arms_4。

    注（v2.37.15）：本 fixture 假设全视角 features 集合相同（全删 flange_arms_4 → 全失败）→
    matches_spec_status='fail'。若 features 出现 per-view 差异（部分视角缺特征），
    partial fail 应为 'warn' 而非 'fail'。

    手动跑步骤：
    1. git stash（保护工作树）
    2. 编辑 cad/end_effector/ee_001_01.py 注释掉 4 臂 union 段
    3. python cad_pipeline.py build --subsystem end_effector + render + enhance
    4. 看 PHOTO3D_JURY_REPORT.json：
       - matches_spec_status == "fail"
       - "flange_arms_4" in per_view_failed_features values
    5. 看 cad/end_effector/.cad-spec-gen/MATCHES_SPEC_TODO.md 应存在
    6. git stash pop 恢复
    """
    pytest.skip("manual e2e — needs git stash + rebuild")


def test_e2e_features_extraction_stable_across_3_runs() -> None:
    """spec §7 risk: 跑 3 次比 features 集合一致（temperature=0 验证）。

    手动跑步骤：
    1. rm cad/end_effector/.cad-spec-gen/matches_spec_features.json
    2. 连续跑 3 次 photo3d-jury（每次 features cache 重抽）
    3. 收集 3 次 features feature_id 集合
    4. 断 3 集合 ⊇ {flange_arms_4} (anchor 必出)
    5. 断 3 集合两两 Jaccard 相似度 >= 0.7（合理 LLM variance）
    """
    pytest.skip("manual e2e — 3x cost")
