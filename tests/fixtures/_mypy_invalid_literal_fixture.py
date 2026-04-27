"""T17 (spec §4.7) mypy CI gate 反例 fixture。

故意类型错的代码片段，让 mypy --platform=win32 --strict 必 fail。
本文件不被 pytest collect（无 test_ prefix），仅作 mypy subprocess 输入。

如果未来 mypy CI gate 配置漂移（如 strict=false），mypy 不再报错此文件，
T17 测试就 fail，提示 reviewer 修复 gate 配置。
"""

from adapters.solidworks.sw_config_broker import (
    InvalidationReason,
    _move_decision_to_history,
)


def _trigger_mypy_error() -> None:
    """故意调用 _move_decision_to_history 传入未定义在 InvalidationReason
    Literal 中的字面量，mypy strict 必 fail。
    """
    envelope: dict[str, object] = {"decisions_by_subsystem": {}, "decisions_history": []}
    # type: ignore 故意不加——让 mypy 必报 type error
    _move_decision_to_history(
        envelope,
        "test_subsystem",
        "TEST-001",
        "bom_change_legacy",  # ← 不在 InvalidationReason Literal 之内，mypy 必 fail
    )


# 第二处类型错：把 InvalidationReason 当 str 传给非 Literal 函数返回类型
def _another_type_error() -> InvalidationReason:
    return "arbitrary_string"  # ← mypy 必 fail：str 非 Literal[3 个具体字面量]
