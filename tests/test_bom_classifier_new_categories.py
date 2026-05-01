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


def test_timing_belt_is_transmission() -> None:
    """GT2 同步带是机械传动件，不应按线缆跳过。"""
    assert classify_part("同步带 GT2") == "transmission"


def test_gt2_belt_is_transmission() -> None:
    """型号写法里的 GT2 belt 也应归入 transmission。"""
    assert classify_part("GT2-310-6mm 带") == "transmission"


def test_spring_washer_stays_spring() -> None:
    """弹性垫圈不被 elastic 误捕（spring 规则在前且含"弹性垫圈"）。"""
    assert classify_part("弹性垫圈 M6") == "spring"


def test_bare_coupler_is_transmission() -> None:
    """联轴器属于机械传动链，不能按电气 connector 处理。"""
    assert classify_part("联轴器 L070") == "transmission"


def test_elastic_coupling_is_transmission() -> None:
    """弹性联轴器也属于机械传动链。"""
    assert classify_part("弹性联轴器 L050") == "transmission"


def test_t16_lead_screw_nut_is_transmission() -> None:
    """T16 丝杠螺母是升降机构功能件，不是紧固螺母。"""
    assert classify_part("T16 螺母 C7") == "transmission"


def test_timing_belt_guard_is_not_skipped_as_cable_or_fastener() -> None:
    """同步带护罩是可视自制件，不能落入 cable/fastener 跳过类。"""
    assert classify_part("同步带护罩") not in {"cable", "fastener"}
