"""加载子系统识别 + KPI 抽取词典；dataclass 自校验。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_DEFAULT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ProductGoalDictionary:
    """3 层确定性解析器词典聚合体。"""

    subsystem_keywords: dict[str, dict[str, Any]]
    kpi_patterns: dict[str, dict[str, dict[str, Any]]]

    def __post_init__(self) -> None:
        for name, entry in self.subsystem_keywords.items():
            status = entry.get("status")
            if status not in {"implemented", "not_yet_implemented"}:
                raise RuntimeError(f"subsystem_keywords[{name}].status 非法：{status!r}")
            if not entry.get("primary_terms"):
                raise RuntimeError(f"subsystem_keywords[{name}].primary_terms 不能为空")

        implemented = {n for n, e in self.subsystem_keywords.items() if e.get("status") == "implemented"}
        kpi_keys = set(self.kpi_patterns.keys())
        missing = sorted(implemented - kpi_keys)
        if missing:
            raise RuntimeError(
                f"implemented 子系统 {missing} 缺少 kpi_patterns 条目"
            )

        for subsystem, kpis in self.kpi_patterns.items():
            for kpi_name, kpi in kpis.items():
                if not isinstance(kpi.get("regex"), list) or not kpi["regex"]:
                    raise RuntimeError(f"kpi_patterns[{subsystem}.{kpi_name}].regex 必须是非空列表")
                if not isinstance(kpi.get("context_terms"), list) or not kpi["context_terms"]:
                    raise RuntimeError(f"kpi_patterns[{subsystem}.{kpi_name}].context_terms 必须是非空列表")
                if "unit" not in kpi:
                    raise RuntimeError(f"kpi_patterns[{subsystem}.{kpi_name}].unit 缺")


def load_dictionary(*, dict_root: Path | None = None) -> ProductGoalDictionary:
    """从 JSON 文件加载词典；缺文件 / schema 错 → RuntimeError。"""
    root = dict_root or _DEFAULT_ROOT
    keywords_path = root / "subsystem_keywords.json"
    patterns_path = root / "kpi_patterns.json"

    if not keywords_path.is_file():
        raise RuntimeError(f"subsystem_keywords.json 不存在：{keywords_path}")
    if not patterns_path.is_file():
        raise RuntimeError(f"kpi_patterns.json 不存在：{patterns_path}")

    keywords = json.loads(keywords_path.read_text(encoding="utf-8"))
    patterns = json.loads(patterns_path.read_text(encoding="utf-8"))

    return ProductGoalDictionary(
        subsystem_keywords=keywords,
        kpi_patterns=patterns,
    )


__all__ = ["ProductGoalDictionary", "load_dictionary"]
