"""sw_preflight/io.py — tkinter.filedialog 包装 + 三选一 prompt 测试（Task 10）。

覆盖：
- ask_step_file 正常取路径（askopenfilename 返回非空字符串）
- ask_step_file 用户取消（askopenfilename 返回空字符串）→ None
- three_choice_prompt 解析 '2' → 'stand_in'
"""
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="tkinter.Tk() 需要 display；产品 Windows-only，CI 跑 Linux 仅为防 import 炸",
)
def test_ask_step_file_returns_path():
    with patch('sw_preflight.io.filedialog.askopenfilename',
               return_value='C:/Users/foo/m6x20.step'):
        from sw_preflight.io import ask_step_file
        result = ask_step_file('为 GB/T 70.1 M6×20 选择 STEP (1/5)')
        assert result == Path('C:/Users/foo/m6x20.step')


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="tkinter.Tk() 需要 display；产品 Windows-only，CI 跑 Linux 仅为防 import 炸",
)
def test_ask_step_file_returns_none_on_cancel():
    with patch('sw_preflight.io.filedialog.askopenfilename', return_value=''):
        from sw_preflight.io import ask_step_file
        assert ask_step_file('test') is None


def test_ask_step_file_returns_none_when_tk_unavailable(monkeypatch):
    from sw_preflight import io

    monkeypatch.setattr(io, "Tk", MagicMock(side_effect=RuntimeError("no tcl")))

    assert io.ask_step_file("test") is None


def test_three_choice_prompt(monkeypatch):
    monkeypatch.setattr('builtins.input', lambda _: '2')
    from sw_preflight.io import three_choice_prompt
    result = three_choice_prompt(missing_count=5)
    assert result == 'stand_in'  # [2] 全部 stand-in
