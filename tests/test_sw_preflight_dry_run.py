"""Task 21 — dry_run_bom 三分类测试

验收 sw_preflight.dry_run.dry_run_bom 对 BOM 4 行的分类能力：
  - 前 3 行 hit（期望 adapter == 实际 adapter）
  - 第 4 行 fall through（success=False）→ stand_in
"""
from unittest.mock import patch, MagicMock

from sw_preflight.types import PartCategory


def test_dry_run_classifies_rows():
    """dry-run 应区分 hit / missing / stand_in 三类"""
    bom = [
        {'name_cn': 'GB/T 70.1 M6×20 内六角', 'category': 'fastener'},
        {'name_cn': 'Maxon ECX SPEED 22L', 'category': ''},
        {'name_cn': '私有件 PXY-2024-A', 'category': ''},
        {'name_cn': '未知件 XXX', 'category': ''},
    ]
    fake_results = [
        MagicMock(category=PartCategory.STANDARD_FASTENER, adapter='sw_toolbox', success=True),
        MagicMock(category=PartCategory.VENDOR_PURCHASED, adapter='step_pool', success=True),
        MagicMock(category=PartCategory.CUSTOM, adapter='jinja_primitive', success=True),
        MagicMock(category=PartCategory.CUSTOM, adapter='step_pool', success=False, fallback='stand_in'),
    ]
    # 偏离 plan 假设：PartsResolver 在仓库根目录 parts_resolver.py，
    # 不在 adapters/parts/ 下 —— patch 路径相应修正为 parts_resolver.PartsResolver.resolve
    with patch('parts_resolver.PartsResolver.resolve', side_effect=fake_results):
        from sw_preflight.dry_run import dry_run_bom
        result = dry_run_bom(bom)
        assert result.total_rows == 4
        assert len(result.hit_rows) == 3  # 前 3 个 hit
        assert len(result.stand_in_rows) == 1  # 第 4 个 fall through → stand_in
