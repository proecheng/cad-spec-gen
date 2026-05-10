"""jury_loop 包测试公共 fixture。"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

import pytest

from tools.jury.config import JuryProfile
from tools.jury.verdict import ViewVerdict
from tools.jury_loop.backends import BACKEND_REGISTRY, register_backend


@pytest.fixture
def fixture_dir() -> Path:
    """测试 fixtures 目录。"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_reason_plastic_flat() -> str:
    """jury reason 含 plastic_look + flat_light 两 tag。"""
    return "plastic look, flat lighting"


@pytest.fixture
def builtin_yaml_path() -> Path:
    """内置 photoreal_v1.yaml 路径。"""
    from importlib.resources import files

    return Path(str(files("tools.jury_loop.rules") / "photoreal_v1.yaml"))


# 以下为 CP-5 orchestrator 测试用 fixture（Task 5.1.3）


@pytest.fixture
def fake_view_verdict():
    """ViewVerdict factory（对齐 tools/jury/verdict.py 真签名 6 字段）。

    用法：
        verdict = fake_view_verdict()                  # 默认低分 + plastic look
        verdict = fake_view_verdict(score=80)          # 高分
        verdict = fake_view_verdict(reason="")         # empty reason 测试用
    """

    def _make(
        score: int = 58,
        reason: str = "plastic look, flat lighting",
        verdict: str = "accepted",
        parse_anomalies: list[str] | None = None,
        semantic_checks: dict[str, bool] | None = None,
    ) -> ViewVerdict:
        return ViewVerdict(
            semantic_checks=semantic_checks
            or {
                "geometry_preserved": True,
                "material_consistent": True,
                "photorealistic": False,
                "no_extra_parts": True,
                "no_missing_parts": True,
            },
            photoreal_score=score,
            reason=reason,
            parse_status="ok",
            parse_anomalies=parse_anomalies or [],
            # ViewVerdict.verdict 是 Literal["accepted", "preview", "needs_review"]，
            # factory 入参为通用 str 便于测试调用，mypy 严格无法窄化 → 在此豁免。
            verdict=verdict,  # type: ignore[arg-type]
        )

    return _make


@pytest.fixture
def fake_jury_sequence(fake_view_verdict):
    """Stateful jury 工厂：把 (score, reason) tuple list 变 lambda 让连续调用按序返。

    用法（测试 #13/#14）：
        next_verdict = fake_jury_sequence([(58, "plastic"), (80, "metallic")])
        monkeypatch.setattr(orchestrator, "_call_jury_subprocess",
                             lambda *a, **kw: (next_verdict(), None))
    """

    def _make(items: Iterable[tuple[int, str]]):
        verdicts = iter([fake_view_verdict(score=s, reason=r) for s, r in items])
        return lambda: next(verdicts)

    return _make


@pytest.fixture
def isolated_backend_registry() -> Iterator[dict]:
    """对齐既有 test_backend_protocol.py:isolated_registry — snapshot/restore 模式。

    防 pytest-xdist 并发同时 register_backend("test_stub") 的 ValueError；
    yield 后整体 restore（不仅 pop 增量）。
    """
    snapshot = dict(BACKEND_REGISTRY)
    yield BACKEND_REGISTRY
    BACKEND_REGISTRY.clear()
    BACKEND_REGISTRY.update(snapshot)


@pytest.fixture
def fake_backend_adapter(isolated_backend_registry):
    """注册 _FakeAdapter 到 BACKEND_REGISTRY 的 context manager。

    用法：
        with fake_backend_adapter(call_returns=BackendResponse(...)) as kind:
            run_loop_if_eligible(backend_kind=kind, ...)

    默认 kind="test_stub" 防与内置 fal_comfy / openai_images_edit 等撞名。
    """

    @contextmanager
    def _register(
        kind: str = "test_stub",
        call_returns=None,
        raises: BaseException | None = None,
        estimate_cost_usd: float = 0.05,
    ):
        class _FakeAdapter:
            @property
            def kind(self) -> str:
                return kind

            @property
            def known_params(self) -> dict[str, tuple[float | None, float | None]]:
                return {}

            def supports_controlnet(self) -> bool:
                return False

            def estimate_cost_usd(self, request) -> float:  # noqa: ARG002
                return estimate_cost_usd

            def call(self, request, timeout):  # noqa: ARG002
                if raises is not None:
                    raise raises
                return call_returns

        BACKEND_REGISTRY.pop(kind, None)
        register_backend(_FakeAdapter())
        yield kind

    return _register


@pytest.fixture
def fake_render_dir(tmp_path):
    """造一个含 V1_enhanced_baseline.jpg 的临时 render_dir。"""
    rd = tmp_path / "render"
    rd.mkdir()
    # 假 PNG 头（仅 ASCII 字节，bytes 字面量限制；用于测试不解码不渲染只看路径存在）
    (rd / "V1_enhanced_baseline.jpg").write_bytes(b"\x89PNG\r\n\x1a\n")
    return rd


@pytest.fixture
def tiny_jury_profile() -> JuryProfile:
    """JuryProfile factory（fake LLM endpoint，测试用）。"""
    return JuryProfile(
        id="test",
        kind="openai_compat",
        api_base_url="https://example.test/v1",
        api_key="sk-fake-test-key",
        model="gemini-2.5-flash",
        cost_per_call_usd=0.005,
    )


@pytest.fixture
def tiny_loop_config():
    """JuryLoopConfig factory（字段对齐 plan Task 5.0 真 schema）。"""

    def _make(
        *,
        enabled: bool = True,
        cost_cap_usd: float = 1.5,
        backend_kind: str = "test_stub",
        threshold: int = 75,
        llm_fallback: bool = False,
        score_select_strategy: str = "pick_max_jury",
        max_retries: int = 1,
        rule_table_path: Path | None = None,
    ):
        from tools.jury_loop.config import BackendConfig, JuryLoopConfig

        return JuryLoopConfig(
            enabled=enabled,
            cost_cap_usd=cost_cap_usd,
            backend=BackendConfig(
                kind=backend_kind,
                base_url="https://example.test",
                api_key_env="TEST_API_KEY",
                model_name="test-model",
                timeout_s=60,
            ),
            advanced={
                "threshold": threshold,
                "max_retries": max_retries,
                "llm_fallback": llm_fallback,
                "rule_table_path": rule_table_path,
                "score_select_strategy": score_select_strategy,
            },
        )

    return _make


@pytest.fixture
def user_yaml_with_tag_no_rule(tmp_path) -> Path:
    """测试 #8 专用：用户 yaml 扩 tag_dictionary 但不加 rule。"""
    p = tmp_path / "user_rules.yaml"
    p.write_text(
        "schema_version: 1\n"
        "tag_dictionary:\n"
        "  unknown_aesthetic_tag:\n"
        "    patterns:\n"
        '      - "weird vibe"\n'
        '      - "off feeling"\n'
        "rules: []\n",
        encoding="utf-8",
    )
    return p
