"""Task 12：sw_preflight.matrix.run_all_checks — 自动通过判定 7 项检查。

测试设计（照抄 plan 1157-1181）：
- test_all_checks_pass：7 项 check 全部 patch 为 (True, None) → passed=True
- test_first_fail_returns_diagnosis：前 2 项通过、第 3 项 (sw_installed) 失败
  → 短路返回 passed=False / failed_check='sw_installed'，验证短路逻辑
"""
from unittest.mock import patch


def test_all_checks_pass():
    """7 项 check 全过 → passed=True / failed_check=None"""
    from sw_preflight.matrix import run_all_checks
    with patch('sw_preflight.matrix._check_platform', return_value=(True, None)):
        with patch('sw_preflight.matrix._check_pywin32', return_value=(True, None)):
            with patch('sw_preflight.matrix._check_sw_installed', return_value=(True, None)):
                with patch('sw_preflight.matrix._check_toolbox_supported', return_value=(True, None)):
                    with patch('sw_preflight.matrix._check_com_healthy', return_value=(True, None)):
                        with patch('sw_preflight.matrix._check_addin_enabled', return_value=(True, None)):
                            with patch('sw_preflight.matrix._check_toolbox_path_healthy', return_value=(True, None)):
                                result = run_all_checks()
                                assert result['passed'] is True
                                assert result['failed_check'] is None


def test_first_fail_returns_diagnosis():
    """第一失败短路返回 — 验证 sw_installed 失败时不再跑后面 4 项"""
    from sw_preflight.matrix import run_all_checks
    from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo
    fake_diag = DiagnosisInfo(code=DiagnosisCode.SW_NOT_INSTALLED,
                              reason="未检测到", suggestion="装", severity='block')
    with patch('sw_preflight.matrix._check_platform', return_value=(True, None)):
        with patch('sw_preflight.matrix._check_pywin32', return_value=(True, None)):
            with patch('sw_preflight.matrix._check_sw_installed', return_value=(False, fake_diag)):
                result = run_all_checks()
                assert result['passed'] is False
                assert result['failed_check'] == 'sw_installed'
                assert result['diagnosis'].code == DiagnosisCode.SW_NOT_INSTALLED


def test_check_toolbox_supported_standard_edition(monkeypatch):
    """edition == 'standard'（小写）→ _check_toolbox_supported 返 False。"""
    from adapters.solidworks import sw_detect
    from sw_preflight import matrix

    sw_detect._reset_cache()
    fake = sw_detect.SwInfo(installed=True, version_year=2024, edition='standard')
    monkeypatch.setattr(sw_detect, 'detect_solidworks', lambda: fake)
    ok, diag = matrix._check_toolbox_supported()
    assert ok is False
    assert diag is not None


def test_check_toolbox_path_healthy_passes_when_dir_healthy(monkeypatch, tmp_path):
    """_check_toolbox_path_healthy：健康目录 → True。"""
    from adapters.solidworks import sw_detect
    from sw_preflight import matrix

    (tmp_path / "swbrowser.sldedb").write_bytes(b"SQLite")
    (tmp_path / "GB").mkdir()
    (tmp_path / "GB" / "p.sldprt").write_bytes(b"\x00")

    sw_detect._reset_cache()
    fake = sw_detect.SwInfo(installed=True, toolbox_dir=str(tmp_path))
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake)

    ok, diag = matrix._check_toolbox_path_healthy()
    assert ok is True
    assert diag is None


def test_check_toolbox_path_healthy_fails_missing_sldedb(monkeypatch, tmp_path):
    """_check_toolbox_path_healthy：缺 sldedb → False。"""
    from adapters.solidworks import sw_detect
    from sw_preflight import matrix

    (tmp_path / "GB").mkdir()
    (tmp_path / "GB" / "p.sldprt").write_bytes(b"\x00")

    sw_detect._reset_cache()
    fake = sw_detect.SwInfo(installed=True, toolbox_dir=str(tmp_path))
    monkeypatch.setattr(sw_detect, "detect_solidworks", lambda: fake)

    ok, diag = matrix._check_toolbox_path_healthy()
    assert ok is False


def test_addin_enabled_advisory_in_run_all_checks(monkeypatch):
    """addin_enabled 失败时 run_all_checks passed=True，advisory_failures 含 addin_enabled。"""
    import sw_preflight.matrix as m

    for name, attr in m.CHECK_ORDER:
        if name != "addin_enabled":
            monkeypatch.setattr(m, attr, lambda: (True, None))
    monkeypatch.setattr(m, "_check_addin_enabled", lambda: (False, None))

    result = m.run_all_checks()
    assert result["passed"] is True
    assert "addin_enabled" in result["advisory_failures"]
