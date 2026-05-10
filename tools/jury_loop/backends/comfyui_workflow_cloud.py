"""comfyui_workflow_cloud adapter — vendor-中性 ComfyUI workflow cloud。

按 spec §2.1 + plan line 1070-1091：base_url 决定 vendor，default fal.ai
（包装 fal_comfy_enhancer.enhance_image()），自定义 endpoint 走通用 POST
ComfyUI workflow JSON 路径（适用 RunComfy / 自部署 / 任意 ComfyUI 兼容）。

supports_controlnet=True 是与 gemini/openai 关键差异：rule_table 在此可注入
canny_strength / depth_strength 等 ControlNet 参数。
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .protocol import (
    BackendAuthError,
    BackendCallError,
    BackendQuotaExceededError,
    BackendRateLimitError,
    BackendRequest,
    BackendResponse,
)

_KNOWN_PARAMS: dict[str, tuple[float | None, float | None]] = {
    "denoise_strength": (0.0, 1.0),
    "cfg_scale": (1.0, 30.0),
    "canny_strength": (0.0, 1.0),
    "canny_end_pct": (0.0, 1.0),
    "depth_strength": (0.0, 1.0),
    "steps": (1, 200),
    "guidance_scale": (1.0, 30.0),
}

_FIXED_COST_USD = 0.18  # fal.ai 默认价；plugin 阶段用户可派生子类覆写


def _is_fal_ai(base_url: str) -> bool:
    """fal.ai endpoint 检测：base_url 含 fal.run / fal.ai 子串。"""
    bl = base_url.lower()
    return "fal.run" in bl or "fal.ai" in bl


def _build_workflow_payload(request: BackendRequest) -> dict[str, Any]:
    """构造通用 ComfyUI workflow payload（generic vendor 路径）。

    合约：POST {base_url} body = {"workflow": ..., "input_image_b64": ..., "model_name": ...}
          response {"image_b64": ...} 或 {"image_url": ...}
    """
    return {
        "positive_prompt": request.prompt,
        "negative_prompt": "",
        "model": request.model_name,
        "params": dict(request.params),
    }


def _classify_http_error(status: int, body_text: str) -> Exception:
    """与 openai_images_edit 顺序对齐：body 关键字优先于 429。"""
    body_lower = body_text.lower()
    if status in (401, 403):
        return BackendAuthError(f"HTTP {status}: 认证失败")
    if status == 402:
        return BackendQuotaExceededError(f"HTTP 402: 余额不足（{body_text[:200]}）")
    if (
        "quota" in body_lower
        or "billing" in body_lower
        or "insufficient" in body_lower
    ):
        return BackendQuotaExceededError(
            f"HTTP {status}: quota/billing 关键字命中（{body_text[:200]}）"
        )
    if status == 429:
        return BackendRateLimitError(f"HTTP 429: rate limited（{body_text[:200]}）")
    return BackendCallError(f"HTTP {status}: {body_text[:200]}")


def _classify_runtime_message(msg: str) -> Exception:
    """从 fal_comfy_enhancer 抛的 RuntimeError 文本中提取分类。

    fal_client 不直接暴露 status code 给 enhance_image()，需从消息里 substring 抠。
    """
    lower = msg.lower()
    if "401" in msg or "unauthorized" in lower or "invalid_api_key" in lower:
        return BackendAuthError(f"fal.ai 认证失败：{msg[:200]}")
    if "429" in msg or "rate limit" in lower or "rate_limit" in lower:
        return BackendRateLimitError(f"fal.ai rate limited：{msg[:200]}")
    if "402" in msg or "quota" in lower or "billing" in lower or "insufficient" in lower:
        return BackendQuotaExceededError(f"fal.ai 余额不足：{msg[:200]}")
    return BackendCallError(f"fal.ai 调用失败：{msg[:200]}")


def _download_image(url: str, timeout: float) -> bytes:
    """下载远程 URL 二进制；失败抛 BackendCallError。"""
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()  # type: ignore[no-any-return]
    except (HTTPError, URLError, TimeoutError) as e:
        raise BackendCallError(f"下载生成图像失败：{type(e).__name__}") from None


class ComfyUIWorkflowCloudAdapter:
    """通用 ComfyUI workflow 云端 adapter（fal.ai default + custom endpoint）。"""

    @property
    def kind(self) -> str:
        return "comfyui_workflow_cloud"

    @property
    def known_params(
        self,
    ) -> dict[str, tuple[float | None, float | None]]:
        return dict(_KNOWN_PARAMS)

    def supports_controlnet(self) -> bool:
        return True

    def estimate_cost_usd(self, request: BackendRequest) -> float:
        return _FIXED_COST_USD

    def call(
        self, request: BackendRequest, timeout: float
    ) -> BackendResponse:
        if _is_fal_ai(request.base_url):
            return self._call_fal_ai(request, timeout)
        return self._call_generic(request, timeout)

    def _call_fal_ai(
        self, request: BackendRequest, timeout: float
    ) -> BackendResponse:
        """fal.ai 路径：lazy import enhance_image() 并调用。

        异常分类：fal_client 抛的 RuntimeError 文本子串 → 4 类异常。
        """
        try:
            from cad_spec_gen.data.python_tools.fal_comfy_enhancer import (
                enhance_image,
            )
        except ImportError as e:
            raise BackendCallError(
                f"fal_comfy_enhancer 不可用：{e}"
                "（请装 fal-client 或切 base_url 到自部署 ComfyUI）"
            ) from None

        # 仅传 known_params 里的字段；endpoint 用 fal.ai 默认
        fal_comfy_cfg: dict[str, Any] = {
            "endpoint": "fal-ai/comfy",
        }
        for k, v in request.params.items():
            if k in _KNOWN_PARAMS:
                fal_comfy_cfg[k] = v

        try:
            result_path = enhance_image(
                png_path=str(request.input_image_path),
                prompt=request.prompt,
                fal_comfy_cfg=fal_comfy_cfg,
                view_key="retry",
                rc={},
            )
        except RuntimeError as e:
            raise _classify_runtime_message(str(e)) from None
        except ImportError as e:
            raise BackendCallError(f"fal_client 缺失：{e}") from None

        # enhance_image 返 tmp_path；落到 input 同级 retry 文件
        out_path = (
            request.input_image_path.parent
            / f"{request.input_image_path.stem}_retry{request.input_image_path.suffix}"
        )
        Path(result_path).replace(out_path)

        return BackendResponse(
            output_image_path=out_path,
            actual_cost_usd=None,
            raw_request_summary={
                "kind": "comfyui_workflow_cloud",
                "vendor": "fal.ai",
                "endpoint": request.base_url,
                "params": dict(request.params),
            },
        )

    def _call_generic(
        self, request: BackendRequest, timeout: float
    ) -> BackendResponse:
        """通用 ComfyUI 兼容 endpoint 路径：上传 workflow JSON + base64 image。

        合约（与 RunComfy / 自部署 / 任何 ComfyUI 兼容 vendor 通用）：
          POST {base_url} {"workflow": ..., "input_image_b64": ..., "model_name": ...}
          → {"image_b64": ...} 或 {"image_url": ...}
        """
        image_b64 = base64.b64encode(
            request.input_image_path.read_bytes()
        ).decode("ascii")
        body_dict = {
            "workflow": _build_workflow_payload(request),
            "input_image_b64": image_b64,
            "model_name": request.model_name,
        }
        body = json.dumps(body_dict).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {request.api_key}",
            "Content-Type": "application/json",
        }
        req = Request(
            request.base_url, data=body, headers=headers, method="POST"
        )

        try:
            with urlopen(req, timeout=timeout) as resp:
                resp_body: bytes = resp.read()
                resp_status = int(resp.status)
        except HTTPError as e:
            err_body = ""
            try:
                err_body = (e.read() or b"").decode("utf-8", errors="replace")
            except Exception:
                err_body = ""
            raise _classify_http_error(e.code, err_body) from None
        except (URLError, TimeoutError) as e:
            raise BackendCallError(f"网络/超时错误：{type(e).__name__}") from None

        try:
            parsed = json.loads(resp_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise BackendCallError(f"响应解析失败：{e}") from None

        out_b64 = parsed.get("image_b64") or parsed.get("output_image_b64")
        if isinstance(out_b64, str) and out_b64:
            try:
                out_bytes = base64.b64decode(out_b64, validate=True)
            except (ValueError, base64.binascii.Error) as e:  # type: ignore[attr-defined]
                raise BackendCallError(f"base64 解码失败：{e}") from None
        elif isinstance(parsed.get("image_url"), str) and parsed.get("image_url"):
            out_bytes = _download_image(parsed["image_url"], timeout)
        else:
            raise BackendCallError(
                "响应无 image_b64 / image_url（ComfyUI 兼容 endpoint 应返其一）"
            )

        out_path = (
            request.input_image_path.parent
            / f"{request.input_image_path.stem}_retry{request.input_image_path.suffix}"
        )
        out_path.write_bytes(out_bytes)

        return BackendResponse(
            output_image_path=out_path,
            actual_cost_usd=None,
            raw_request_summary={
                "kind": "comfyui_workflow_cloud",
                "vendor": "generic",
                "endpoint": request.base_url,
                "params": dict(request.params),
                "http_status": resp_status,
            },
        )
