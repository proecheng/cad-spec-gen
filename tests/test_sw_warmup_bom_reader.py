"""sw_warmup BOM CSV reader 单元测试（spec §7 BOM schema）。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestReadBomCsv:
    """读取 BOM CSV 转 PartQuery 列表，支持中英文列名 + 大小写不敏感。"""

    def test_read_english_columns(self, tmp_path):
        from tools.sw_warmup import read_bom_csv

        csv_path = tmp_path / "bom.csv"
        csv_path.write_text(
            "part_no,name_cn,material,category,make_buy\n"
            "GIS-001,GB/T 70.1 M6 螺钉,钢,fastener,标准\n",
            encoding="utf-8",
        )
        rows = read_bom_csv(csv_path)
        assert len(rows) == 1
        q = rows[0]
        assert q.part_no == "GIS-001"
        assert q.name_cn == "GB/T 70.1 M6 螺钉"
        assert q.material == "钢"
        assert q.category == "fastener"
        assert q.make_buy == "标准"

    def test_read_chinese_column_aliases(self, tmp_path):
        """中文列名（部件号/名称/材料/类别）应正确映射。"""
        from tools.sw_warmup import read_bom_csv

        csv_path = tmp_path / "bom.csv"
        csv_path.write_text(
            "部件号,名称,材料,类别\nGIS-002,深沟球轴承 6205,GCr15,bearing\n",
            encoding="utf-8",
        )
        rows = read_bom_csv(csv_path)
        assert rows[0].part_no == "GIS-002"
        assert rows[0].category == "bearing"

    def test_case_insensitive_column_names(self, tmp_path):
        """大小写不敏感（PART_NO / Part_No / part_no 都接受）。"""
        from tools.sw_warmup import read_bom_csv

        csv_path = tmp_path / "bom.csv"
        csv_path.write_text(
            "Part_No,Name_CN,Material,Category\nGIS-003,M4 螺母,钢,fastener\n",
            encoding="utf-8",
        )
        rows = read_bom_csv(csv_path)
        assert rows[0].part_no == "GIS-003"

    def test_make_buy_optional(self, tmp_path):
        """make_buy 列缺失时给空字符串，不报错。"""
        from tools.sw_warmup import read_bom_csv

        csv_path = tmp_path / "bom.csv"
        csv_path.write_text(
            "part_no,name_cn,material,category\nGIS-004,垫圈,钢,fastener\n",
            encoding="utf-8",
        )
        rows = read_bom_csv(csv_path)
        assert rows[0].make_buy == ""

    def test_missing_required_column_raises(self, tmp_path):
        """缺必需列（part_no/name_cn/material/category）应 raise ValueError。"""
        from tools.sw_warmup import read_bom_csv
        import pytest

        csv_path = tmp_path / "bom.csv"
        csv_path.write_text(
            "part_no,name_cn,material\n"  # 缺 category
            "GIS-005,X,钢\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="category"):
            read_bom_csv(csv_path)
