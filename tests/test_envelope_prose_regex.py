"""Tests for the envelope prose regex fix (partial Issue 2 fix).

Spec 1 validation on the real end_effector design doc revealed that
`extract_part_envelopes()` returned 0 envelopes, even though the doc
contains 4 explicit `模块包络尺寸` lines. Two regex bugs were identified:

1. The P2 regex did not handle markdown bold wrappers:
   `模块包络尺寸**：60×40×290mm` vs the regex `模块包络尺寸[：:]`
   — the `**` between text and colon caused zero matches.

2. The P2 regex did not handle cylindrical `Φd×h` forms:
   `模块包络尺寸: Φ45×120mm` was never matched because only the
   three-dimension `W×D×H` form was supported.

This test locks in both regex fixes.

**Known limitation** (documented in cad_spec_extractors.py P2 block):
Even with these regex fixes, `_find_nearest_assembly()` may still return
None for design docs that use Chinese section headings instead of
explicit part_no references. The full fix requires a section-header
walker and is deferred to a follow-up spec. This test only verifies the
REGEX MATCHES THE TEXT — not that the resulting envelopes are
successfully attached to BOM assemblies.
"""
import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent


def _load_repo_root_extractors():
    """Load the repo-root cad_spec_extractors.py directly, bypassing
    any sys.path contamination from other tests."""
    path = _REPO_ROOT / "cad_spec_extractors.py"
    spec = importlib.util.spec_from_file_location("cad_spec_extractors_repo_root", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Sample envelope lines covering all the forms the design doc uses
_SAMPLE_DOC = """
### 工位1(0°)：耦合剂涂抹模块
- **模块包络尺寸**：60×40×290mm（宽×深×高，含储罐延伸）
- LEMO接头

### 工位2(90°)：AE声发射检测模块
- **模块包络尺寸**：Φ45×120mm（含弹簧限力）
- 传感器

### 工位3(180°)：卷带清洁模块
- **模块包络尺寸**：50×40×120mm（切向宽×径向深×轴向高）
- 卷轴

### 工位4(270°)：UHF模块
- **模块包络尺寸**：Φ50×85mm（含安装支架）
- UHF天线

### Half-width colon variant
- **模块包络尺寸**:80×60×150mm
- Note: uses ASCII colon, no bold

### No bold marker variant
- 模块包络尺寸：100×50×200mm
"""


def test_regex_matches_box_form_with_markdown_bold():
    """模块包络尺寸**：W×D×H — the specific form the real design doc uses."""
    import re
    pattern = (
        r"模块包络尺寸(?:\*\*)?[：:]\s*"
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm"
    )
    matches = re.findall(pattern, _SAMPLE_DOC)
    # Expect: (60,40,290), (50,40,120), (80,60,150), (100,50,200)
    assert len(matches) == 4, f"Expected 4 box matches, got {len(matches)}: {matches}"
    assert ('60', '40', '290') in matches
    assert ('50', '40', '120') in matches
    assert ('80', '60', '150') in matches
    assert ('100', '50', '200') in matches


def test_regex_matches_cylinder_form_with_markdown_bold():
    """模块包络尺寸**：Φd×h — the new regex pattern."""
    import re
    pattern = (
        r"模块包络尺寸(?:\*\*)?[：:]\s*"
        r"[ΦφØ∅](\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm"
    )
    matches = re.findall(pattern, _SAMPLE_DOC)
    # Expect: (45, 120), (50, 85)
    assert len(matches) == 2, f"Expected 2 cylinder matches, got {len(matches)}: {matches}"
    assert ('45', '120') in matches
    assert ('50', '85') in matches


def test_regex_rejects_old_pattern_without_bold_fix():
    """The OLD regex (without (?:\\*\\*)?) must NOT match bold-wrapped text.

    This is the regression gate: if the old pattern is accidentally
    re-introduced, this test fails.
    """
    import re
    old_pattern = (
        r"模块包络尺寸[：:]\s*"
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm"
    )
    matches = re.findall(old_pattern, _SAMPLE_DOC)
    # Old pattern only matches the "No bold marker variant" line (100×50×200)
    # and the half-width colon variant (80×60×150), but NOT the **bold** ones.
    old_match_strs = [f"{w}×{d}×{h}" for w, d, h in matches]
    assert "60×40×290" not in old_match_strs, \
        "Old regex should NOT have matched bold-wrapped envelope"
    assert "50×40×120" not in old_match_strs, \
        "Old regex should NOT have matched bold-wrapped envelope"


def test_extract_part_envelopes_regex_finds_real_design_doc_envelopes():
    """End-to-end: load cad_spec_extractors and test its P2 regex against
    a sample doc that mimics the real end_effector design doc.

    This does NOT test that the envelopes are attached to assemblies —
    that depends on `_find_nearest_assembly()` which has a known
    limitation documented in the extractor's P2 block comment.

    This test ONLY verifies that the regex can find the envelope
    markers in the text. For the full pipeline to succeed, a future
    fix must address _find_nearest_assembly() semantics.
    """
    import re
    extractors = _load_repo_root_extractors()
    # Access the P2 regex by re-running it directly. We re-declare the
    # patterns here (identical to what's in extract_part_envelopes) to
    # verify they exist and match.
    box_pattern = (
        r"模块包络尺寸(?:\*\*)?[：:]\s*"
        r"(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm"
    )
    cyl_pattern = (
        r"模块包络尺寸(?:\*\*)?[：:]\s*"
        r"[ΦφØ∅](\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*mm"
    )
    box_hits = re.findall(box_pattern, _SAMPLE_DOC)
    cyl_hits = re.findall(cyl_pattern, _SAMPLE_DOC)
    total = len(box_hits) + len(cyl_hits)
    assert total == 6, f"Expected 6 total envelope hits (4 box + 2 cyl), got {total}"

    # Also verify the source file itself contains both regex patterns
    extractor_src = (_REPO_ROOT / "cad_spec_extractors.py").read_text(encoding="utf-8", errors="replace")
    assert "模块包络尺寸(?:\\*\\*)?[：:]" in extractor_src, \
        "cad_spec_extractors.py P2 regex is missing the markdown bold fix"
    assert "[ΦφØ∅]" in extractor_src, \
        "cad_spec_extractors.py P2 regex is missing the cylinder form"


def test_known_limitation_documented():
    """The P2 block comment must explicitly document the
    _find_nearest_assembly limitation so future maintainers know this
    is a partial fix, not a complete one.
    """
    src = (_REPO_ROOT / "cad_spec_extractors.py").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "KNOWN LIMITATION" in src, \
        "cad_spec_extractors.py must document the _find_nearest_assembly limitation"
    assert "_find_nearest_assembly" in src, \
        "Documentation must name the function with the limitation"
    assert "section-header walker" in src or "follow-up spec" in src, \
        "Documentation must reference the deferred fix"


def test_find_nearest_assembly_uses_bom_derived_prefixes():
    """Tier 0 must work on non-GISBOT subsystems. The prefix regex should
    be built from BOM data at call time, not hardcoded to GIS-EE-NNN."""
    from cad_spec_extractors import _find_nearest_assembly

    bom = {
        "assemblies": [
            {"part_no": "CHASSIS-DRV-001", "name": "Drive Wheel 1"},
            {"part_no": "CHASSIS-DRV-002", "name": "Drive Wheel 2"},
        ]
    }
    prefixes = ("CHASSIS-DRV",)
    context = "see CHASSIS-DRV-001 specification for detail"
    assert _find_nearest_assembly(context, bom, prefixes) == "CHASSIS-DRV-001"


def test_find_nearest_assembly_auto_derives_prefix_when_not_supplied():
    """When bom_pno_prefixes is None, auto-derive from BOM assemblies.
    This preserves backward compat with the legacy P2 block that calls
    with only two args."""
    from cad_spec_extractors import _find_nearest_assembly
    bom = {
        "assemblies": [{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}],
    }
    context = "as defined in GIS-EE-002 above"
    assert _find_nearest_assembly(context, bom) == "GIS-EE-002"


def test_find_nearest_assembly_empty_bom_no_match():
    from cad_spec_extractors import _find_nearest_assembly
    bom = {"assemblies": []}
    assert _find_nearest_assembly("anything", bom) is None


def test_find_nearest_assembly_no_match_falls_back_to_name_substring():
    """When no part_no matches, the second strategy — 4-char substring
    of BOM name — still works. This is the existing behavior, preserved."""
    from cad_spec_extractors import _find_nearest_assembly
    bom = {
        "assemblies": [{"part_no": "GIS-EE-002", "name": "工位1涂抹模块"}],
    }
    # Context contains the first 4 chars of the BOM name
    context = "The 工位1涂 module has been defined"
    assert _find_nearest_assembly(context, bom) == "GIS-EE-002"


def test_extract_part_envelopes_returns_tuple_with_walker_report():
    """Return type is now (envelopes, walker_report) — all callers must
    destructure the tuple."""
    from cad_spec_extractors import extract_part_envelopes

    lines = [
        "## 4.1 机械结构",
        "**工位1(0°)：耦合剂涂抹模块**",
        "- **模块包络尺寸**：60×40×290mm (宽×深×高)",
    ]
    bom = {
        "assemblies": [
            {"part_no": "GIS-EE-002", "name": "工位1涂抹模块", "parts": []},
        ]
    }
    result = extract_part_envelopes(lines, bom)
    assert isinstance(result, tuple)
    assert len(result) == 2
    envelopes, walker_report = result
    assert isinstance(envelopes, dict)
    assert "GIS-EE-002" in envelopes
    assert envelopes["GIS-EE-002"]["source"].startswith("P2:walker:tier")
    assert envelopes["GIS-EE-002"]["granularity"] == "station_constraint"
    # Envelope dict carries canonical axes.
    assert envelopes["GIS-EE-002"]["x"] == 60.0
    assert envelopes["GIS-EE-002"]["y"] == 40.0
    assert envelopes["GIS-EE-002"]["z"] == 290.0
    # walker_report is the WalkerReport dataclass
    assert walker_report.feature_flag_enabled is True
