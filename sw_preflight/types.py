"""数据类型"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sw_preflight.diagnosis import DiagnosisInfo


class PartCategory(Enum):
    """零件分类枚举"""
    STANDARD_FASTENER = 'standard_fastener'
    STANDARD_BEARING = 'standard_bearing'
    STANDARD_SEAL = 'standard_seal'
    STANDARD_LOCATING = 'standard_locating'
    STANDARD_ELASTIC = 'standard_elastic'
    STANDARD_TRANSMISSION = 'standard_transmission'
    STANDARD_OTHER = 'standard_other'
    VENDOR_PURCHASED = 'vendor_purchased'
    CUSTOM = 'custom'


@dataclass(frozen=True)
class FixRecord:
    """记录单次自动修复动作及其结果"""
    action: str
    before_state: str
    after_state: str
    elapsed_ms: float


@dataclass(frozen=True)
class PreflightResult:
    """整体预检结果载体"""
    passed: bool
    sw_info: Any  # 来自 adapters/solidworks/sw_detect.SwInfo（避免循环 import 用 Any）
    fixes_applied: list[FixRecord]
    diagnosis: Optional['DiagnosisInfo']
    per_step_ms: dict[str, float]
    advisory_failures: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RowOutcome:
    """BOM 单行匹配结果"""
    bom_row: dict
    category: PartCategory
    expected_adapter: str
    actual_adapter: str
    status: Literal['✅', '⚠️', '❌']
    diagnosis: Optional['DiagnosisInfo']


@dataclass(frozen=True)
class BomDryRunResult:
    """BOM 干跑汇总结果"""
    total_rows: int
    hit_rows: list[RowOutcome]
    missing_rows: list[RowOutcome]
    stand_in_rows: list[RowOutcome]


@dataclass(frozen=True)
class UserChoiceResult:
    """用户手动提供文件的选择结果"""
    provided_files: dict[str, Path]
    stand_in_keys: set[str]
    skipped_keys: set[str]
