"""Task 2.5.4：comfyui_workflow_cloud adapter 单元测试。

双路径覆盖：
- fal.ai 路径：mock cad_spec_gen.data.python_tools.fal_comfy_enhancer.enhance_image
- generic 路径（RunComfy / 自部署）：mock urlopen，验证上传 workflow JSON
"""
from __future__ import annotations

import base64
import io
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from tools.jury_loop.backends.comfyui_workflow_cloud import (
    ComfyUIWorkflowCloudAdapter,
)
from tools.jury_loop.backends.protocol import (
    BackendAdapter,
    BackendAuthError,
    BackendCallError,
    BackendQuotaExceededError,
    BackendRateLimitError,
    BackendRequest,
)


@pytest.fixture
def adapter() -> ComfyUIWorkflowCloudAdapter:
    return ComfyUIWorkflowCloudAdapter()


@pytest.fixture
def png_input(tmp_path: Path) -> Path:
    p = tmp_path / "V1_baseline.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n_input_bytes_")
    return p


def _make_request(
    png: Path,
    *,
    base_url: str = "https://queue.fal.run/fal-ai/comfy",
    api_key: str = "fal-key",
    model_name: str = "comfy-default",
    params: dict[str, Any] | None = None,
) -> BackendRequest:
    return BackendRequest(
        input_image_path=png,
        prompt="enhance",
        params=params or {"denoise_strength": 0.6, "canny_strength": 0.5},
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
    )


def _fake_b64() -> str:
    return base64.b64encode(b"\x89PNG\r\n\x1a\n_output_bytes_").decode("ascii")


@contextmanager
def _fake_urlopen_ok(response_dict: dict[str, Any], status: int = 200):
    body = json.dumps(response_dict).encode("utf-8")

    class _R:
        def __init__(self) -> None:
            self.status = status
            self.headers: dict[str, str] = {}

        def read(self) -> bytes:
            return body

        def __enter__(self) -> "_R":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    yield _R()


def _http_error_factory(status: int, body: str = ""):
    fp = io.BytesIO(body.encode("utf-8")) if body else None
    return HTTPError(
        url="https://comfy.example.com",
        code=status,
        msg=f"HTTP {status}",
        hdrs={},  # type: ignore[arg-type]
        fp=fp,
    )


# ============ Protocol ============


def test_implements_protocol(adapter: ComfyUIWorkflowCloudAdapter) -> None:
    assert isinstance(adapter, BackendAdapter)


def test_kind(adapter: ComfyUIWorkflowCloudAdapter) -> None:
    assert adapter.kind == "comfyui_workflow_cloud"


def test_supports_controlnet_true(
    adapter: ComfyUIWorkflowCloudAdapter,
) -> None:
    """关键差异：comfyui_workflow_cloud 是 SP1 唯一支持 ControlNet 的内置 adapter。"""
    assert adapter.supports_controlnet() is True


def test_known_params_includes_controlnet_keys(
    adapter: ComfyUIWorkflowCloudAdapter,
) -> None:
    """plan line 1089：known_params 含 ControlNet 参数 (canny_strength / depth_strength)。"""
    kp = adapter.known_params
    assert "canny_strength" in kp
    assert kp["canny_strength"] == (0.0, 1.0)
    assert "depth_strength" in kp
    assert kp["depth_strength"] == (0.0, 1.0)
    assert "canny_end_pct" in kp
    assert kp["denoise_strength"] == (0.0, 1.0)
    assert kp["cfg_scale"] == (1.0, 30.0)
    assert kp["steps"] == (1, 200)
    assert kp["guidance_scale"] == (1.0, 30.0)


def test_estimate_cost_usd_fixed(
    adapter: ComfyUIWorkflowCloudAdapter, png_input: Path
) -> None:
    """plan line 1081：default fal.ai 价 0.18 USD。"""
    req = _make_request(png_input)
    assert adapter.estimate_cost_usd(req) == 0.18


# ============ fal.ai 路径 ============


