"""BOM 分类器新增 elastic / transmission 类别规则测试。

import 说明：pytest 根据 pyproject.toml testpaths=["tests"] 运行，conftest.py
将 src/ 加入 sys.path，pytest rootdir（项目根）也在 sys.path，
所以 `from bom_parser import ...` 直接引用根目录的 bom_parser.py。
"""

from __future__ import annotations

from bom_parser import classify_part


def test_rubber_spring_elastic() -> None:
    """橡胶弹簧应归类为 elastic。"""
    assert classify_part("橡胶弹簧") == "elastic"


def test_leaf_spring_elastic() -> None:
    """板弹簧应归类为 elastic。"""
    assert classify_part("板弹簧 120×30×3mm") == "elastic"


def test_gear_transmission() -> None:
    """齿轮应归类为 transmission。"""
    assert classify_part("齿轮 m=1 z=20") == "transmission"


def test_sprocket_transmission() -> None:
    """链轮应归类为 transmission。"""
    assert classify_part("链轮 GB") == "transmission"


def test_pulley_transmission() -> None:
    """皮带轮应归类为 transmission。"""
    assert classify_part("皮带轮 Φ60") == "transmission"


def test_timing_belt_stays_cable() -> None:
    """同步带 GT2 不被 transmission 误捕（cable 规则含"同步带"/"皮带"）。"""
    assert classify_part("同步带 GT2") == "cable"


def test_spring_washer_stays_spring() -> None:
    """弹性垫圈不被 elastic 误捕（spring 规则在前且含"弹性垫圈"）。"""
    assert classify_part("弹性垫圈 M6") == "spring"


def test_bare_coupler_stays_connector() -> None:
    """裸联轴器归 connector（first-match 且 connector 规则含"联轴器"）。"""
    assert classify_part("联轴器 L070") == "connector"


def test_elastic_coupling_stays_connector() -> None:
    """弹性联轴器也归 connector（connector 规则含"联轴器"和"L050"，排在 elastic 前）。"""
    assert classify_part("弹性联轴器 L050") == "connector"
