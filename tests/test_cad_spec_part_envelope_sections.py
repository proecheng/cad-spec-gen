"""Tests for part-envelope extraction from explicit part sections."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_part_section_dimensions_override_visual_reference_sizes():
    from cad_spec_extractors import extract_part_envelopes

    lines = """
## 二、上固定板（Top Plate）— SLP-100

- **外形**：200 × 100 × 8 mm，平面度 <= 0.05 mm
- **Z 向**：板底 Z=+272，板顶 Z=+280

## 三、下固定板（分体式 Bottom Plate）

### 3.1 左支撑条 — SLP-200

- **尺寸**：50 × 100 × 8 mm，Z 范围 [-8, 0]
- **X 范围**：[-85, -35]（中心 X=-60），**Y 范围**：[-50, +50]

### 3.2 右支撑条 — SLP-201

- **尺寸**：50 × 100 × 8 mm，Z 范围 [-8, 0]

## 四、升降台板（动板）— SLP-300

- **外形**：150 × 100 × 8 mm，平面度 <= 0.05 mm
- **Z 范围**：板底有效行程 Z = +43 ~ +235；板顶 = 板底 + 8
""".splitlines()
    visual_ids = [
        {"part": "上固定板 SLP-100", "size": "200×160×8 mm"},
        {"part": "左支撑条 SLP-200", "size": "40×260×15 mm"},
        {"part": "右支撑条 SLP-201", "size": "40×260×15 mm"},
        {"part": "动板 SLP-300", "size": "160×120×8 mm"},
    ]
    bom = {
        "assemblies": [{
            "part_no": "UNKNOWN",
            "parts": [
                {"part_no": "SLP-100", "name": "上固定板"},
                {"part_no": "SLP-200", "name": "左支撑条"},
                {"part_no": "SLP-201", "name": "右支撑条"},
                {"part_no": "SLP-300", "name": "动板"},
            ],
        }],
    }

    envelopes, _ = extract_part_envelopes(lines, bom, visual_ids)

    assert envelopes["SLP-100"]["source"] == "P1:part_section"
    assert envelopes["SLP-100"]["w"] == 200.0
    assert envelopes["SLP-100"]["d"] == 100.0
    assert envelopes["SLP-100"]["h"] == 8.0

    assert envelopes["SLP-200"]["source"] == "P1:part_section"
    assert envelopes["SLP-200"]["w"] == 50.0
    assert envelopes["SLP-200"]["d"] == 100.0
    assert envelopes["SLP-200"]["h"] == 8.0

    assert envelopes["SLP-201"]["source"] == "P1:part_section"
    assert envelopes["SLP-201"]["w"] == 50.0
    assert envelopes["SLP-201"]["d"] == 100.0
    assert envelopes["SLP-201"]["h"] == 8.0

    assert envelopes["SLP-300"]["source"] == "P1:part_section"
    assert envelopes["SLP-300"]["w"] == 150.0
    assert envelopes["SLP-300"]["d"] == 100.0
    assert envelopes["SLP-300"]["h"] == 8.0
