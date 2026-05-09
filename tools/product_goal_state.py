"""PROJECT_GOAL_STATE.json schema + read/write/delete/validate_answer helper

spec: docs/superpowers/specs/2026-05-09-product-goal-progressive-design.md v1.0
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.contract_io import write_json_atomic

PROJECT_GOAL_STATE_FILENAME = "PROJECT_GOAL_STATE.json"
SCHEMA_VERSION = 1
MAX_ROUND = 20

KPI_VALUE_TYPES: dict[str, str] = {
    "load_kg": "float",
    "stroke_mm": "float",
    "platform_size_mm": "size_pair",
    "rot_range_deg": "float",
    "switch_time_s": "float",
    "flange_dia_mm": "float",
}

_SIZE_PAIR_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$")


def state_path(cwd: Path | None = None) -> Path:
    """返回 PROJECT_GOAL_STATE.json 的绝对路径（基于 cwd 或 Path.cwd()）"""
    return (cwd or Path.cwd()) / PROJECT_GOAL_STATE_FILENAME


def read_state(cwd: Path | None = None) -> dict[str, Any] | None:
    """读取 state 文件；不存在返回 None；解析失败 / schema 不识别抛 ValueError"""
    path = state_path(cwd)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"./PROJECT_GOAL_STATE.json 读取失败：{exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"./PROJECT_GOAL_STATE.json 解析失败：{exc.msg}（删除后重新 --product-goal 起手）"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("./PROJECT_GOAL_STATE.json 顶层必须是 dict")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"./PROJECT_GOAL_STATE.json schema_version={data.get('schema_version')} "
            f"不识别（期望 {SCHEMA_VERSION}）"
        )
    return data


def write_state(state: Mapping[str, Any], cwd: Path | None = None) -> Path:
    """原子写入 state；首次创建时记录 created_at；每次更新 updated_at"""
    path = state_path(cwd)
    now_iso = datetime.now(timezone.utc).isoformat()

    existing = read_state(cwd) if path.is_file() else None
    created_at = (
        existing["created_at"]
        if existing and "created_at" in existing
        else now_iso
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        **dict(state),
        "created_at": created_at,
        "updated_at": now_iso,
    }
    write_json_atomic(path, payload)
    return path


def delete_state(cwd: Path | None = None) -> None:
    """删除 state 文件；幂等（文件不存在不报错）"""
    path = state_path(cwd)
    if path.is_file():
        path.unlink()


def validate_answer(key: str, value: str) -> Any:
    """校验并解析 --answer KEY=VALUE 的字符串值

    返回类型按 KPI_VALUE_TYPES 映射：float / size_pair (tuple[float, float]) / str
    解析失败 / key 不识别抛 ValueError
    """
    key = key.strip()

    if key == "subsystem":
        if not value.strip():
            raise ValueError("--answer value 'subsystem' 不能为空")
        return value.strip()

    if key not in KPI_VALUE_TYPES:
        all_keys = sorted(set(KPI_VALUE_TYPES.keys()) | {"subsystem"})
        raise ValueError(
            f"--answer key {key!r} 不在 KPI 列表 {all_keys}"
        )

    value_type = KPI_VALUE_TYPES[key]
    if value_type == "float":
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(
                f"--answer value {value!r} 解析失败：{key} 期望 float（如 '50' / '800.5'）"
            ) from exc

    if value_type == "size_pair":
        match = _SIZE_PAIR_PATTERN.match(value.strip())
        if not match:
            raise ValueError(
                f"--answer value {value!r} 解析失败：{key} 期望 'AxB' 格式（如 '600x600' / '800x600'）"
            )
        return (float(match.group(1)), float(match.group(2)))

    raise ValueError(f"内部错误：未知 value_type {value_type!r} for key {key!r}")
