"""Task 3 — sw_preflight/diagnosis.py 的 TDD 测试"""
from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo


def test_diagnosis_code_v1_complete():
    expected = {
        'PLATFORM_NOT_WINDOWS', 'SW_NOT_INSTALLED', 'SW_TOOLBOX_NOT_SUPPORTED',
        'LICENSE_PROBLEM', 'COM_REGISTRATION_BROKEN', 'TOOLBOX_PATH_INVALID',
        'TOOLBOX_PATH_NOT_ACCESSIBLE', 'PYWIN32_MISSING', 'PYWIN32_INSTALL_FAILED',
        'ADDIN_DISABLED', 'MULTIPLE_SW_VERSIONS_AMBIGUOUS', 'INSUFFICIENT_PRIVILEGES',
        'BOM_ROW_NO_MATCH', 'BOM_ROW_FELL_THROUGH_TO_STAND_IN',
        'USER_PROVIDED_SOURCE_HASH_MISMATCH', 'USER_PROVIDED_SCHEMA_INVALID',
    }
    actual = {c.name for c in DiagnosisCode}
    missing = expected - actual
    assert not missing, f"v1 码缺失: {missing}"


def test_diagnosis_info_required_fields():
    d = DiagnosisInfo(
        code=DiagnosisCode.SW_NOT_INSTALLED,
        reason="未检测到 SolidWorks 安装",
        suggestion="请安装 SolidWorks Pro 或 Premium",
        severity='block',
    )
    assert d.severity == 'block'
    assert d.code == DiagnosisCode.SW_NOT_INSTALLED
