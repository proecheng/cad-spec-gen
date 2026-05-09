"""jury_loop 包测试公共 fixture。"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixture_dir() -> Path:
    """测试 fixtures 目录。"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_reason_plastic_flat() -> str:
    """jury reason 含 plastic_look + flat_light 两 tag。"""
    return "plastic look, flat lighting"


@pytest.fixture
def builtin_yaml_path() -> Path:
    """内置 photoreal_v1.yaml 路径。"""
    from importlib.resources import files

    return Path(str(files("tools.jury_loop.rules") / "photoreal_v1.yaml"))
