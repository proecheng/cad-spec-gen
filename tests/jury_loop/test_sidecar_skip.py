"""CP-7 Task 7.1.1：`should_skip_jury_loop_for_view` 单元测试（OPS-MAJOR-3 fast-path）。

`--rerun-loop` 控制：默认 false 时检测既有 sidecar 跳过该视角；true 时强制重跑。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jury_loop.sidecar_skip import should_skip_jury_loop_for_view


def _write_sidecar(render_dir: Path, view: str, payload: dict) -> Path:
    sidecar = render_dir / f"{view}.jury_loop.json"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    return sidecar


def test_should_skip_existing_delivered_retry_default_no_rerun(tmp_path: Path) -> None:
    """已有 delivered_retry sidecar + rerun=False → 跳过（fast-path）。"""
    _write_sidecar(tmp_path, "V1", {"delivered_retry": True, "loop_status": "ok"})
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is True


def test_should_not_skip_when_rerun_loop_force(tmp_path: Path) -> None:
    """已有 delivered_retry sidecar + rerun=True → 强制重跑（不跳过）。"""
    _write_sidecar(tmp_path, "V1", {"delivered_retry": True, "loop_status": "ok"})
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=True) is False


def test_should_not_skip_when_no_sidecar(tmp_path: Path) -> None:
    """无 sidecar → 不跳过（首次跑）。"""
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is False


def test_should_not_skip_when_sidecar_lacks_delivered_retry(tmp_path: Path) -> None:
    """sidecar 存在但无 delivered_retry=true → 不跳过（baseline_kept / jury_unavailable 等需重试场景）。"""
    _write_sidecar(tmp_path, "V1", {"loop_status": "baseline_kept", "delivered_retry": False})
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is False


def test_should_not_skip_when_sidecar_corrupt(tmp_path: Path) -> None:
    """损坏 sidecar（非 JSON）→ 不跳过（容错重跑）。"""
    (tmp_path / "V1.jury_loop.json").write_text("{not json", encoding="utf-8")
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is False


def test_should_not_skip_when_sidecar_unreadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """sidecar read 抛 OSError → 不跳过（容错重跑）。"""
    _write_sidecar(tmp_path, "V1", {"delivered_retry": True})

    real_read_text = Path.read_text

    def _raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "V1.jury_loop.json":
            raise OSError("simulated I/O error")
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", _raise_oserror)
    assert should_skip_jury_loop_for_view("V1", tmp_path, rerun_loop=False) is False
