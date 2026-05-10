"""规则表加载 + 用户 yaml override + 范围校验。

安全：yaml.safe_load 强制；用户 yaml 路径限定在 project_root 内（SEC-MAJOR-1）。
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 1
_BUILTIN_RESOURCE = "photoreal_v1.yaml"

# M-12 范围常量：(min, max)。已知 key 在此声明，未知 key 静默忽略。
# 注：Task 2.5.5 会接入 BACKEND_REGISTRY[kind].known_params 动态拿白名单；
# 此静态表是 CP-2 临时占位（spec §4.3 明示）。
KNOWN_PARAMS: dict[str, tuple[float, float]] = {
    "canny_strength":   (0.0, 1.0),
    "depth_strength":   (0.0, 1.0),
    "canny_end_pct":    (0.0, 1.0),
    "denoise_strength": (0.0, 1.0),
    "img2img_strength": (0.0, 1.0),
    "guidance_scale":   (1.0, 30.0),
    "cfg_scale":        (1.0, 30.0),
    "steps":            (1, 200),
    # gemini_chat_image
    "temperature":      (0.0, 2.0),
    "top_p":            (0.0, 1.0),
    "top_k":            (1, 100),
}

# DRIFT-MINOR-6 closed schema 允许字段集
_TOP_KEYS_ALLOWED = {"schema_version", "rules", "tag_dictionary"}
_RULE_KEYS_ALLOWED = {"id", "when_tags", "prompt_addons", "param_overrides"}


class RuleTableLoadError(Exception):
    """yaml load / schema 校验 / 路径限制 / 反序列化失败。"""


class RuleTableUnsupportedSchemaWarning(UserWarning):
    """SEC-MINOR-3 用户 yaml schema_version 不支持，降级仅用内置。"""


@dataclass(frozen=True)
class Rule:
    id: str
    when_tags: frozenset[str]
    prompt_addons: tuple[str, ...]
    # {"gemini_chat_image": {...}, "openai_images_edit": {...}, "comfyui_workflow_cloud": {...}}
    param_overrides: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class RuleTable:
    schema_version: int
    rules: tuple[Rule, ...]
    tag_dictionary: dict[str, list[str]]


@dataclass
class RuleTableLookupResult:
    prompt_addons: list[str] = field(default_factory=list)
    param_overrides: dict[str, Any] = field(default_factory=dict)
    matched_rule_ids: list[str] = field(default_factory=list)
    matched_tags: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)


def load_rule_table(
    user_yaml_path: Path | None = None,
    project_root: Path | None = None,
) -> RuleTable:
    """加载内置 + 可选用户 yaml 合并后的规则表。"""
    builtin_text = files("tools.jury_loop.rules").joinpath(_BUILTIN_RESOURCE).read_text(encoding="utf-8")
    try:
        builtin = yaml.safe_load(builtin_text)
    except yaml.YAMLError as e:
        raise RuleTableLoadError(f"内置 photoreal_v1.yaml 解析失败：{e}") from e
    _assert_closed_schema(builtin)
    table = _build_table(builtin)

    if user_yaml_path is not None:
        if project_root is None:
            raise RuleTableLoadError("project_root 必填当 user_yaml_path 提供时")

        try:
            user_resolved = user_yaml_path.resolve()
            project_resolved = project_root.resolve()
            user_resolved.relative_to(project_resolved)
        except (OSError, ValueError) as e:
            raise RuleTableLoadError(
                f"rule_table_path 必须在项目目录内：{user_yaml_path}"
            ) from e

        try:
            user_text = user_yaml_path.read_text(encoding="utf-8")
            user = yaml.safe_load(user_text)
        except (OSError, yaml.YAMLError) as e:
            raise RuleTableLoadError(f"用户 yaml 加载失败：{e}") from e

        if not isinstance(user, dict):
            raise RuleTableLoadError("用户 yaml 顶层必须是 mapping")

        user_sv = user.get("schema_version")
        if user_sv != SCHEMA_VERSION:
            warnings.warn(
                f"用户 yaml schema_version={user_sv} 不被支持（仅 {SCHEMA_VERSION}），降级为仅用内置",
                RuleTableUnsupportedSchemaWarning,
                stacklevel=2,
            )
            return table

        _assert_closed_schema(user)
        table = _merge(table, user)

    return table


def _assert_closed_schema(data: dict[str, Any]) -> None:
    """closed schema：除 _* 前缀外不允许未知字段。"""
    if not isinstance(data, dict):
        raise RuleTableLoadError("yaml 顶层必须是 mapping")
    for k in data:
        if k.startswith("_"):
            continue
        if k not in _TOP_KEYS_ALLOWED:
            raise RuleTableLoadError(
                f"unknown field at top level: {k!r}（是否拼写错误？允许字段：{sorted(_TOP_KEYS_ALLOWED)}）"
            )

    rules = data.get("rules", [])
    if not isinstance(rules, list):
        raise RuleTableLoadError("rules 必须是 list")
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise RuleTableLoadError(f"rules[{i}] 必须是 mapping")
        for rk in rule:
            if rk.startswith("_"):
                continue
            if rk not in _RULE_KEYS_ALLOWED:
                raise RuleTableLoadError(
                    f"unknown field in rules[{i}] (id={rule.get('id', '?')!r}): {rk!r}"
                )

        po = rule.get("param_overrides", {})
        if not isinstance(po, dict):
            raise RuleTableLoadError(f"rules[{i}].param_overrides 必须是 mapping")
        for backend, params in po.items():
            if not isinstance(params, dict):
                raise RuleTableLoadError(
                    f"rules[{i}].param_overrides.{backend} 必须是 mapping"
                )
            for pkey, pval in params.items():
                if isinstance(pval, dict):
                    raise RuleTableLoadError(
                        f"rules[{i}].param_overrides.{backend}.{pkey} 不允许嵌套 dict（M-11 必须 flat）"
                    )
                if not isinstance(pval, (int, float, str, bool)):
                    raise RuleTableLoadError(
                        f"rules[{i}].param_overrides.{backend}.{pkey} 类型必须是 int|float|str|bool，得到 {type(pval)}"
                    )


def _build_table(data: dict[str, Any]) -> RuleTable:
    rules: list[Rule] = []
    for r in data.get("rules", []):
        rules.append(Rule(
            id=r["id"],
            when_tags=frozenset(r.get("when_tags", [])),
            prompt_addons=tuple(r.get("prompt_addons", [])),
            param_overrides={k: dict(v) for k, v in r.get("param_overrides", {}).items()},
        ))
    return RuleTable(
        schema_version=int(data["schema_version"]),
        rules=tuple(rules),
        tag_dictionary=dict(data.get("tag_dictionary", {})),
    )


def _merge(builtin: RuleTable, user: dict[str, Any]) -> RuleTable:
    """合并内置 + 用户 yaml。同 id 替换保留内置位置；新 id 追加；tag_dict 同 key 追加。"""
    builtin_rule_by_id = {r.id: i for i, r in enumerate(builtin.rules)}
    merged_rules: list[Rule] = list(builtin.rules)

    for ur in user.get("rules", []):
        rule_obj = Rule(
            id=ur["id"],
            when_tags=frozenset(ur.get("when_tags", [])),
            prompt_addons=tuple(ur.get("prompt_addons", [])),
            param_overrides={k: dict(v) for k, v in ur.get("param_overrides", {}).items()},
        )
        if ur["id"] in builtin_rule_by_id:
            merged_rules[builtin_rule_by_id[ur["id"]]] = rule_obj
        else:
            merged_rules.append(rule_obj)

    merged_tagdict = {k: list(v) for k, v in builtin.tag_dictionary.items()}
    for tag, patterns in user.get("tag_dictionary", {}).items():
        if tag in merged_tagdict:
            for p in patterns:
                if p not in merged_tagdict[tag]:
                    merged_tagdict[tag].append(p)
        else:
            merged_tagdict[tag] = list(patterns)

    return RuleTable(
        schema_version=builtin.schema_version,
        rules=tuple(merged_rules),
        tag_dictionary=merged_tagdict,
    )


def lookup(
    table: RuleTable,
    tags: set[str],
    backend_kind: str,
) -> RuleTableLookupResult:
    """规则表查询：返回合并后的 prompt_addons + param_overrides。

    注：Task 2.5.5 会改 _clamp_param 走 BACKEND_REGISTRY[backend_kind].known_params。
    """
    result = RuleTableLookupResult()
    seen_addons: set[str] = set()

    for rule in table.rules:
        if not rule.when_tags.issubset(tags):
            continue
        result.matched_rule_ids.append(rule.id)
        result.matched_tags |= rule.when_tags

        for addon in rule.prompt_addons:
            if addon not in seen_addons:
                result.prompt_addons.append(addon)
                seen_addons.add(addon)

        backend_params = rule.param_overrides.get(backend_kind, {})
        for pkey, pval in backend_params.items():
            clamped, warn = _clamp_param(pkey, pval)
            if warn:
                result.warnings.append(warn)
            result.param_overrides[pkey] = clamped

    return result


def _clamp_param(key: str, value: Any) -> tuple[Any, str | None]:
    """对已知 param 做范围 clamp，越界写 warning；未知 key 透传写 unknown_param warning。"""
    if key not in KNOWN_PARAMS:
        return value, f"unknown_param: {key}"
    lo, hi = KNOWN_PARAMS[key]
    if not isinstance(value, (int, float)):
        return value, None
    if value < lo:
        return lo, f"param_clamped: {key}={value}→{lo}"
    if value > hi:
        return hi, f"param_clamped: {key}={value}→{hi}"
    return value, None
