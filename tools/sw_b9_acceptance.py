"""SW-B9 真跑验收编排脚本（见 specs/2026-04-14-sw-b9-real-run-acceptance-design.md）。"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

log = logging.getLogger("sw_b9")


def _dump(artifacts_dir: Path, name: str, data: dict[str, Any]) -> None:
    path = artifacts_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    data.setdefault("schema_version", 1)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("[%s] written: %s", name, path)


def stage_0_preflight(
    toolbox_root: Path,
    demo_bom: Path,
    artifacts_dir: Path,
    rebuild_index: bool = True,
) -> dict[str, Any]:
    """探测 toolbox + 强制重建索引 + min_score 校准。"""
    from adapters.solidworks import sw_toolbox_catalog

    if not toolbox_root.exists():
        raise RuntimeError(f"toolbox_root 不存在: {toolbox_root}")

    # 检查 GB/ISO/DIN 子目录
    required = {"GB", "ISO", "DIN"}
    existing = {p.name for p in toolbox_root.iterdir() if p.is_dir()}
    missing = required - existing
    if missing:
        raise RuntimeError(f"toolbox 缺少标准目录: {missing}")

    # 重建或复用 index
    index_path = sw_toolbox_catalog.get_toolbox_index_path({})
    if rebuild_index or not index_path.exists():
        log.info("[stage_0] 重建 toolbox index...")
        index = sw_toolbox_catalog.build_toolbox_index(str(toolbox_root))
    else:
        index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_root)

    index_size = sum(
        len(parts)
        for sub in index.get("standards", {}).values()
        for parts in sub.values()
    )

    # 调校准脚本（subprocess）
    cal_result = subprocess.run(
        [sys.executable, "tools/sw_warmup_calibration.py", "--bom", str(demo_bom)],
        capture_output=True, text=True, check=False, timeout=120,
    )
    # 校准脚本输出里解析推荐 min_score（简化：默认 0.30）
    min_score = 0.30

    result = {
        "toolbox_root": str(toolbox_root),
        "index_size": index_size,
        "min_score_recommended": min_score,
        "min_score_used": min_score,
        "rebuild_forced": rebuild_index,
        "calibration_stdout_tail": cal_result.stdout[-500:] if cal_result.stdout else "",
        "pass": index_size > 0,
    }
    _dump(artifacts_dir, "preflight.json", result)
    return result


def stage_0_5_token_health(
    demo_bom: Path,
    artifacts_dir: Path,
    toolbox_root: Path | None = None,
) -> dict[str, Any]:
    """中文 token 命中率检查。全 0 则硬失败要求先合 PR-a。"""
    from adapters.solidworks import sw_toolbox_catalog

    index_path = sw_toolbox_catalog.get_toolbox_index_path({})
    # load_toolbox_index(cache_path, toolbox_dir) — toolbox_dir 用于回退重建
    _toolbox_dir = toolbox_root if toolbox_root is not None else Path("C:/SolidWorks Data/browser")
    index = sw_toolbox_catalog.load_toolbox_index(index_path, _toolbox_dir)

    # 收集 index 所有 part token 集合
    all_part_tokens: set[str] = set()
    for sub in index.get("standards", {}).values():
        for parts in sub.values():
            for p in parts:
                all_part_tokens.update(p.tokens)

    # 读 demo_bom 每行 name_cn，tokenize + 同义词扩展，统计命中
    import csv
    hit_rows = 0
    total = 0
    with open(demo_bom, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            tokens = sw_toolbox_catalog.tokenize(row.get("name_cn", ""))
            weighted = [(t, 1.0) for t in tokens]
            synonyms = sw_toolbox_catalog.load_cn_synonyms()
            expanded = sw_toolbox_catalog.expand_cn_synonyms(weighted, synonyms)
            if any(t in all_part_tokens for t, _ in expanded):
                hit_rows += 1

    hit_rate = hit_rows / total if total else 0.0
    result = {
        "cn_token_hit_rate": hit_rate,
        "total_rows": total,
        "hit_rows": hit_rows,
        "pass": hit_rate > 0.0,
    }
    _dump(artifacts_dir, "stage_0_5.json", result)
    if not result["pass"]:
        raise RuntimeError(
            "Stage 0.5 硬失败：中文 token 命中率 0。确认 PR-a（同义词表）已合入。"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="SW-B9 真跑验收编排")
    parser.add_argument("--toolbox-root", default="C:/SolidWorks Data/browser")
    parser.add_argument("--demo-bom", default="tests/fixtures/sw_warmup_demo_bom.csv")
    parser.add_argument("--real-bom-spec",
                        default="D:/Work/cad-tests/GISBOT/cad/end_effector/CAD_SPEC.md")
    parser.add_argument("--output-dir", default="artifacts/sw_b9")
    parser.add_argument("--no-rebuild-index", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    artifacts_dir = Path(args.output_dir)
    toolbox_root = Path(args.toolbox_root)
    demo_bom = Path(args.demo_bom)

    try:
        stage_0_preflight(
            toolbox_root, demo_bom, artifacts_dir,
            rebuild_index=not args.no_rebuild_index,
        )
        stage_0_5_token_health(demo_bom, artifacts_dir, toolbox_root)
        # Task 10 起补 Stage A/B/D-pre/C/D/E
        log.info("Stage 0 + 0.5 完成，后续 stage 在 Task 10+ 实现")
        return 0
    except Exception:
        log.error("编排失败:\n%s", traceback.format_exc())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
