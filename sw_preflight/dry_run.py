"""BOM 干跑 — 给每行打 hit/missing/stand_in 标记，不触发任何 COM / 重图形。

Task 21：本模块是 sw-preflight 装即用体验的 BOM 层验收器。
  - 输入：BOM 行 dict 列表
  - 输出：BomDryRunResult（three-way 分类）
  - 约束：不做重计算、不 import cq / SolidWorks、不写盘

调用链：
  dry_run_bom(rows) → PartsResolver.resolve(PartQuery) → RowOutcome → BomDryRunResult
"""
from typing import Optional

from sw_preflight.diagnosis import DiagnosisCode, DiagnosisInfo
from sw_preflight.types import BomDryRunResult, PartCategory, RowOutcome


def _to_part_query(row: dict):
    """dict → PartQuery（5 个必填字段给默认空串，避免 TypeError）。

    真实使用中 BOM 行会来自 BomReader，5 字段必然齐全；此处容错是为了
    让 dry-run 对缺字段行不抛异常 —— missing 行本身就应该走 warn 路径。
    """
    from parts_resolver import PartQuery
    return PartQuery(
        part_no=row.get('part_no', ''),
        name_cn=row.get('name_cn', ''),
        material=row.get('material', ''),
        category=row.get('category', ''),
        make_buy=row.get('make_buy', ''),
    )


def _expected_adapter_for_category(cat: PartCategory) -> str:
    """按 PartCategory 推断期望 adapter（用于判断"是否走了期望路径"）。

    规则（与 plan §8 BOM 路由一致）：
      - 紧固件 / 轴承：走 sw_toolbox
      - 外购件：走 step_pool（vendor STEP 文件池）
      - 自制件：走 jinja_primitive（参数化原语）
      - 其它 STANDARD_*（密封 / 定位 / 弹性 / 传动 / 其它）：兜底 sw_toolbox
    """
    if cat in (PartCategory.STANDARD_FASTENER, PartCategory.STANDARD_BEARING):
        return 'sw_toolbox'
    if cat == PartCategory.VENDOR_PURCHASED:
        return 'step_pool'
    if cat == PartCategory.CUSTOM:
        return 'jinja_primitive'
    return 'sw_toolbox'  # 其它 STANDARD_* 兜底期望 SW（SEAL / LOCATING / 等）


def _status_from_resolve(res) -> str:
    """判状态：success=False → ⚠️（fell through）；adapter 不符期望 → ⚠️；否则 ✅。

    注：`success` 是测试 mock 暴露的标志，真实 ResolveResult 用 status
    字段（"hit"/"miss"/"fallback"）；通过 getattr 兜底让两种场景都走通。
    """
    if not getattr(res, 'success', True):
        return '⚠️'
    if res.adapter == _expected_adapter_for_category(res.category):
        return '✅'
    return '⚠️'


def _diagnosis_from_resolve(res) -> Optional[DiagnosisInfo]:
    """走 fallback adapter 时给 warn 级诊断，指引用户改用三选一。"""
    if _status_from_resolve(res) == '⚠️':
        return DiagnosisInfo(
            code=DiagnosisCode.BOM_ROW_FELL_THROUGH_TO_STAND_IN,
            reason=f"未命中期望 adapter，走 {res.adapter}",
            suggestion="可在三选一中指定 STEP 文件提升精度",
            severity='warn',
        )
    return None


def dry_run_bom(bom_rows: list[dict]) -> BomDryRunResult:
    """走 PartsResolver 一遍，给每行打三分类标签；不触发 COM / 重图形 / 生成文件。

    注：此处 PartsResolver() 是空注册表实例 —— 测试里 resolve 被 patch 不受
    影响，但真实运行时命中率会是 0%。plan 约束本函数为零参数入口；真实
    路径依赖下游 CHECKPOINT 5 的 orchestrator 通过依赖注入传 default_resolver()
    进来——不在本 task 范围。
    """
    from parts_resolver import PartsResolver
    resolver = PartsResolver()
    hit, missing, stand_in = [], [], []
    for row in bom_rows:
        query = _to_part_query(row)
        res = resolver.resolve(query)
        outcome = RowOutcome(
            bom_row=row,
            category=res.category,
            expected_adapter=_expected_adapter_for_category(res.category),
            actual_adapter=res.adapter,
            status=_status_from_resolve(res),
            diagnosis=_diagnosis_from_resolve(res),
        )
        if outcome.status == '✅':
            hit.append(outcome)
        elif outcome.status == '⚠️':
            stand_in.append(outcome)
        else:
            missing.append(outcome)
    return BomDryRunResult(
        total_rows=len(bom_rows),
        hit_rows=hit,
        missing_rows=missing,
        stand_in_rows=stand_in,
    )
