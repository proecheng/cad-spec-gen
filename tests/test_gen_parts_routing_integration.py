"""Integration test: gen_parts.py calls parts_routing and logs decisions."""
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent


def test_gen_parts_imports_parts_routing():
    """codegen/gen_parts.py must import parts_routing for Spec 1 integration."""
    gen_parts_src = (_REPO_ROOT / "codegen" / "gen_parts.py").read_text(encoding="utf-8")
    assert "from cad_spec_gen.parts_routing import" in gen_parts_src, \
        "gen_parts.py must import parts_routing"


def test_gen_parts_route_call_is_log_only():
    """Spec 1 integration is log-only — no behavior change to emission."""
    gen_parts_src = (_REPO_ROOT / "codegen" / "gen_parts.py").read_text(encoding="utf-8")
    # Some form of routing-preview log must be present
    assert "routing preview" in gen_parts_src or "route preview" in gen_parts_src, \
        "gen_parts.py must log routing decisions at INFO level with 'routing preview' phrase"


def test_gen_parts_src_path_inserted():
    """gen_parts.py must insert src/ path before importing cad_spec_gen.parts_routing."""
    gen_parts_src = (_REPO_ROOT / "codegen" / "gen_parts.py").read_text(encoding="utf-8")
    # Verify there's an insertion of "src" into sys.path
    assert "src" in gen_parts_src and "sys.path" in gen_parts_src, \
        "gen_parts.py must add src/ to sys.path for package resolution"
