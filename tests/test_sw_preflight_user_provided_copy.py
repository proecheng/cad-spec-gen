"""Task 23 — copy_to_user_provided 按 PartCategory 分流复制测试"""
from sw_preflight.types import PartCategory
from pathlib import Path


def test_copy_default_category_falls_to_custom(tmp_path, monkeypatch):
    """省略 category 参数 → 默认 CUSTOM → 走 std_parts/custom/

    守护 prompt_user_provided 里 copy_to_user_provided(path, row) 只传 2 参的调用点——
    没有 category 上下文时按保守默认归档到 custom/，不抛 TypeError。
    """
    monkeypatch.chdir(tmp_path)
    src = tmp_path / 'no_category.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import copy_to_user_provided
    dest = copy_to_user_provided(src, {'name_cn': '未知件'})  # 2 参调用
    assert dest.exists()
    assert 'std_parts/custom' in str(dest).replace('\\', '/')


def test_copy_standard_to_user_provided_standard(tmp_path, monkeypatch):
    """STANDARD_FASTENER → ./std_parts/user_provided/standard/"""
    monkeypatch.chdir(tmp_path)
    src = tmp_path / 'm3x8.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import copy_to_user_provided
    row = {'name_cn': 'GB/T 70.1 M3×8'}
    dest = copy_to_user_provided(src, row, category=PartCategory.STANDARD_FASTENER)
    assert dest.exists()
    assert 'std_parts/user_provided/standard' in str(dest).replace('\\', '/')


def test_copy_vendor_to_user_provided_vendor(tmp_path, monkeypatch):
    """VENDOR_PURCHASED → ./std_parts/user_provided/vendor/"""
    monkeypatch.chdir(tmp_path)
    src = tmp_path / 'lemo.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import copy_to_user_provided
    row = {'name_cn': 'LEMO FGG.0B.302'}
    dest = copy_to_user_provided(src, row, category=PartCategory.VENDOR_PURCHASED)
    assert 'std_parts/user_provided/vendor' in str(dest).replace('\\', '/')


def test_copy_custom_to_std_parts_custom(tmp_path, monkeypatch):
    """CUSTOM → ./std_parts/custom/"""
    monkeypatch.chdir(tmp_path)
    src = tmp_path / 'pxy.step'
    src.write_bytes(b'ISO-10303\n' + b'\n' * 20000)
    from sw_preflight.user_provided import copy_to_user_provided
    row = {'name_cn': '私有件 PXY-2024-A'}
    dest = copy_to_user_provided(src, row, category=PartCategory.CUSTOM)
    assert 'std_parts/custom' in str(dest).replace('\\', '/')
