from __future__ import annotations

import re
from typing import Any

from adapters.parts.base import PartsAdapter


class ParametricTransmissionAdapter(PartsAdapter):
    name = "parametric_transmission"

    def is_available(self):
        return True, None

    def can_resolve(self, query) -> bool:
        return getattr(query, "category", "") == "transmission"

    def resolve(self, query, spec: dict, mode: str = "codegen"):
        from parts_resolver import ResolveResult

        template = spec.get("template")
        if template != "trapezoidal_lead_screw":
            return ResolveResult.miss()

        params = _parse_lead_screw_params(query, spec)
        if params is None:
            return ResolveResult.miss()

        return ResolveResult(
            status="hit",
            kind="codegen",
            adapter=self.name,
            body_code=_emit_lead_screw_body(params),
            real_dims=(
                params["outer_diameter_mm"],
                params["outer_diameter_mm"],
                params["total_length_mm"],
            ),
            source_tag=(
                "parametric_transmission:"
                f"trapezoidal_lead_screw(Tr{params['outer_diameter_mm']:g}"
                f"x{params['pitch_mm']:g},L{params['total_length_mm']:g})"
            ),
            geometry_source="PARAMETRIC_TEMPLATE",
            geometry_quality="B",
            validated=True,
            requires_model_review=False,
            metadata={
                "template": "trapezoidal_lead_screw",
                "normalize_origin": "center_xy_bottom_z",
                "parameters": dict(params),
            },
        )

    def probe_dims(self, query, spec: dict):
        params = _parse_lead_screw_params(query, spec)
        if params is None:
            return None
        return (
            params["outer_diameter_mm"],
            params["outer_diameter_mm"],
            params["total_length_mm"],
        )


def _parse_lead_screw_params(query, spec: dict) -> dict[str, Any] | None:
    text = f"{getattr(query, 'name_cn', '')} {getattr(query, 'material', '')}"
    defaults = dict(spec.get("defaults") or {})
    env_dims = _envelope_dims(getattr(query, "spec_envelope", None))

    outer_d = _float_or_none(defaults.get("outer_diameter_mm"))
    pitch = _float_or_none(defaults.get("pitch_mm"))
    total_l = _float_or_none(defaults.get("total_length_mm"))

    tr_match = re.search(
        r"\btr\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\b",
        text,
        re.IGNORECASE,
    )
    if tr_match:
        outer_d = outer_d if outer_d is not None else float(tr_match.group(1))
        pitch = pitch if pitch is not None else float(tr_match.group(2))
    else:
        t_match = re.search(r"\bt\s*(\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
        if t_match and outer_d is None:
            outer_d = float(t_match.group(1))

    if outer_d is None and env_dims:
        outer_d = min(env_dims)
    if pitch is None:
        pitch = _float_or_none(defaults.get("lead_mm"))
    if outer_d is None or pitch is None:
        return None

    length_match = re.search(r"\bL\s*(\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if total_l is None and length_match:
        total_l = float(length_match.group(1))
    if total_l is None and env_dims:
        total_l = max(env_dims)
    if total_l is None:
        return None

    lower_l = _float_or_none(defaults.get("lower_shaft_length_mm"))
    upper_l = _float_or_none(defaults.get("upper_shaft_length_mm"))
    lower_l = 0.0 if lower_l is None else max(0.0, lower_l)
    upper_l = 0.0 if upper_l is None else max(0.0, upper_l)

    thread_l_default = defaults.get("thread_length_mm")
    if thread_l_default is None:
        thread_l = None
    else:
        available_thread_l = max(0.0, total_l - lower_l - upper_l)
        parsed_thread_l = _float_or_none(thread_l_default)
        thread_l = (
            None
            if parsed_thread_l is None
            else max(0.0, min(parsed_thread_l, available_thread_l))
        )

    lower_d = _float_or_none(defaults.get("lower_shaft_diameter_mm"))
    upper_d = _float_or_none(defaults.get("upper_shaft_diameter_mm"))
    root_d = _float_or_none(defaults.get("root_diameter_mm"))

    return {
        "outer_diameter_mm": outer_d,
        "pitch_mm": pitch,
        "total_length_mm": total_l,
        "thread_length_mm": thread_l,
        "lower_shaft_diameter_mm": lower_d if lower_d is not None else max(outer_d * 0.75, outer_d - pitch),
        "lower_shaft_length_mm": lower_l,
        "upper_shaft_diameter_mm": upper_d if upper_d is not None else max(outer_d * 0.75, outer_d - pitch),
        "upper_shaft_length_mm": upper_l,
        "root_diameter_mm": root_d if root_d is not None else max(outer_d - pitch * 0.55, outer_d * 0.72),
        "starts": int(defaults.get("starts") or 1),
    }


def _envelope_dims(raw: Any) -> tuple[float, ...]:
    if raw is None:
        return ()
    try:
        return tuple(float(value) for value in raw if value is not None and float(value) > 0)
    except (TypeError, ValueError):
        return ()


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _emit_lead_screw_body(params: dict[str, Any]) -> str:
    lines = [
        "    from adapters.parts.parametric_transmission import make_trapezoidal_lead_screw",
        "    return make_trapezoidal_lead_screw(",
    ]
    for key in (
        "outer_diameter_mm",
        "pitch_mm",
        "total_length_mm",
        "thread_length_mm",
        "lower_shaft_diameter_mm",
        "lower_shaft_length_mm",
        "upper_shaft_diameter_mm",
        "upper_shaft_length_mm",
        "root_diameter_mm",
        "starts",
    ):
        lines.append(f"        {key}={params[key]!r},")
    lines.append("    )")
    return "\n".join(lines)
