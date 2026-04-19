"""sw_preflight.preflight — run_preflight 主入口（Task 26）。

编排流水：
  1. ``matrix.run_all_checks()`` 跑 7 项体检；
  2. 首次失败 → ``matrix.try_one_click_fix()`` 尝试一键修；
  3. 修后重跑 check；
  4. 仍异常 → 按 ``strict`` 决定 sys.exit(2) / 温和提示；
  5. 收集 ``SwInfo`` 构造 ``PreflightResult``；
  6. ``run_id`` 非空 → 落 ``artifacts/{run_id}/sw_preflight_cache.json``（供 IPC 判重）。

strict 语义与入口对齐：
  - ``cad-codegen`` 等"真执行"入口使用 strict=True，卡住就退出；
  - ``cad-spec`` 等"编辑辅助"入口使用 strict=False，只打预告不阻塞。
"""
from __future__ import annotations

import sys
import time
from dataclasses import asdict
from pathlib import Path

from sw_preflight import cache, matrix
from sw_preflight.types import FixRecord, PreflightResult


def run_preflight(
    strict: bool = True,
    run_id: str = '',
    entry: str = 'unknown',
) -> PreflightResult:
    """主入口 — 编排 matrix 体检 + 一键修 + cache 落盘。

    Args:
        strict: True 时异常 ``sys.exit(2)``；False 时打 1 行温和提示后继续
            （不阻塞编辑流程，后续真执行入口会再兜底）。
        run_id: ``artifacts/{run_id}/`` 子目录；空字符串则跳过 cache 落盘。
        entry: 入口标识（cad-spec / cad-codegen / cad-enhance），写入 cache
            的 ``ran_by_entry`` 字段供 IPC 判重与排查多入口互相覆盖。

    Returns:
        PreflightResult: 含 passed / sw_info / fixes_applied / diagnosis / per_step_ms。

    Raises:
        SystemExit(2): strict=True 且 matrix 仍异常（一键修后仍失败）。
    """
    per_step: dict[str, float] = {}
    fixes: list[FixRecord] = []

    # 第一步：跑 7 项 check（失败会短路到第一个 failed_check）
    t0 = time.time()
    check = matrix.run_all_checks()
    per_step['detect'] = (time.time() - t0) * 1000

    # 第二步：异常 → 尝试一键修
    if not check['passed']:
        fix = matrix.try_one_click_fix(check['failed_check'], check['diagnosis'])
        if fix is not None:
            fixes.append(fix)
            # 重跑 check（对应的 fix_* 已触发 sw_detect.reset_cache 等清缓存动作）
            t1 = time.time()
            check = matrix.run_all_checks()
            per_step['after_fix_detect'] = (time.time() - t1) * 1000

    # 第三步：仍异常 → 按 strict 决定
    if not check['passed']:
        diag = check['diagnosis']
        if strict:
            print(f"\n❌ {diag.reason if diag else '预检失败'}")
            if diag:
                print(f"   建议: {diag.suggestion}")
            sys.exit(2)
        else:
            print(f"\nℹ️ SW 状态预告: {diag.reason if diag else '预检失败'}")
            print("   后续 cad-codegen 会自动提示修复。当前编辑不受影响。")

    # 第四步：收集 SwInfo（detect 异常吞掉 — 测试 mock / 非 Windows 均兜底为 None）
    try:
        from adapters.solidworks.sw_detect import detect_solidworks
        sw_info = detect_solidworks()
    except Exception:  # noqa: BLE001 — 非关键路径，收集失败不阻塞主结果
        sw_info = None

    result = PreflightResult(
        passed=check['passed'],
        sw_info=sw_info,
        fixes_applied=fixes,
        diagnosis=check['diagnosis'],
        per_step_ms=per_step,
    )

    # 第五步：落 cache（run_id 非空时）
    if run_id:
        cache_path = Path(f'./artifacts/{run_id}/sw_preflight_cache.json')
        # asdict 仅认 dataclass — 测试里 sw_info 可能是 MagicMock 会 TypeError
        try:
            payload = {'preflight_result': asdict(result)}
        except TypeError:
            # 回退：只序列化 dataclass 字段，sw_info 降级为 str(...)
            payload = {
                'preflight_result': {
                    'passed': result.passed,
                    'sw_info': str(result.sw_info),
                    'fixes_applied': [asdict(f) for f in result.fixes_applied],
                    'diagnosis': asdict(result.diagnosis) if result.diagnosis else None,
                    'per_step_ms': result.per_step_ms,
                }
            }
        cache.write_cache(
            cache_path,
            payload,
            ttl_sec=300,
            ran_by_entry=entry,
        )

    return result
