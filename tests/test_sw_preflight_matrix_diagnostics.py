"""Task 18 — make_diagnosis 工厂 + DIAGNOSIS_TEMPLATES 覆盖测试。

照抄 plan 1645-1666 行 4 测试：验证 4 个典型 DiagnosisCode 的模板
是否按预期构造 DiagnosisInfo（reason 中文关键字 / suggestion 语义 /
context 参数注入）。
"""
from sw_preflight.diagnosis import DiagnosisCode


def test_make_diagnosis_for_sw_not_installed():
    from sw_preflight.matrix import make_diagnosis
    d = make_diagnosis(DiagnosisCode.SW_NOT_INSTALLED)
    assert '未检测到' in d.reason
    assert d.severity == 'block'


def test_make_diagnosis_license_problem_suggests_open_sw_gui():
    from sw_preflight.matrix import make_diagnosis
    d = make_diagnosis(DiagnosisCode.LICENSE_PROBLEM)
    assert '双击桌面 SOLIDWORKS 图标' in d.suggestion or '打开 SOLIDWORKS' in d.suggestion


def test_make_diagnosis_unc_path_not_accessible():
    from sw_preflight.matrix import make_diagnosis
    d = make_diagnosis(DiagnosisCode.TOOLBOX_PATH_NOT_ACCESSIBLE,
                       context={'path': r'\\fileserver\Toolbox'})
    assert 'fileserver' in d.reason


def test_make_diagnosis_multiple_versions_ambiguous():
    from sw_preflight.matrix import make_diagnosis
    d = make_diagnosis(DiagnosisCode.MULTIPLE_SW_VERSIONS_AMBIGUOUS,
                       context={'versions': [2022, 2024]})
    assert '2022' in d.reason and '2024' in d.reason
