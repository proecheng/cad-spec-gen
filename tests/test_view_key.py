"""Tests for `view_sort_key()` 与 `extract_view_key()`（v2.9.2 Tier 1）。

两个函数都在 `enhance_prompt.py`，分别用于：
- `extract_view_key(png_path, rc=None)`: 从 PNG 文件名（可能含时间戳后缀）
  提取出 config camera 字典里的 key（如 "V1"、"V3"、"FRONT"）
- `view_sort_key(path, rc=None)`: 给 `sorted(...)` 用的 key 函数，保证
  V1、V2、V10 数字顺序正确（不是 lexical V1 < V10 < V2），且 rc 提供的
  相机顺序优先于数字顺序

纯字符串 / 正则处理，无文件 I/O，无 bpy，可直接单测。
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ════════════════════════════════════════════════════════════════════════════
# extract_view_key
# ════════════════════════════════════════════════════════════════════════════


class TestExtractViewKey:
    def test_simple_v1_front_iso(self):
        from enhance_prompt import extract_view_key

        assert extract_view_key("V1_front_iso.png") == "V1"

    def test_strips_timestamp_suffix(self):
        """v2.9.0+ render 文件名带 `_YYYYMMDD_HHMM` 时间戳后缀，仍能提取 V3。"""
        from enhance_prompt import extract_view_key

        assert (
            extract_view_key("V3_side_elevation_20260411_1712.png") == "V3"
        )

    def test_two_digit_view_key_v10(self):
        from enhance_prompt import extract_view_key

        assert extract_view_key("V10_detail.png") == "V10"

    def test_rc_camera_key_takes_precedence(self):
        """若 rc 提供了 camera 字典（如 `FRONT` / `ISO`），优先匹配 config key。"""
        from enhance_prompt import extract_view_key

        rc = {"camera": {"FRONT": {}, "ISO": {}, "V1": {}}}
        assert extract_view_key("FRONT_render.png", rc) == "FRONT"
        assert extract_view_key("ISO_top.png", rc) == "ISO"

    def test_case_insensitive_v_prefix(self):
        """`v1` / `V1` 都应识别为 "V1"（正则 re.IGNORECASE）。"""
        from enhance_prompt import extract_view_key

        assert extract_view_key("v1_lowercase.png") == "V1"


# ════════════════════════════════════════════════════════════════════════════
# view_sort_key
# ════════════════════════════════════════════════════════════════════════════


class TestViewSortKey:
    def test_numeric_order_not_lexical(self):
        """V1 / V2 / V10 必须按数字排序，不能 V1 < V10 < V2 字符串序。"""
        from enhance_prompt import view_sort_key

        paths = ["V10_detail.png", "V2_rear.png", "V1_front.png"]
        assert sorted(paths, key=view_sort_key) == [
            "V1_front.png",
            "V2_rear.png",
            "V10_detail.png",
        ]

    def test_rc_camera_order_overrides_numeric(self):
        """rc 提供的 camera 字典顺序应压过数字顺序 —— config 说 V3 先，就 V3 先。"""
        from enhance_prompt import view_sort_key

        rc = {"camera": {"V3": {}, "V1": {}, "V2": {}}}
        paths = ["V1.png", "V3.png", "V2.png"]
        sorted_paths = sorted(paths, key=lambda p: view_sort_key(p, rc))
        assert sorted_paths == ["V3.png", "V1.png", "V2.png"]

    def test_unknown_files_sort_to_end_alphabetically(self):
        """没有 V\\d+ 的文件落到最后一个 tier，按字母序排。"""
        from enhance_prompt import view_sort_key

        paths = ["misc_shot.png", "V1_front.png", "aaa_generic.png"]
        sorted_paths = sorted(paths, key=view_sort_key)

        # tier 1 (V\d+) 优先
        assert sorted_paths[0] == "V1_front.png"
        # tier 2 alphabetic: aaa_generic < misc_shot
        assert sorted_paths[1] == "aaa_generic.png"
        assert sorted_paths[2] == "misc_shot.png"

    def test_rc_ordered_and_unknown_mixed(self):
        """混合场景：rc 指定的相机走 tier 0，没在 rc 里的 V\\d+ 走 tier 1。"""
        from enhance_prompt import view_sort_key

        rc = {"camera": {"FRONT": {}, "BACK": {}}}  # 只定义了两个 named 相机
        paths = ["V1_extra.png", "FRONT_main.png", "BACK_main.png"]
        sorted_paths = sorted(paths, key=lambda p: view_sort_key(p, rc))

        # FRONT / BACK 先（rc 顺序），V1 后（tier 1）
        assert sorted_paths == [
            "FRONT_main.png",
            "BACK_main.png",
            "V1_extra.png",
        ]