def test_call_fal_ai_invokes_enhance_image(
    adapter: ComfyUIWorkflowCloudAdapter,
    png_input: Path,
    tmp_path: Path,
) -> None:
    """plan line 1086：default base_url (fal.ai) 走入 enhance_image()。"""
    req = _make_request(png_input)
    fake_result = tmp_path / "fal_tmp_result.png"
    fake_result.write_bytes(b"\x89PNG\r\n\x1a\n_fal_output_")

    captured: dict[str, Any] = {}

    def _fake_enhance_image(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return str(fake_result)

    with patch(
        "cad_spec_gen.data.python_tools.fal_comfy_enhancer.enhance_image",
        side_effect=_fake_enhance_image,
        create=True,
    ):
        resp = adapter.call(req, timeout=30.0)

    assert captured["png_path"] == str(png_input)
    assert captured["prompt"] == "enhance"
    assert captured["view_key"] == "retry"
    # fal_comfy_cfg 应包含来自 params 的 known_params 子集
    fcc = captured["fal_comfy_cfg"]
    assert fcc["endpoint"] == "fal-ai/comfy"
    assert fcc["denoise_strength"] == 0.6
    assert fcc["canny_strength"] == 0.5
    # 输出文件已 move 到 input 同级 retry 路径
    assert resp.output_image_path.exists()
    assert resp.output_image_path == png_input.parent / "V1_baseline_retry.png"
    assert not fake_result.exists()  # 已 move
    assert resp.raw_request_summary["vendor"] == "fal.ai"


def test_call_fal_ai_runtime_401(
    adapter: ComfyUIWorkflowCloudAdapter, png_input: Path
) -> None:
    """fal_comfy_enhancer 抛 RuntimeError "401 unauthorized" → BackendAuthError。"""
    req = _make_request(png_input)
    with patch(
        "cad_spec_gen.data.python_tools.fal_comfy_enhancer.enhance_image",
        side_effect=RuntimeError("HTTP 401 unauthorized: invalid_api_key"),
        create=True,
    ):
        with pytest.raises(BackendAuthError):
            adapter.call(req, timeout=30.0)


def test_call_fal_ai_runtime_429(
    adapter: ComfyUIWorkflowCloudAdapter, png_input: Path
) -> None:
    """fal_comfy_enhancer 抛含 '429 rate limit' → BackendRateLimitError。"""
    req = _make_request(png_input)
    with patch(
        "cad_spec_gen.data.python_tools.fal_comfy_enhancer.enhance_image",
        side_effect=RuntimeError("Got 429 rate limit hit"),
        create=True,
    ):
        with pytest.raises(BackendRateLimitError):
            adapter.call(req, timeout=30.0)


def test_call_fal_ai_runtime_quota(
    adapter: ComfyUIWorkflowCloudAdapter, png_input: Path
) -> None:
    """RuntimeError 含 'insufficient_quota' → BackendQuotaExceededError。"""
    req = _make_request(png_input)
    with patch(
        "cad_spec_gen.data.python_tools.fal_comfy_enhancer.enhance_image",
        side_effect=RuntimeError("error: insufficient_quota balance=0"),
        create=True,
    ):
        with pytest.raises(BackendQuotaExceededError):
            adapter.call(req, timeout=30.0)


def test_call_fal_ai_runtime_other_call_error(
    adapter: ComfyUIWorkflowCloudAdapter, png_input: Path
) -> None:
    """未匹配关键字的 RuntimeError → BackendCallError 兜底。"""
    req = _make_request(png_input)
    with patch(
        "cad_spec_gen.data.python_tools.fal_comfy_enhancer.enhance_image",
        side_effect=RuntimeError("Connection reset by peer"),
        create=True,
    ):
        with pytest.raises(BackendCallError):
            adapter.call(req, timeout=30.0)


# ============ generic 路径 ============


def test_call_generic_uploads_workflow_json(
    adapter: ComfyUIWorkflowCloudAdapter, png_input: Path
) -> None:
    """plan line 1087：切自定义 base_url 仍以 ComfyUI workflow JSON 形式上传。"""
    base_url = "https://api.runcomfy.com/v1/run"
    req = _make_request(png_input, base_url=base_url)
    response = {"image_b64": _fake_b64()}
    captured: dict[str, Any] = {}

    def _capture(request, timeout=None):  # type: ignore[no-untyped-def]
        captured["url"] = request.full_url
        captured["body"] = request.data
        captured["headers"] = dict(request.headers)
        return _fake_urlopen_ok(response).__enter__()

    with patch(
        "tools.jury_loop.backends.comfyui_workflow_cloud.urlopen",
        side_effect=_capture,
    ):
        adapter.call(req, timeout=30.0)

    assert captured["url"] == base_url
    body_dict = json.loads(captured["body"].decode("utf-8"))
    # workflow + input_image_b64 + model_name 三必备字段
    assert "workflow" in body_dict
    assert isinstance(body_dict["workflow"], dict)
    assert body_dict["workflow"]["positive_prompt"] == "enhance"
    assert "input_image_b64" in body_dict
    assert body_dict["model_name"] == "comfy-default"
    # ControlNet 参数透传到 workflow.params
    assert body_dict["workflow"]["params"]["canny_strength"] == 0.5


def test_call_generic_b64_response_writes_file(
    adapter: ComfyUIWorkflowCloudAdapter, png_input: Path
) -> None:
    req = _make_request(png_input, base_url="https://api.runcomfy.com/v1/run")
    response = {"image_b64": _fake_b64()}

    with patch(
        "tools.jury_loop.backends.comfyui_workflow_cloud.urlopen",
        return_value=_fake_urlopen_ok(response),
    ):
        resp = adapter.call(req, timeout=30.0)

    assert resp.output_image_path.exists()
    assert resp.output_image_path.read_bytes().startswith(b"\x89PNG")
    assert resp.raw_request_summary["vendor"] == "generic"


def test_call_generic_url_response_downloads(
    adapter: ComfyUIWorkflowCloudAdapter, png_input: Path
) -> None:
    """response.image_url → 第二次 urlopen GET 下载。"""
    req = _make_request(png_input, base_url="https://api.runcomfy.com/v1/run")
    download_url = "https://cdn.runcomfy.com/results/abc.png"
    response_post = {"image_url": download_url}

    @contextmanager
    def _fake_get():
        class _R:
            status = 200

            def read(self) -> bytes:
                return b"\x89PNG\r\n\x1a\n_downloaded_"

            def __enter__(self) -> "_R":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        yield _R()

    call_count = {"n": 0}

    def _urlopen_side(request, timeout=None):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _fake_urlopen_ok(response_post).__enter__()
        assert request.full_url == download_url
        return _fake_get().__enter__()

    with patch(
        "tools.jury_loop.backends.comfyui_workflow_cloud.urlopen",
        side_effect=_urlopen_side,
    ):
        resp = adapter.call(req, timeout=30.0)

    assert resp.output_image_path.exists()
    assert call_count["n"] == 2


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, '{"error": "unauthorized"}', BackendAuthError),
        (403, '{"error": "forbidden"}', BackendAuthError),
        (402, '{"error": "billing"}', BackendQuotaExceededError),
        (429, '{"error": "rate"}', BackendRateLimitError),
        (429, '{"error": "insufficient_quota"}', BackendQuotaExceededError),
        (500, '{"error": "internal"}', BackendCallError),
    ],
)
def test_call_generic_http_errors(
    adapter: ComfyUIWorkflowCloudAdapter,
    png_input: Path,
    status: int,
    body: str,
    expected: type[Exception],
) -> None:
    req = _make_request(png_input, base_url="https://api.runcomfy.com/v1/run")
    with patch(
        "tools.jury_loop.backends.comfyui_workflow_cloud.urlopen",
        side_effect=_http_error_factory(status, body),
    ):
        with pytest.raises(expected):
            adapter.call(req, timeout=30.0)


