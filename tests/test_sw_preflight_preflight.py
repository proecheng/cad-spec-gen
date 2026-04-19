"""sw_preflight.preflight — run_preflight 主入口测试（Task 26）。

覆盖 4 场景：
  1. 全过 → PreflightResult(passed=True)
  2. 卡住 + strict=True → sys.exit(2)
  3. 卡住 + strict=False → 只打提示，返回 passed=False
  4. run_id 非空 → 落 sw_preflight_cache.json
"""
from unittest.mock import patch, MagicMock

from sw_preflight.types import PreflightResult  # noqa: F401 — 供类型提示/导入副作用


def test_run_preflight_strict_true_passed():
    """全过 → 返回 PreflightResult(passed=True)。"""
    with patch('sw_preflight.matrix.run_all_checks',
               return_value={'passed': True, 'failed_check': None, 'diagnosis': None}):
        with patch('adapters.solidworks.sw_detect.detect_solidworks',
                   return_value=MagicMock(installed=True, version_year=2024)):
            from sw_preflight.preflight import run_preflight
            result = run_preflight(strict=True)
            assert result.passed is True


def test_run_preflight_strict_true_blocked():
    """卡住且不可修 → strict=True 时 sys.exit(2)。"""
    from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo
    fake_diag = DiagnosisInfo(
        code=DiagnosisCode.SW_NOT_INSTALLED,
        reason="未装",
        suggestion="装",
        severity='block',
    )
    with patch('sw_preflight.matrix.run_all_checks',
               return_value={'passed': False, 'failed_check': 'sw_installed', 'diagnosis': fake_diag}):
        with patch('sw_preflight.matrix.try_one_click_fix', return_value=None):
            from sw_preflight.preflight import run_preflight
            import pytest
            with pytest.raises(SystemExit) as exc:
                run_preflight(strict=True)
            assert exc.value.code == 2


def test_run_preflight_strict_false_just_warns(capsys):
    """strict=False 异常时只打 1 行温和提示，不 raise。"""
    from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo
    fake_diag = DiagnosisInfo(
        code=DiagnosisCode.ADDIN_DISABLED,
        reason="未启用",
        suggestion="启用",
        severity='block',
    )
    with patch('sw_preflight.matrix.run_all_checks',
               return_value={'passed': False, 'failed_check': 'addin_enabled', 'diagnosis': fake_diag}):
        from sw_preflight.preflight import run_preflight
        result = run_preflight(strict=False)
        assert result.passed is False  # 不 raise
        captured = capsys.readouterr()
        assert 'SW 状态预告' in captured.out


def test_run_preflight_writes_cache(tmp_path, monkeypatch):
    """preflight 完成后写 artifacts/{run_id}/sw_preflight_cache.json。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'artifacts' / 'test-run').mkdir(parents=True)
    with patch('sw_preflight.matrix.run_all_checks',
               return_value={'passed': True, 'failed_check': None, 'diagnosis': None}):
        with patch('adapters.solidworks.sw_detect.detect_solidworks',
                   return_value=MagicMock(installed=True, version_year=2024)):
            from sw_preflight.preflight import run_preflight
            run_preflight(strict=True, run_id='test-run', entry='cad-spec')
    cache_file = tmp_path / 'artifacts' / 'test-run' / 'sw_preflight_cache.json'
    assert cache_file.exists()
