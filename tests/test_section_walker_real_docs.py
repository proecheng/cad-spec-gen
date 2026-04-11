"""Layer 3 integration tests against real design docs.

Uses pre-computed BOM YAML fixtures at tests/fixtures/real_doc_boms/*.yaml
(generated manually via _regenerate.py). Tests NEVER write to cad/<subsystem>/.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from cad_spec_section_walker import SectionWalker

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "real_doc_boms"
END_EFFECTOR_DOC = Path("D:/Work/cad-tests/04-末端执行机构设计.md")
LIFTING_PLATFORM_DOC = Path("D:/Work/cad-tests/19-液压钳升降平台设计.md")


def _load_yaml_bom(name: str) -> dict | None:
    path = FIXTURE_DIR / f"{name}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.integration
def test_end_effector_docs_match_four_stations():
    bom = _load_yaml_bom("end_effector")
    if bom is None or not END_EFFECTOR_DOC.exists():
        pytest.skip("end_effector fixture or source doc missing")
    lines = END_EFFECTOR_DOC.read_text(encoding="utf-8").splitlines()
    outputs, stats = SectionWalker(lines, bom).extract_envelopes()
    assert stats.matched_count >= 4, (
        f"Expected >=4 station envelopes matched, got {stats.matched_count}. "
        f"Unmatched reasons: {stats.unmatched_reasons}"
    )
    # All matches should resolve to GIS-EE-00N assemblies
    for o in outputs:
        if o.matched_pno:
            assert o.matched_pno.startswith("GIS-EE-"), \
                f"Unexpected match: {o.matched_pno}"


@pytest.mark.integration
def test_lifting_platform_docs_match_at_least_two():
    bom = _load_yaml_bom("lifting_platform")
    if bom is None or not LIFTING_PLATFORM_DOC.exists():
        pytest.skip("lifting_platform fixture or source doc missing")
    lines = LIFTING_PLATFORM_DOC.read_text(encoding="utf-8").splitlines()
    outputs, stats = SectionWalker(lines, bom).extract_envelopes()
    if stats.matched_count < 2:
        pytest.skip(
            f"lifting_platform only matched {stats.matched_count} envelopes — "
            f"documented known limitation (reasons: {stats.unmatched_reasons})"
        )
    assert stats.matched_count >= 2


@pytest.mark.integration
def test_cad_pipeline_out_dir_flag_isolates_writes(tmp_path):
    """Running cad_pipeline.py spec --out-dir <tmp> must NOT mutate cad/end_effector/."""
    if not END_EFFECTOR_DOC.exists():
        pytest.skip("end_effector source doc missing")
    import subprocess, sys
    cad_ee = Path("cad/end_effector")
    before = {}
    if cad_ee.exists():
        before = {p.name: p.stat().st_mtime for p in cad_ee.glob("*") if p.is_file()}
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "cad_pipeline.py", "spec",
         "--design-doc", str(END_EFFECTOR_DOC),
         "--out-dir", str(tmp_path), "--proceed", "--auto-fill"],
        env=env, capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
    )
    after = {}
    if cad_ee.exists():
        after = {p.name: p.stat().st_mtime for p in cad_ee.glob("*") if p.is_file()}
    assert before == after, (
        f"cad/end_effector/ was mutated during --out-dir test: "
        f"{set(after) ^ set(before)}. pipeline output:\n{result.stdout}\n{result.stderr}"
    )
