# tests/test_sw_preflight_blocking_checks.py
import pytest


class TestBlockingChecks:
    def test_addin_enabled_not_in_blocking_checks(self):
        """addin_enabled 不在 _BLOCKING_CHECKS → advisory-only。"""
        from sw_preflight.matrix import _BLOCKING_CHECKS
        assert "addin_enabled" not in _BLOCKING_CHECKS

    def test_blocking_checks_contains_platform_and_core(self):
        from sw_preflight.matrix import _BLOCKING_CHECKS
        for name in ("platform", "pywin32", "sw_installed", "toolbox_supported", "com_healthy"):
            assert name in _BLOCKING_CHECKS

    def test_run_all_checks_advisory_failure_doesnt_block(self, monkeypatch):
        """addin_enabled 失败 → run_all_checks passed=True，advisory_failures 非空。"""
        import sw_preflight.matrix as m
        # mock blocking checks → all pass
        for name, attr in m.CHECK_ORDER:
            if name != "addin_enabled":
                monkeypatch.setattr(m, attr, lambda: (True, None))
        # addin_enabled → fail
        monkeypatch.setattr(m, "_check_addin_enabled", lambda: (False, None))

        result = m.run_all_checks()
        assert result["passed"] is True
        assert "addin_enabled" in result.get("advisory_failures", {})

    def test_run_all_checks_blocking_failure_sets_passed_false(self, monkeypatch):
        """blocking check 失败 → passed=False。"""
        import sw_preflight.matrix as m
        for name, attr in m.CHECK_ORDER:
            monkeypatch.setattr(m, attr, lambda: (True, None))
        # com_healthy → fail（blocking）
        monkeypatch.setattr(m, "_check_com_healthy", lambda: (False, None))

        result = m.run_all_checks()
        assert result["passed"] is False

    def test_preflight_result_has_advisory_failures_field(self):
        """PreflightResult 有 advisory_failures 字段，默认空 dict。"""
        from sw_preflight.types import PreflightResult
        r = PreflightResult(
            passed=True, sw_info=None,
            fixes_applied=[], diagnosis=None, per_step_ms={}
        )
        assert hasattr(r, "advisory_failures")
        assert r.advisory_failures == {}
