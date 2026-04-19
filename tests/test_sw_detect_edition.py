"""Task 4: SwInfo.edition + reset_cache() 公开 API 测试。

RED 阶段：这两个测试在 SwInfo 加 edition 字段 +
模块级 reset_cache() 函数存在前必须失败。
"""

import pytest


def test_sw_info_has_edition_field():
    """SwInfo dataclass 必须声明 edition 字段（Task 4 新增）。"""
    from adapters.solidworks.sw_detect import SwInfo
    import dataclasses

    fields = {f.name for f in dataclasses.fields(SwInfo)}
    assert "edition" in fields


def test_reset_cache_clears_cached_info():
    """模块级 reset_cache() 公开 API 必须把 _cached_info 置回 None。"""
    from adapters.solidworks import sw_detect

    sw_detect.detect_solidworks()  # 充缓存
    sw_detect.reset_cache()
    # 重 detect 应该重新执行（不能从缓存返回）
    assert sw_detect._cached_info is None  # _cached_info 是模块级变量
