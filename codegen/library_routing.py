from __future__ import annotations

from cad_spec_defaults import strip_part_prefix
from parts_resolver import PartQuery


LIBRARY_ROUTED_CUSTOM_CATEGORIES = {"transmission", "elastic", "locating", "seal"}
LIBRARY_ROUTED_ADAPTERS = {"parametric_transmission", "step_pool", "partcad"}


def library_suffix(part_no: str) -> str:
    suffix = strip_part_prefix(part_no).lower().replace("-", "_")
    if suffix and suffix[0].isdigit():
        suffix = "p" + suffix
    return suffix


def library_module_name(part_no: str) -> str:
    return f"std_{library_suffix(part_no)}"


def library_make_function(part_no: str) -> str:
    return f"make_{library_module_name(part_no)}"


def build_library_part_query(
    part: dict,
    *,
    category: str,
    envelope,
    project_root: str,
) -> PartQuery:
    spec_envelope = envelope
    granularity = "part_envelope"
    if isinstance(envelope, dict):
        spec_envelope = envelope.get("dims")
        granularity = envelope.get("granularity") or "part_envelope"
    return PartQuery(
        part_no=part["part_no"],
        name_cn=part["name_cn"],
        material=part.get("material", ""),
        category=category,
        make_buy=part.get("make_buy", ""),
        spec_envelope=spec_envelope,
        spec_envelope_granularity=granularity,
        project_root=project_root,
    )


def is_library_routed_row(
    part: dict,
    *,
    category: str,
    resolver,
    query: PartQuery,
) -> bool:
    make_buy = part.get("make_buy", "")
    if "外购" in make_buy or "标准" in make_buy:
        return True
    if "自制" not in make_buy:
        return False
    if category not in LIBRARY_ROUTED_CUSTOM_CATEGORIES:
        return False
    matching_rules = getattr(resolver, "matching_rules", None)
    if matching_rules is None:
        return False
    matched_rule = None
    for rule in matching_rules(query):
        if rule.get("adapter") in LIBRARY_ROUTED_ADAPTERS:
            matched_rule = rule
            break
    if matched_rule is None:
        return False

    adapter = _find_adapter(resolver, matched_rule.get("adapter"))
    if adapter is None:
        return False
    is_available = getattr(adapter, "is_available", None)
    if is_available is not None:
        ok, _reason = is_available()
        if not ok:
            return False
    probe_dims = getattr(adapter, "probe_dims", None)
    if probe_dims is None:
        return False
    try:
        return probe_dims(query, matched_rule.get("spec", {}) or {}) is not None
    except Exception:
        return False


def _find_adapter(resolver, name: str | None):
    if not name:
        return None
    for adapter in getattr(resolver, "adapters", []) or []:
        if getattr(adapter, "name", "") == name:
            return adapter
    return None
