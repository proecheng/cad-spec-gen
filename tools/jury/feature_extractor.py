"""LLM 特征抽取（matches_spec 维度）：从 CAD_SPEC + design doc 拉关键特征列表。

Per spec D1/D7：每个 photo3d-jury 进程调 1 次；text-only endpoint 优先 + vision fallback；
LLM 失败 → fail-safe 返回空 features；超过 12 条截断。
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

_MAX_FEATURES = 12

# v2.37.1 fix：LLM 即使被 prompt 要求"不要 markdown"也常坚持包 ```json...```
# 围栏（gpt-image-2-pro / 等多模型实测）。脱栏后再 json.loads 兜底。
_MARKDOWN_FENCE_RE = re.compile(
    r"\A\s*```(?:json)?\s*(.*?)\s*```\s*\Z", re.DOTALL
)


def _strip_markdown_fence(raw: str) -> str:
    """脱 LLM 输出外层 markdown 代码围栏（如有）。无则原样返回。"""
    m = _MARKDOWN_FENCE_RE.match(raw)
    return m.group(1) if m else raw

# 单源截断窗口（按字符数），控 token：8k 字符 ≈ 4k token（中文 0.5 token/char 估算）。
_SOURCE_CHAR_LIMIT = 8000

_PROMPT_TEMPLATE = """\
你是一个 CAD/工业设计领域的特征抽取助手。任务：从下列设计文档片段提取**关键可见特征**，
让视觉 LLM 后续能据此对账渲染图。

要求：
- 仅抽对一张实物渲染图**肉眼能看见**的几何 / 装配 / 颜色 / 位置特征
- 不抽尺寸数字 / 公差 / 材质牌号 这种"看不见但能写出来"的元数据
- 最多 12 条；每条 1 行中文描述（≤40 字）
- 输出严格 JSON：{{"features": [{{"feature_id": "snake_case", "description_cn": "...", "expected_in_views": ["V4","V5"]或null, "doc_ref": "文件名:section/line"}}]}}
- expected_in_views = null 表示所有视角应可见；列表表特定视角应可见
- feature_id 使用 ASCII snake_case，<32 字符，唯一

--- CAD_SPEC.md 内容 ---
{spec_content}

--- 设计文档内容 ---
{design_content}

--- 输出 JSON ---
"""


def _read_source(path: pathlib.Path) -> tuple[str, str | None]:
    """读源文件，截前 _SOURCE_CHAR_LIMIT 字符；返回 (content, anomaly_or_none)。"""
    try:
        return path.read_text(encoding="utf-8")[:_SOURCE_CHAR_LIMIT], None
    except (OSError, UnicodeDecodeError):
        return "", f"{path.name}_unreadable"


def extract(
    spec_md_path: pathlib.Path,
    design_doc_path: pathlib.Path,
    *,
    cache_dir: pathlib.Path,
    llm_client: Any,
    subsystem: str,
    run_id: str,
) -> dict[str, Any]:
    """抽取特征列表并落盘 cache。

    Args:
        spec_md_path: CAD_SPEC.md 路径
        design_doc_path: 设计文档（如 04-末端执行机构设计.md）路径
        cache_dir: 缓存目录（matches_spec_features.json 写到此目录下）
        llm_client: 鸭子类型 LLM client，需有 `.complete(prompt: str) -> str`
        subsystem: 子系统名（如 end_effector），写进 cache payload
        run_id: 本次 run 标识，写进 cache payload

    Returns:
        {"features": [...], "parse_anomalies": [...]}（异常时 features=[] + anomalies 含 cause）

    Notes:
        Per spec D5：任何 LLM 故障 / 非 JSON / 非 list 一律 fail-safe 返空。
        Per spec D6：超过 _MAX_FEATURES (=12) 条截断 + 记 anomaly。
        Per spec §5.2.1：cache schema_version=1。
    """
    anomalies: list[str] = []

    # 读源文件（不存在或不可读 → 记 anomaly 但继续，让 LLM 在空 context 上自行决定）
    spec_content, spec_err = _read_source(spec_md_path)
    if spec_err is not None:
        anomalies.append("spec_md_unreadable")
    design_content, design_err = _read_source(design_doc_path)
    if design_err is not None:
        anomalies.append("design_doc_unreadable")

    # 调 LLM
    prompt = _PROMPT_TEMPLATE.format(
        spec_content=spec_content, design_content=design_content
    )
    # text endpoint 优先（spec F8）；vision/通用 complete fallback
    try:
        if hasattr(llm_client, "complete_text"):
            raw = llm_client.complete_text(prompt)
        else:
            raw = llm_client.complete(prompt)
    except Exception:  # noqa: BLE001 — spec D5 fail-safe：任何 LLM 故障兜底返空
        return {"features": [], "parse_anomalies": ["feature_extraction_failed"]}

    # parse JSON（v2.37.1：先脱可能的 markdown 围栏）
    try:
        payload = json.loads(_strip_markdown_fence(raw))
    except (json.JSONDecodeError, TypeError):
        return {"features": [], "parse_anomalies": ["feature_extraction_failed"]}

    if not isinstance(payload, dict):
        return {"features": [], "parse_anomalies": ["feature_extraction_failed"]}

    features = payload.get("features", [])
    if not isinstance(features, list):
        return {"features": [], "parse_anomalies": ["feature_extraction_failed"]}

    # 截断
    if len(features) > _MAX_FEATURES:
        features = features[:_MAX_FEATURES]
        anomalies.append("feature_extraction_truncated")

    result: dict[str, Any] = {"features": features, "parse_anomalies": anomalies}

    # 落盘 cache（best-effort，写失败不影响返回）
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_payload = {
            "schema_version": 1,
            "subsystem": subsystem,
            "run_id": run_id,
            "source_files": [str(spec_md_path), str(design_doc_path)],
            "features": features,
            "parse_anomalies": anomalies,
        }
        (cache_dir / "matches_spec_features.json").write_text(
            json.dumps(cache_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass

    return result
