"""sw-warmup 核心实现（v4 §7 + 决策 #26）。

模块只暴露 run_sw_warmup(args) → int 主入口，
acquire_warmup_lock(lock_path) context manager 给单元测试单独覆盖。
"""

from __future__ import annotations

import contextlib
import csv
import logging
import os
from pathlib import Path
from typing import Iterator

from parts_resolver import PartQuery

log = logging.getLogger(__name__)

# 全局状态：追踪当前进程已持有的锁（同进程内防止重复 acquire）
_held_locks: set[str] = set()


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
                    raw, seen_normalized[normalized], normalized,
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
    """独占进程锁（决策 #26）。Windows 用 msvcrt，其他平台 fcntl。

    Args:
        lock_path: 锁文件绝对路径，父目录会被自动创建

    Yields:
        None — with 块内代表已持锁

    Raises:
        RuntimeError: 已被另一进程占用（带 PID 提示）
    """
    lock_path = Path(lock_path)
    lock_path_str = str(lock_path.resolve())

    # 同进程内重复 acquire 检查
    if lock_path_str in _held_locks:
        pid = os.getpid()
        raise RuntimeError(f"另一个 sw-warmup 进程运行中 (PID {pid})")

    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # 确保文件存在，以便 lock 操作
    if not lock_path.exists():
        lock_path.write_text(str(os.getpid()))

    fh = open(lock_path, "a+")
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                fh.close()
                pid = lock_path.read_text(encoding="utf-8").strip() or "未知"
                raise RuntimeError(f"另一个 sw-warmup 进程运行中 (PID {pid})") from e
        else:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as e:
                fh.close()
                pid = lock_path.read_text(encoding="utf-8").strip() or "未知"
                raise RuntimeError(f"另一个 sw-warmup 进程运行中 (PID {pid})") from e

        # 记录为已持有
        _held_locks.add(lock_path_str)

        # 持锁后写入当前 PID 供下个尝试者诊断（spec 要求）
        # 用 seek(0)+truncate 保证清掉 bootstrap 写入的旧值
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(str(os.getpid()))
            fh.flush()
        except OSError as e:
            log.debug("写入 PID 异常（忽略）: %s", e)

        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError as e:
                    log.debug("释放 msvcrt 锁异常（忽略）: %s", e)
            else:
                import fcntl

                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError as e:
                    log.debug("释放 fcntl 锁异常（忽略）: %s", e)

            # 移除持有标记
            _held_locks.discard(lock_path_str)
    finally:
        fh.close()
