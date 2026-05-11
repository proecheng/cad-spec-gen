"""Task 2.5.1：BackendAdapter Protocol + Registry + 4 异常分类。

测试覆盖 plan line 1018-1022：
- BackendAdapter Protocol 用 runtime_checkable 装饰
- BackendRequest/Response NamedTuple 字段集
- BACKEND_REGISTRY 注册表与 register_backend 行为（重复 kind / 非 Protocol）
- 4 异常类继承 BackendError 基类
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.jury_loop.backends import (
    BACKEND_REGISTRY,
    register_backend,
)
from tools.jury_loop.backends.protocol import (
    BackendAdapter,
    BackendAuthError,
    BackendCallError,
    BackendError,
    BackendQuotaExceededError,
    BackendRateLimitError,
    BackendRequest,
    BackendResponse,
)


class _CompleteAdapter:
    """实现 BackendAdapter Protocol 全部 5 接口的 fake。"""

    def __init__(self, kind: str = "fake_complete") -> None:
        self._kind = kind

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def known_params(self) -> dict[str, tuple[float | None, float | None]]:
        return {"x": (0.0, 1.0)}

    def supports_controlnet(self) -> bool:
        return False

    def estimate_cost_usd(self, request: BackendRequest) -> float:
        return 0.01

    def call(self, request: BackendRequest, timeout: float) -> BackendResponse:
        return BackendResponse(
            output_image_path=Path("/tmp/out.jpg"),
            actual_cost_usd=0.01,
            raw_request_summary={"prompt": request.prompt},
        )


class _IncompleteAdapter:
    """缺 call() 方法的不合规 adapter。"""

    @property
    def kind(self) -> str:
        return "fake_incomplete"

    @property
    def known_params(self) -> dict[str, tuple[float | None, float | None]]:
        return {}

    def supports_controlnet(self) -> bool:
        return False

    def estimate_cost_usd(self, request: BackendRequest) -> float:
        return 0.0


@pytest.fixture
def isolated_registry():
    """每个测试拿独立 BACKEND_REGISTRY 视图：保存原始内容，测试后还原。"""
    snapshot = dict(BACKEND_REGISTRY)
    yield BACKEND_REGISTRY
    BACKEND_REGISTRY.clear()
    BACKEND_REGISTRY.update(snapshot)


# ============ Protocol shape ============


def test_backend_adapter_is_runtime_checkable() -> None:
    """Protocol 用 @runtime_checkable 装饰，isinstance 在运行时可工作。"""
    assert isinstance(_CompleteAdapter(), BackendAdapter)


def test_incomplete_adapter_not_protocol() -> None:
    """缺 call() 的实例不通过 Protocol isinstance 检查。"""
    assert not isinstance(_IncompleteAdapter(), BackendAdapter)


def test_backend_request_namedtuple_fields() -> None:
    """BackendRequest 6 字段与 spec §2.1 一致。"""
    req = BackendRequest(
        input_image_path=Path("/tmp/in.jpg"),
        prompt="test",
        params={"x": 0.5},
        base_url="https://api.example.com",
        api_key="key",
        model_name="model-1",
    )
    assert req.input_image_path == Path("/tmp/in.jpg")
    assert req.prompt == "test"
    assert req.params == {"x": 0.5}
    assert req.base_url == "https://api.example.com"
    assert req.api_key == "key"
    assert req.model_name == "model-1"


def test_backend_response_namedtuple_fields() -> None:
    """BackendResponse 3 字段与 spec §2.1 一致。"""
    resp = BackendResponse(
        output_image_path=Path("/tmp/out.jpg"),
        actual_cost_usd=0.04,
        raw_request_summary={"a": "b"},
    )
    assert resp.output_image_path == Path("/tmp/out.jpg")
    assert resp.actual_cost_usd == 0.04
    assert resp.raw_request_summary == {"a": "b"}


def test_backend_response_actual_cost_optional() -> None:
    """actual_cost_usd 可为 None：vendor 不返计费时由 LoopBudget 用 estimate。"""
    resp = BackendResponse(
        output_image_path=Path("/tmp/out.jpg"),
        actual_cost_usd=None,
        raw_request_summary={},
    )
    assert resp.actual_cost_usd is None


# ============ Exception hierarchy ============


@pytest.mark.parametrize(
    "exc_cls",
    [BackendAuthError, BackendRateLimitError, BackendQuotaExceededError, BackendCallError],
)
def test_backend_subclasses_inherit_base(exc_cls: type[BackendError]) -> None:
    """4 个分类异常都继承 BackendError，orchestrator 可只 catch 基类。"""
    assert isinstance(exc_cls("test"), BackendError)
    assert issubclass(exc_cls, BackendError)


def test_backend_error_subclasses_distinct() -> None:
    """4 个分类异常彼此独立（不互为父子）。"""
    classes = [
        BackendAuthError,
        BackendRateLimitError,
        BackendQuotaExceededError,
        BackendCallError,
    ]
    for c1 in classes:
        for c2 in classes:
            if c1 is c2:
                continue
            assert not issubclass(c1, c2), f"{c1.__name__} 不应是 {c2.__name__} 子类"


# ============ Registry ============


def test_register_backend_adds_to_registry(isolated_registry: dict) -> None:
    """register_backend(adapter) 用 adapter.kind 作 key 加入 BACKEND_REGISTRY。"""
    isolated_registry.clear()
    adapter = _CompleteAdapter(kind="my_test_kind")

    register_backend(adapter)

    assert "my_test_kind" in isolated_registry
    assert isolated_registry["my_test_kind"] is adapter


def test_register_backend_duplicate_kind_raises(isolated_registry: dict) -> None:
    """同 kind 重复注册抛 ValueError，防 plugin 误覆盖内置。"""
    isolated_registry.clear()
    register_backend(_CompleteAdapter(kind="dupkind"))

    with pytest.raises(ValueError, match="dupkind"):
        register_backend(_CompleteAdapter(kind="dupkind"))


def test_register_backend_rejects_non_protocol(isolated_registry: dict) -> None:
    """非 BackendAdapter 形实例抛 TypeError，防 plugin 写错偷偷过。"""
    isolated_registry.clear()

    with pytest.raises(TypeError, match="BackendAdapter"):
        register_backend(_IncompleteAdapter())  # type: ignore[arg-type]


def test_backend_registry_is_mutable_dict() -> None:
    """BACKEND_REGISTRY 是 dict[str, BackendAdapter]，便于 orchestrator/rule_table 直接索引。"""
    assert isinstance(BACKEND_REGISTRY, dict)
