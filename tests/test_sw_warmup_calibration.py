"""sw_warmup_calibration 校准脚本测试（决策 #32）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEMO_BOM = Path(__file__).parent / "fixtures" / "sw_warmup_demo_bom.csv"
FAKE_TOOLBOX = Path(__file__).parent / "fixtures" / "fake_toolbox"


def test_calibration_outputs_recommendation(tmp_path, monkeypatch, capsys):
    """脚本应输出推荐阈值行，且阈值 >= 0.30（决策 #32 下界）。"""
    from adapters.solidworks import sw_detect, sw_toolbox_catalog
    from tools import sw_warmup_calibration as cal

    sw_detect._reset_cache()
    monkeypatch.setattr(
        sw_detect,
        "detect_solidworks",
        lambda: sw_detect.SwInfo(
            installed=True,
            version_year=2024,
            pywin32_available=True,
            toolbox_dir=str(FAKE_TOOLBOX),
            toolbox_addin_enabled=True,
        ),
    )
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "get_toolbox_index_path",
        lambda config: tmp_path / "idx.json",
    )
    monkeypatch.setattr(
        sw_toolbox_catalog,
        "get_toolbox_cache_root",
        lambda config: tmp_path / "cache",
    )
    monkeypatch.setattr(sys, "platform", "win32")

    rc = cal.run_calibration(DEMO_BOM)
    captured = capsys.readouterr()
    assert rc == 0
    assert "推荐 min_score" in captured.out
    # 推荐值能被解析出来（最后一行格式 "推荐 min_score: 0.XX"）
    import re

    m = re.search(r"推荐 min_score:\s*(\d+\.\d+)", captured.out)
    assert m, f"未找到推荐阈值行，输出: {captured.out}"
    threshold = float(m.group(1))
    assert threshold >= 0.30, f"推荐阈值 {threshold} 应 >= 0.30（下界）"
