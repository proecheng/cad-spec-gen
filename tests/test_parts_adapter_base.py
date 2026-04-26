"""PartsAdapter.prewarm() virtual method 默认 no-op 测试（Task 14.6 / Task 9）。"""

from __future__ import annotations


def test_base_class_has_prewarm_method():
    from adapters.parts.base import PartsAdapter

    assert hasattr(PartsAdapter, "prewarm")


def test_default_prewarm_is_no_op():
    """base 给 default no-op body：现有 4 adapter 不需要 override 也能跑。"""
    from adapters.parts.jinja_primitive_adapter import JinjaPrimitiveAdapter

    a = JinjaPrimitiveAdapter()
    # 不抛 + 返 None
    result = a.prewarm([])
    assert result is None
    result = a.prewarm([("fake_query", {"some": "spec"})])
    assert result is None


def test_prewarm_is_not_abstractmethod():
    """prewarm 不是 abstractmethod；新 adapter 无需实现也可继承 PartsAdapter。"""
    from adapters.parts.base import PartsAdapter

    method = PartsAdapter.prewarm
    abstract = getattr(method, "__isabstractmethod__", False)
    assert abstract is False
