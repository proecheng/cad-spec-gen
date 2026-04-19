"""sw_preflight/io.py 测试 — 装配体检测 + 等关闭轮询（Task 9）。

本文件只覆盖 Task 9 范围：
- `_count_open_assemblies()`：用 mock 打桩，不测真 COM
- `wait_for_assembly_close(timeout_sec, poll_interval)` 的轮询语义

tkinter dialog / STEP 校验属 Task 10/11 范围，不在此文件测。

一条 @requires_solidworks 测试在真机跑（conftest.py 自动 skip 无 SW 环境），
命令 `-m "not requires_solidworks"` 下应显示为 deselect。
"""

from unittest.mock import patch

import pytest


@pytest.mark.requires_solidworks
def test_wait_for_assembly_close_returns_when_no_assembly():
    """真机测试：当前 SW 无装配体打开 → 立即返回 True。

    本测试依赖真装 SolidWorks 且当前无装配体窗口；conftest 的
    pytest_collection_modifyitems 钩子会在非 Windows / 无 SW / 无 pywin32
    环境下自动 skip，因此本地 CI mock 通道不会跑到这里。
    """
    from sw_preflight.io import wait_for_assembly_close

    result = wait_for_assembly_close(timeout_sec=2)
    assert result is True


def test_wait_for_assembly_close_mock_assembly_then_close():
    """有装配体 → 轮询到装配体关闭后返回 True。

    mock `_count_open_assemblies` 的 side_effect 模拟前两次探测有 1 个装配体
    打开、第三次探测已关闭；`wait_for_assembly_close` 应在轮询第三次后返回。
    """
    from sw_preflight import io

    states = ["has_assembly", "has_assembly", "no_assembly"]
    with patch.object(
        io,
        "_count_open_assemblies",
        side_effect=lambda: 0 if states.pop(0) == "no_assembly" else 1,
    ):
        result = io.wait_for_assembly_close(timeout_sec=10, poll_interval=0.01)
        assert result is True


def test_wait_for_assembly_close_timeout():
    """一直有装配体打开 → 到 timeout 后返回 False。

    mock 让每次 poll 都返回 1（始终 1 个装配体打开），timeout=0.05s /
    poll_interval=0.01s，预期轮询几次后因超时退出返回 False。
    """
    from sw_preflight import io

    with patch.object(io, "_count_open_assemblies", return_value=1):
        result = io.wait_for_assembly_close(timeout_sec=0.05, poll_interval=0.01)
        assert result is False
