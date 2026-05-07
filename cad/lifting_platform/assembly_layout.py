"""Manual assembly layout overrides.

This file is owned by users or design agents. Ordinary codegen --force
preserves it; pass --force-layout only when you intentionally want to rebuild
the manual layout scaffold.
"""

MANUAL_LAYOUT_OVERRIDES = {}


def apply_layout(assy):
    """Return assy after applying manual placement overrides."""
    return assy
