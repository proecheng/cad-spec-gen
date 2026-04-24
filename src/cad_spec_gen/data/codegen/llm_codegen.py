"""LLM 辅助几何生成：L1 参数提取 / L2 CadQuery 代码生成 / L2 自我修正。

依赖：GEMINI_API_KEY 环境变量（text-only，不走 gemini_image_config.json）。
所有公开函数失败时返回 None，不抛异常。
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

_GEMINI_TEXT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)
_TIMEOUT_L1 = 10   # L1 参数提取超时秒数
_TIMEOUT_L2 = 30   # L2 代码生成超时秒数


def _call_gemini_text(prompt: str, timeout: int = 10) -> str | None:
    """向 Gemini 2.0 Flash 发送纯文本请求，返回模型第一条文本回复；失败返回 None。"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("GEMINI_API_KEY 未设置，跳过 LLM 调用")
        return None
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }).encode()
    url = f"{_GEMINI_TEXT_URL}?key={api_key}"
    req = urllib.request.Request(url, data=payload, method="POST",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        log.warning("Gemini text call failed: %s", exc)
        return None


# ── L1: 参数提取 ─────────────────────────────────────────────────────────────

_L1_PROMPT_TEMPLATE = """\
你是 CAD 参数提取助手。从以下零件描述中提取指定尺寸参数。

零件名称：{part_name}
模板类型：{template_name}
描述文本：
{spec_text}

需要提取的参数键（已存在的键已列出，只需提取缺失的）：
{missing_keys}

已存在参数（不要修改这些）：
{existing_json}

请严格按以下 JSON 格式输出，不含任何说明文字、Markdown 代码块或注释：
[{{"name": "KEY_NAME", "nominal": "数值"}}, ...]

只输出缺失键的提取结果。若某键在描述中找不到数值，忽略它（不输出）。
"""


def _llm_extract_params(
    part_name: str,
    spec_text: str,
    template_name: str,
    required_tol_keys: list[str],
    existing_dim_tols: list[dict],
) -> list[dict] | None:
    """从 spec_text 补全 dim_tolerances 中缺失的参数条目。

    返回合并后的完整 dim_tolerances 列表（已有 + 新提取）；
    解析失败返回 None，不抛异常。
    """
    existing_names = {d["name"] for d in existing_dim_tols}
    missing = [k for k in required_tol_keys if k not in existing_names]
    if not missing:
        return list(existing_dim_tols)  # 全部已有，不调 LLM

    prompt = _L1_PROMPT_TEMPLATE.format(
        part_name=part_name,
        template_name=template_name,
        spec_text=spec_text[:2000],  # 截断避免超长
        missing_keys=", ".join(missing),
        existing_json=json.dumps(existing_dim_tols, ensure_ascii=False),
    )
    raw = _call_gemini_text(prompt, timeout=_TIMEOUT_L1)
    if raw is None:
        return None

    # 提取 JSON 数组（去掉可能包裹的 ```json ... ``` 或多余文字）
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        log.warning("L1: LLM 返回无法解析为 JSON 数组: %s", raw[:200])
        return None
    try:
        new_entries: list[dict] = json.loads(match.group())
    except json.JSONDecodeError as exc:
        log.warning("L1: JSON 解析失败: %s", exc)
        return None

    # 过滤掉已有键（LLM 有时会重复输出）
    merged = list(existing_dim_tols)
    for entry in new_entries:
        if isinstance(entry, dict) and "name" in entry and "nominal" in entry:
            if entry["name"] not in existing_names:
                merged.append(entry)
    return merged
