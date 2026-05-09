"""sw-warmup 核心实现（v4 §7 + 决策 #26）。

模块只暴露 run_sw_warmup(args) → int 主入口，
acquire_warmup_lock(lock_path) context manager 给单元测试单独覆盖。
"""

from __future__ import annotations

import contextlib
import csv
import logging
from pathlib import Path
from typing import Iterator

from parts_resolver import PartQuery
from tools._file_lock import LockBusy, acquire_lock

log = logging.getLogger(__name__)


class WarmupLockContentionError(RuntimeError):
    """另一 sw-warmup 进程持有锁；调用方应返回 exit 3 而非 1。

    PID 作为结构化属性暴露，未来 sw-inspect 子命令（P2）可以直接
    `exc.pid` 读取，无需 `re.match(r"PID (\\d+)", str(exc))` 反解字符串。

    Task 1 重构后：进程锁实现已下沉到 tools/_file_lock.py（jury 共用）；
    acquire_warmup_lock 仍保留 WarmupLockContentionError 作为外部 API
    抛出类型，转发器把内部 LockBusy 转换为本异常以保旧契约不变。
    """

    _MSG_FMT = "另一个 sw-warmup 进程运行中 (PID {pid})"

    def __init__(self, pid: str):
        super().__init__(self._MSG_FMT.format(pid=pid))
        self.pid: str = pid


# 列名别名表（值为标准化后的字段名，键为 BOM CSV 中可能出现的列名小写）
BOM_COLUMN_ALIASES = {
    "part_no": "part_no",
    "partno": "part_no",
    "部件号": "part_no",
    "零件号": "part_no",
    "name_cn": "name_cn",
    "namecn": "name_cn",
    "名称": "name_cn",
    "中文名": "name_cn",
    "material": "material",
    "材料": "material",
    "材质": "material",
    "category": "category",
    "类别": "category",
    "分类": "category",
    "make_buy": "make_buy",
    "makebuy": "make_buy",
    "外购自制": "make_buy",
}

REQUIRED_BOM_FIELDS = ("part_no", "name_cn", "material", "category")


def read_bom_csv(csv_path: Path) -> list[PartQuery]:
    """读取 BOM CSV 并返回 PartQuery 列表（spec §7）。

    支持中英文列名别名（见 BOM_COLUMN_ALIASES），大小写不敏感。
    缺必需列时抛 ValueError；可选列 make_buy 缺失时填空字符串。

    Args:
        csv_path: BOM CSV 文件路径，UTF-8 编码

    Returns:
        PartQuery 列表，每行一个

    Raises:
        ValueError: 缺必需列
        OSError: 文件读取失败
    """
    # encoding="utf-8-sig" 自动剥离 Excel/LibreOffice 导出 CSV 的 UTF-8 BOM
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"BOM CSV 无表头: {csv_path}")

        # 列名标准化（小写 + 别名映射）
        col_map: dict[str, str] = {}
        seen_normalized: dict[str, str] = {}  # normalized → first raw key
        for raw in reader.fieldnames:
            normalized = BOM_COLUMN_ALIASES.get(raw.strip().lower())
            if normalized is None:
                continue
            if normalized in seen_normalized:
                log.warning(
                    "BOM 列名 %r 与 %r 都映射到 %r，后者覆盖前者（数据可能丢失）",
                    raw,
                    seen_normalized[normalized],
                    normalized,
                )
            seen_normalized[normalized] = raw
            col_map[raw] = normalized

        # 必需列检查
        present = set(col_map.values())
        missing = [f for f in REQUIRED_BOM_FIELDS if f not in present]
        if missing:
            raise ValueError(
                f"BOM CSV 缺必需列: {missing}（已识别: {sorted(present)}）"
            )

        rows: list[PartQuery] = []
        for raw_row in reader:
            mapped = {col_map[k]: v for k, v in raw_row.items() if k in col_map}
            rows.append(
                PartQuery(
                    part_no=mapped.get("part_no", "").strip(),
                    name_cn=mapped.get("name_cn", "").strip(),
                    material=mapped.get("material", "").strip(),
                    category=mapped.get("category", "").strip(),
                    make_buy=mapped.get("make_buy", "").strip(),
                )
            )
        return rows


@contextlib.contextmanager
def acquire_warmup_lock(lock_path: Path) -> Iterator[None]:
    """独占进程锁（决策 #26）。

    Task 1 重构后：转发到 tools/_file_lock.acquire_lock（jury 共用通用锁）。
    把内部 LockBusy 翻译为既有 WarmupLockContentionError，保留外部 API 契约
    （RuntimeError 子类 + .pid 结构化属性 + "另一个 sw-warmup 进程" 文案）。

    行为差异说明：
    - 旧实现用 OS-level msvcrt/fcntl 锁；新实现用 JSON sidecar + PID liveness +
      30 分钟 mtime stale 自动清理。两种方案都达到"另一进程并发抢锁失败"的契约。
    - LockBusy.pid 是 int；翻译时统一转 str 以匹配旧契约（exc.pid 是 str）。

    Args:
        lock_path: 锁文件绝对路径，父目录会被自动创建

    Yields:
        None — with 块内代表已持锁

    Raises:
        WarmupLockContentionError: 已被另一进程占用（带 PID 提示）
    """
    try:
        with acquire_lock(Path(lock_path)):
            yield
    except LockBusy as e:
        raise WarmupLockContentionError(pid=str(e.pid)) from e


