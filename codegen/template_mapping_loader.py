import json
from pathlib import Path

_BUILTIN_KEYWORDS: dict[str, str] = {
    "flange": "法兰",
    "housing": "壳体",
    "bracket": "支架",
    "spring_mechanism": "弹簧",
    "sleeve": "套筒",
    "plate": "板",
    "arm": "悬臂",
    "cover": "盖",
}

_VALID_TEMPLATES: frozenset[str] = frozenset(_BUILTIN_KEYWORDS.keys())


def load_template_mapping(mapping_path: str | None) -> dict[str, str]:
    """加载用户 template_mapping.json，返回 name_cn → template_type 字典。

    文件不存在时静默返回空字典。值不在已知模板名内时 warn + 跳过。
    """
    if not mapping_path:
        return {}
    p = Path(mapping_path)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        raw: dict = json.load(f)
    result: dict[str, str] = {}
    for key, val in raw.items():
        if key.startswith("_"):  # 跳过 _comment / _valid_values 等注释键
            continue
        if val not in _VALID_TEMPLATES:
            print(
                f"  WARNING: template_mapping.json: 未知模板名 '{val}'（键 '{key}'），已跳过"
            )
            continue
        result[key] = val
    return result


def match_template(name_cn: str, user_mapping: dict[str, str]) -> str | None:
    """将零件 name_cn 匹配到模板类型。

    优先级：user_mapping 精确匹配 > 内置关键词包含匹配 > None
    """
    if name_cn in user_mapping:
        return user_mapping[name_cn]
    for tpl_type, keyword in _BUILTIN_KEYWORDS.items():
        if keyword in name_cn:
            return tpl_type
    return None
