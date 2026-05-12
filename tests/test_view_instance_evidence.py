"""单测 view_instance_evidence.compute_view_visible_instances（render_manifest 逐视角实例证据 — 方案 B bbox-presence）。"""
from tools.view_instance_evidence import compute_view_visible_instances


_VIEWS = ["V1", "V2", "V3"]


def _sig(*instances):
    return {"schema_version": 1, "instances": list(instances)}


def test_lists_instances_with_valid_bbox_uniform_across_views():
    sig = _sig(
        {"instance_id": "A", "bbox_mm": [0.0, 0.0, 0.0, 10.0, 5.0, 2.0]},   # 正常
        {"instance_id": "D", "bbox_mm": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},     # 零退化——故意仍收录（不查退化）
    )
    out = compute_view_visible_instances(sig, _VIEWS)
    assert out is not None
    assert set(out.keys()) == {"V1", "V2", "V3"}
    assert out["V1"] == ["A", "D"]                # 已排序
    assert out["V1"] == out["V2"] == out["V3"]    # 每视角同一份
    assert compute_view_visible_instances(sig, _VIEWS) == out  # 确定性


def test_excludes_invalid_bbox_and_missing_id():
    sig = _sig(
        {"instance_id": "A", "bbox_mm": [0.0, 0.0, 0.0, 10.0, 5.0, 2.0]},
        {"instance_id": "B", "bbox_mm": [0.0, 0.0, 0.0, 10.0, 5.0]},          # 长度≠6
        {"instance_id": "B2", "bbox_mm": [0.0, 0.0, 0.0, float("inf"), 5.0, 2.0]},  # 非有限 (inf)
        {"instance_id": "B2n", "bbox_mm": [0.0, 0.0, 0.0, float("nan"), 5.0, 2.0]}, # 非有限 (nan)
        {"instance_id": "B3", "bbox_mm": "not a list"},                       # 非 list
        {"instance_id": "B3b", "bbox_mm": [0.0, 0.0, 0.0, 1.0, 1.0, True]},   # 含 bool（bool 是 int 子类——必须被排除）
        {"instance_id": "B4"},                                                 # 无 bbox_mm
        {"bbox_mm": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]},                          # 无 instance_id
        {"instance_id": "", "bbox_mm": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]},       # 空 instance_id
        "not a dict",
    )
    out = compute_view_visible_instances(sig, _VIEWS)
    assert out is not None
    assert out["V1"] == ["A"]


def test_returns_none_when_no_instances():
    assert compute_view_visible_instances({}, _VIEWS) is None
    assert compute_view_visible_instances({"instances": "not a list"}, _VIEWS) is None
    assert compute_view_visible_instances("not a dict", _VIEWS) is None  # type: ignore[arg-type]


def test_empty_view_ids_returns_empty_dict():
    sig = _sig({"instance_id": "A", "bbox_mm": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]})
    assert compute_view_visible_instances(sig, []) == {}