def _default_lock_path() -> Path:
    """默认锁文件位置 ~/.cad-spec-gen/sw_warmup.lock。"""
    return Path.home() / ".cad-spec-gen" / "sw_warmup.lock"


def _default_error_log_path() -> Path:
    """默认错误日志位置 ~/.cad-spec-gen/sw_warmup_errors.log。"""
    return Path.home() / ".cad-spec-gen" / "sw_warmup_errors.log"


def _print_preflight_failure(reason: str) -> None:
    """前置检查失败的统一打印格式。"""
    print(f"[sw-warmup] 前置检查失败：{reason}")


def _check_preflight() -> tuple[bool, str]:
    """前置检查。返回 (ok, reason)。

    SW-B0 spike 实证：Toolbox Library add-in 不是 sldprt→STEP 转换的
    必要条件。若该 add-in 未启用，仅打印 warning（见 _run_warmup_locked），
    不阻断 warmup。
    """
    from adapters.solidworks.sw_detect import detect_solidworks

    info = detect_solidworks()
    if not info.installed:
        return False, "未检测到 SolidWorks 安装；本命令需要本机已装 SolidWorks ≥2024"
    if (info.version_year or 0) < 2024:
        return False, f"SolidWorks 版本 {info.version_year} < 2024；请升级"
    if not info.pywin32_available:
        return False, (
            "pywin32 未安装；请运行 "
            "`pip install 'cad-spec-gen[solidworks]'`（Windows only）"
        )
    if not info.toolbox_dir:
        return False, "未检测到 Toolbox 目录；检查 SW 安装完整性"
    import psutil  # 局部 import，与 msvcrt/fcntl 惯例一致

    sw_running = any(
        (p.info.get("name") or "").upper() == "SLDWORKS.EXE"
        for p in psutil.process_iter(["name"])
    )
    if not sw_running:
        return False, (
            "SolidWorks 未运行；请先打开 SolidWorks，"
            "再运行 sw-warmup（COM 转换需要 SW 进程已就绪）"
        )
    return True, ""


def run_sw_warmup(args) -> int:
    """sw-warmup 主入口（v4 §7）。

    Returns:
        0 成功 / 1 部分失败 / 2 前置失败 / 3 锁争用（另一实例在运行）
    """
    try:
        with acquire_warmup_lock(_default_lock_path()):
            if args.smoke_test:
                return _run_smoke_test()
            return _run_warmup_locked(args)
    except WarmupLockContentionError as e:
        print(f"[sw-warmup] {e}")
        return 3
    except RuntimeError as e:
        # 其它 RuntimeError 仍按"部分失败"处理，保持既有行为
        print(f"[sw-warmup] {e}")
        return 1


def _select_targets_by_standard(index: dict, standards_csv: str | None) -> list:
    """按 --standard / --all 选 sldprt 候选。返回 [SwToolboxPart] 列表。

    standards_csv 为 None 时返回全部（--all 路径）；非 None 时按逗号切分大写后过滤。
    """
    from adapters.solidworks.sw_toolbox_catalog import SwToolboxPart

    standards_filter: set[str] | None = None
    if standards_csv:
        standards_filter = {s.strip().upper() for s in standards_csv.split(",")}

    targets: list[SwToolboxPart] = []
    for std_name, sub_dict in index.get("standards", {}).items():
        if standards_filter is not None and std_name.upper() not in standards_filter:
            continue
        for parts in sub_dict.values():
            targets.extend(parts)
    return targets


def _convert_one(
    part, cache_root: Path, session, overwrite: bool
) -> tuple[bool, float, str]:
    """调用 session 转换单个 part；返回 (success, elapsed_sec, message)。"""
    import time

    step_relative = (
        Path(part.standard) / part.subcategory / (Path(part.filename).stem + ".step")
    )
    step_abs = cache_root / step_relative

    if step_abs.exists() and not overwrite:
        return True, 0.0, "已缓存"

    t0 = time.monotonic()
    ok = session.convert_sldprt_to_step(part.sldprt_path, str(step_abs))
    elapsed = time.monotonic() - t0
    return ok, elapsed, ("OK" if ok else "FAIL")


def _resolve_bom_targets(bom_path: Path, registry: dict) -> dict:
    """读 BOM → 复用 SwToolboxAdapter.find_sldprt 找匹配 sldprt。
    返回 {part_no: SwToolboxPart}（找不到的行被跳过 + warning）。
    """
    from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter

    queries = read_bom_csv(bom_path)
    adapter = SwToolboxAdapter(config=registry.get("solidworks_toolbox", {}))
    out: dict = {}
    for q in queries:
        spec = {"standard": ["GB", "ISO", "DIN"], "part_category": q.category}
        match = adapter.find_sldprt(q, spec)
        if match is None:
            log.warning("BOM 行未匹配到 sldprt: %s (%s)", q.part_no, q.name_cn)
            continue
        part, _score = match
        if q.part_no in out:
            log.warning("BOM 重复 part_no 覆盖: %s（后者生效）", q.part_no)
        out[q.part_no] = part
    return out


