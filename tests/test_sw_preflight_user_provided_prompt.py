"""Task 22 — prompt_user_provided 三选一主入口测试"""
from unittest.mock import patch
from pathlib import Path


def test_user_choice_stand_in_returns_all_stand_in():
    """用户选 stand_in：全部缺件 → stand_in_keys"""
    from sw_preflight.user_provided import prompt_user_provided
    missing = [{'name_cn': 'GB/T 70.1 M3×8'}, {'name_cn': '私有件 X'}]
    with patch('sw_preflight.io.three_choice_prompt', return_value='stand_in'):
        result = prompt_user_provided(missing)
        assert len(result.stand_in_keys) == 2
        assert len(result.provided_files) == 0


def test_user_choice_skip_returns_all_skipped():
    """用户选 skip：全部缺件 → skipped_keys"""
    from sw_preflight.user_provided import prompt_user_provided
    missing = [{'name_cn': 'GB/T 70.1 M3×8'}]
    with patch('sw_preflight.io.three_choice_prompt', return_value='skip'):
        result = prompt_user_provided(missing)
        assert len(result.skipped_keys) == 1


def test_user_choice_provide_loops_dialog(tmp_path):
    """用户选 provide：逐行 file dialog；取消后二次决策 stand-in/skip"""
    from sw_preflight.user_provided import prompt_user_provided
    missing = [{'name_cn': 'GB/T 70.1 M3×8'}, {'name_cn': '私有件 X'}]
    fake_step = tmp_path / 'm3x8.step'
    fake_step.write_bytes(b'ISO-10303-21;\n' + b'\n' * 20000)
    with patch('sw_preflight.io.three_choice_prompt', return_value='provide'):
        with patch('sw_preflight.io.ask_step_file', side_effect=[fake_step, None]):  # 第 2 个取消
            with patch('builtins.input', return_value='1'):  # 取消后选 stand-in
                result = prompt_user_provided(missing, copy_files=False)
                assert len(result.provided_files) == 1
                assert len(result.stand_in_keys) == 1
