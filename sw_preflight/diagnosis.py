"""诊断系统 — DiagnosisCode 枚举 + DiagnosisInfo 载体"""
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class DiagnosisCode(Enum):
    """v1 诊断码枚举（16 个）"""
    PLATFORM_NOT_WINDOWS = 'platform_not_windows'
    SW_NOT_INSTALLED = 'sw_not_installed'
    SW_TOOLBOX_NOT_SUPPORTED = 'sw_toolbox_not_supported'
    LICENSE_PROBLEM = 'license_problem'
    COM_REGISTRATION_BROKEN = 'com_registration_broken'
    TOOLBOX_PATH_INVALID = 'toolbox_path_invalid'
    TOOLBOX_PATH_NOT_ACCESSIBLE = 'toolbox_path_not_accessible'
    PYWIN32_MISSING = 'pywin32_missing'
    PYWIN32_INSTALL_FAILED = 'pywin32_install_failed'
    ADDIN_DISABLED = 'addin_disabled'
    MULTIPLE_SW_VERSIONS_AMBIGUOUS = 'multiple_sw_versions_ambiguous'
    INSUFFICIENT_PRIVILEGES = 'insufficient_privileges'
    BOM_ROW_NO_MATCH = 'bom_row_no_match'
    BOM_ROW_FELL_THROUGH_TO_STAND_IN = 'bom_row_fell_through_to_stand_in'
    USER_PROVIDED_SOURCE_HASH_MISMATCH = 'user_provided_source_hash_mismatch'
    USER_PROVIDED_SCHEMA_INVALID = 'user_provided_schema_invalid'


@dataclass(frozen=True)
class DiagnosisInfo:
    """诊断结果载体：诊断码 + 原因 + 建议 + 严重级别"""
    code: DiagnosisCode
    reason: str
    suggestion: str
    severity: Literal['block', 'warn']