def _run_smoke_test() -> int:
    """单件 smoke test：取 GB/bearing 第一个件做转换验收。"""
    import shutil
    import tempfile

    from adapters.solidworks import sw_toolbox_catalog
    from adapters.solidworks.sw_com_session import get_session
    from adapters.solidworks.sw_detect import detect_solidworks
    from parts_resolver import load_registry

    ok, reason = _check_preflight()
    if not ok:
        _print_preflight_failure(reason)
        return 2

    info = detect_solidworks()
    registry = load_registry()
    sw_cfg = registry.get("solidworks_toolbox", {})
    index_path = sw_toolbox_catalog.get_toolbox_index_path(sw_cfg)
    index = sw_toolbox_catalog.load_toolbox_index(index_path, Path(info.toolbox_dir))

    bearing_parts = index.get("standards", {}).get("GB", {}).get("bearing", [])
    if not bearing_parts:
        print("[sw-warmup] smoke-test FAIL — Toolbox index 无 GB/bearing 件")
        return 2

    part = bearing_parts[0]
    tmp_dir = Path(tempfile.mkdtemp(prefix="sw_smoke_"))
    step_out = str(tmp_dir / "smoke_test.step")

    try:
        session = get_session()
        success = session.convert_sldprt_to_step(part.sldprt_path, step_out)
        if success:
            size_kb = Path(step_out).stat().st_size // 1024
            print(f"[sw-warmup] smoke-test PASS — STEP 文件 {size_kb}KB")
            return 0
        else:
            stderr_tail = (session.last_convert_diagnostics or {}).get(
                "stderr_tail", ""
            )
            print(f"[sw-warmup] smoke-test FAIL — {stderr_tail}")
            return 2
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_warmup_locked(args) -> int:
    """实际 warmup 流程，已持进程锁。"""
    from adapters.solidworks import sw_toolbox_catalog
    from adapters.solidworks.sw_com_session import get_session
    from adapters.solidworks.sw_detect import detect_solidworks
    from parts_resolver import load_registry

    ok, reason = _check_preflight()
    if not ok:
        _print_preflight_failure(reason)
        return 2

    info = detect_solidworks()
    if not info.toolbox_addin_enabled:
        print(
            "[sw-warmup] 警告：SolidWorks Toolbox Library add-in 未启用或未安装；"
            "这对 sldprt→STEP 转换不是必要条件（SW-B0 spike 实证），继续。"
        )
    toolbox_dir = Path(info.toolbox_dir)
    registry = load_registry()
    sw_cfg = registry.get("solidworks_toolbox", {})
    cache_root = sw_toolbox_catalog.get_toolbox_cache_root(sw_cfg)
    index_path = sw_toolbox_catalog.get_toolbox_index_path(sw_cfg)
    index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)

    # 默认 --standard GB（若三个目标参数都缺），不污染 caller 的 args
    selected_standard = args.standard
    if not args.all and not args.standard and not args.bom:
        selected_standard = "GB"

    if args.bom:
        bom_targets = _resolve_bom_targets(Path(args.bom), registry)
        targets = list(bom_targets.values())
    elif args.all:
        targets = _select_targets_by_standard(index, None)
    else:
        targets = _select_targets_by_standard(index, selected_standard)

    print(f"[sw-warmup] 目标 {len(targets)} 个 sldprt")

    if args.dry_run:
        print("[sw-warmup] DRY-RUN 模式，不调 COM；以上即转换计划")
        for p in targets[:20]:
            print(f"  - {p.standard}/{p.subcategory}/{p.filename}")
        if len(targets) > 20:
            print(f"  ...（其余 {len(targets) - 20} 个）")
        return 0

    session = get_session()
    success = 0
    failed = 0
    error_log = _default_error_log_path()
    error_log.parent.mkdir(parents=True, exist_ok=True)

    import time
    from datetime import datetime, timezone

    t_start = time.monotonic()
    for i, part in enumerate(targets, start=1):
        ok, elapsed, msg = _convert_one(part, cache_root, session, args.overwrite)
        symbol = "✓" if ok else "✗"
        print(
            f"[{i}/{len(targets)}] {part.standard}/{part.subcategory}/"
            f"{Path(part.filename).stem}.step  {symbol}  ({elapsed:.1f}s {msg})"
        )
        if ok:
            success += 1
        else:
            failed += 1
            with open(error_log, "a", encoding="utf-8") as f:
                ts = datetime.now(timezone.utc).isoformat()
                f.write(
                    f"{ts}\t{part.standard}/{part.subcategory}/{part.filename}\t{msg}\n"
                )

    t_total = time.monotonic() - t_start
    print(
        f"[sw-warmup] 汇总: 目标 {len(targets)} / 成功 {success} / "
        f"失败 {failed} / 耗时 {t_total / 60:.1f}m"
    )
    return 0 if failed == 0 else 1
