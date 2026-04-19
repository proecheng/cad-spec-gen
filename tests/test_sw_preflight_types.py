"""Task 2 — sw_preflight/types.py 的 TDD 测试"""
import pytest
import dataclasses
from sw_preflight.types import (
    PartCategory, PreflightResult, BomDryRunResult, RowOutcome,
    UserChoiceResult, FixRecord
)


def test_part_category_has_9_members():
    expected = {'STANDARD_FASTENER', 'STANDARD_BEARING', 'STANDARD_SEAL',
                'STANDARD_LOCATING', 'STANDARD_ELASTIC', 'STANDARD_TRANSMISSION',
                'STANDARD_OTHER', 'VENDOR_PURCHASED', 'CUSTOM'}
    assert {m.name for m in PartCategory} == expected


def test_preflight_result_frozen():
    r = PreflightResult(passed=True, sw_info=None, fixes_applied=[],
                        diagnosis=None, per_step_ms={'detect': 12.3})
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.passed = False


def test_row_outcome_has_category():
    o = RowOutcome(bom_row={'name_cn': 'M6'}, category=PartCategory.STANDARD_FASTENER,
                   expected_adapter='sw_toolbox', actual_adapter='sw_toolbox',
                   status='✅', diagnosis=None)
    assert o.category == PartCategory.STANDARD_FASTENER


def test_fix_record_fields():
    f = FixRecord(action='enable_addin', before_state='disabled',
                  after_state='enabled', elapsed_ms=820.5)
    assert f.elapsed_ms == 820.5


def test_bom_dry_run_result_lists():
    r = BomDryRunResult(total_rows=0, hit_rows=[], missing_rows=[], stand_in_rows=[])
    assert r.total_rows == 0


def test_user_choice_result_sets():
    r = UserChoiceResult(provided_files={}, stand_in_keys=set(), skipped_keys=set())
    assert r.skipped_keys == set()
