"""Task 1 — 验证 sw_preflight 包可导入"""


def test_sw_preflight_package_importable():
    import sw_preflight
    assert sw_preflight is not None