def test_call_generic_url_error_call_error(
    adapter: ComfyUIWorkflowCloudAdapter, png_input: Path
) -> None:
    req = _make_request(png_input, base_url="https://api.runcomfy.com/v1/run")
    with patch(
        "tools.jury_loop.backends.comfyui_workflow_cloud.urlopen",
        side_effect=URLError("dns failed"),
    ):
        with pytest.raises(BackendCallError):
            adapter.call(req, timeout=30.0)


def test_call_generic_no_image_in_response(
    adapter: ComfyUIWorkflowCloudAdapter, png_input: Path
) -> None:
    req = _make_request(png_input, base_url="https://api.runcomfy.com/v1/run")
    response: dict[str, Any] = {"status": "done"}
    with patch(
        "tools.jury_loop.backends.comfyui_workflow_cloud.urlopen",
        return_value=_fake_urlopen_ok(response),
    ):
        with pytest.raises(BackendCallError, match="image_b64"):
            adapter.call(req, timeout=30.0)


# ============ vendor detection ============


@pytest.mark.parametrize(
    ("base_url", "is_fal"),
    [
        ("https://queue.fal.run/fal-ai/comfy", True),
        ("https://api.fal.ai/anything", True),
        ("https://api.runcomfy.com/v1/run", False),
        ("https://localhost:8188/prompt", False),
    ],
)
def test_vendor_detection(
    adapter: ComfyUIWorkflowCloudAdapter,
    png_input: Path,
    base_url: str,
    is_fal: bool,
    tmp_path: Path,
) -> None:
    """base_url 子串识别 fal.ai；其他走 generic 路径。"""
    req = _make_request(png_input, base_url=base_url)
    fake_result = tmp_path / "fal_tmp.png"
    fake_result.write_bytes(b"\x89PNG\r\n\x1a\n_x_")

    response = {"image_b64": _fake_b64()}

    if is_fal:
        with patch(
            "cad_spec_gen.data.python_tools.fal_comfy_enhancer.enhance_image",
            return_value=str(fake_result),
            create=True,
        ):
            resp = adapter.call(req, timeout=30.0)
        assert resp.raw_request_summary["vendor"] == "fal.ai"
    else:
        with patch(
            "tools.jury_loop.backends.comfyui_workflow_cloud.urlopen",
            return_value=_fake_urlopen_ok(response),
        ):
            resp = adapter.call(req, timeout=30.0)
        assert resp.raw_request_summary["vendor"] == "generic"


# ============ Registry 集成（Task 2.5.1 推迟到 2.5.4 末尾） ============


def test_all_three_builtin_adapters_registered() -> None:
    """Task 2.5.1 plan line 1021：BACKEND_REGISTRY 启动时含 3 个内置 key。

    本测试在 Task 2.5.4 落地后才能通过（前面三 adapter 模块全到位）。
    """
    from tools.jury_loop.backends import BACKEND_REGISTRY

    assert "gemini_chat_image" in BACKEND_REGISTRY
    assert "openai_images_edit" in BACKEND_REGISTRY
    assert "comfyui_workflow_cloud" in BACKEND_REGISTRY

    # 每个 entry 实现 BackendAdapter Protocol
    for kind, adapter_inst in BACKEND_REGISTRY.items():
        assert adapter_inst.kind == kind
        assert isinstance(adapter_inst, BackendAdapter)
