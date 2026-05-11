"""CP-7 Task 7.1.0：`should_skip_jury_loop_for_view` 单元测试（OPS-MAJOR-3 fast-path）。

漂移修正（rev 2）：sidecar 文件名是 `<view>_enhance_meta.json`（orchestrator 实际写出，spec §4.4），
键是 `loop_status` 枚举（spec §4.6），不是布尔 `delivered_retry`。fast-path skip-set 见 spec §6.2。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jury_loop.sidecar_skip import should_skip_jury_loop_for_view


def _write_meta(render_dir: Path, view: str, loop_status: str | None) -> Path:
    """写一份最小 `<view>_enhance_meta.json`；loop_status=None 时不写该键。"""
    payload: dict[str, object] = {"$schema_version": 1, "view": view}
    if loop_status is not None:
        payload["loop_status"] = loop_status
    sidecar = render_dir / f"{view}_enhance_meta.json"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    return sidecar


# ── 已成功交付 / 持久失败 → fast-path skip（rerun=False） ──────────────────


@pytest.mark.parametrize(
    "loop_status",
    ["delivered_retry", "delivered_baseline", "above_threshold",
     "retry_auth_failed", "retry_quota_exceeded"],
)
def test_skip_true_for_terminal_statuses(tmp_path: Path, loop_status: str) -> None:
    """已成功交付（delivered_*/above_threshold）+ 持久失败（auth/quota）→ 默认跳过。"""
    _write_meta(tmp_path, "V1", loop_status)
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is True


# ── 临时失败 → 默认仍重试（不进 fast-path） ─────────────────────────────────


@pytest.mark.parametrize(
    "loop_status",
    ["jury_unavailable", "retry_rate_limited", "retry_failed",
     "cost_capped", "loop_disabled", "empty_reason", "no_tags_parsed"],
)
def test_skip_false_for_transient_statuses(tmp_path: Path, loop_status: str) -> None:
    """临时/可恢复状态 → 不跳过（上次失败这次再试；cost_capped 走新 LoopBudget）。"""
    _write_meta(tmp_path, "V1", loop_status)
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is False


# ── --rerun-loop 强制重跑 ──────────────────────────────────────────────────


def test_rerun_loop_forces_no_skip_even_for_terminal(tmp_path: Path) -> None:
    """已 delivered_retry sidecar + rerun=True → 强制重跑（不跳过）。"""
    _write_meta(tmp_path, "V1", "delivered_retry")
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=True) is False


# ── 缺失 / 损坏 / 不可读 / 缺键 → 不跳过（容错重跑） ───────────────────────


def test_skip_false_when_no_sidecar(tmp_path: Path) -> None:
    """无 sidecar 文件 → 不跳过（首次跑）。"""
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is False


def test_skip_false_when_sidecar_corrupt(tmp_path: Path) -> None:
    """sidecar 非 JSON（损坏）→ 不跳过（容错重跑）。"""
    (tmp_path / "V1_enhance_meta.json").write_text("{not json", encoding="utf-8")
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is False


def test_skip_false_when_sidecar_unreadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """sidecar read 抛 OSError → 不跳过（容错重跑）。"""
    _write_meta(tmp_path, "V1", "delivered_retry")
    real_read_text = Path.read_text

    def _raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "V1_enhance_meta.json":
            raise OSError("simulated I/O error")
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", _raise_oserror)
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is False


def test_skip_false_when_loop_status_missing(tmp_path: Path) -> None:
    """sidecar 存在但缺 loop_status 键 → 不跳过。"""
    _write_meta(tmp_path, "V1", None)
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is False
