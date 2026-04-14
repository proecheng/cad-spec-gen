"""min_score 阈值校准脚本（v4 决策 #32）。

对 BOM 每行计算 SwToolboxAdapter token 打分分布，输出直方图 + 推荐阈值。
推荐阈值 = max(noise_mean + 2 * noise_std, 0.30)。
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def run_calibration(bom_path: Path) -> int:
    """扫 BOM × Toolbox 打分分布，输出直方图 + 推荐阈值。"""
    from adapters.solidworks import sw_toolbox_catalog
    from adapters.solidworks.sw_detect import detect_solidworks
    from parts_resolver import load_registry
    from tools.sw_warmup import read_bom_csv

    info = detect_solidworks()
    if not info.toolbox_dir:
        print("[calibration] 未检测到 toolbox_dir，无法校准")
        return 1

    toolbox_dir = Path(info.toolbox_dir)
    registry = load_registry()
    sw_cfg = registry.get("solidworks_toolbox", {})
    size_patterns_cfg = sw_cfg.get("size_patterns", {})
    weights = sw_cfg.get("token_weights", {})

    index_path = sw_toolbox_catalog.get_toolbox_index_path(sw_cfg)
    index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
    queries = read_bom_csv(bom_path)

    total_parts = sum(
        len(p) for sub in index["standards"].values() for p in sub.values()
    )
    print(f"[calibration] BOM={bom_path}, 行数 {len(queries)}")
    print(f"[calibration] Toolbox={toolbox_dir}, 索引零件总数 {total_parts}")

    all_top_scores: list[float] = []
    all_other_scores: list[float] = []

    for q in queries:
        # 按 category 选 size pattern（fastener/bearing/...）
        patterns = size_patterns_cfg.get(q.category, {})
        size_dict = sw_toolbox_catalog.extract_size_from_name(q.name_cn, patterns)
        query_tokens = sw_toolbox_catalog.build_query_tokens_weighted(
            q, size_dict or {}, weights
        )

        candidates: list[tuple[str, float]] = []
        for std_name, sub_dict in index.get("standards", {}).items():
            for parts in sub_dict.values():
                for part in parts:
                    part_token_set = set(part.tokens)
                    if not query_tokens or not part_token_set:
                        continue
                    total_w = sum(w for _, w in query_tokens) or 1.0
                    hit_w = sum(w for t, w in query_tokens if t in part_token_set)
                    score = hit_w / total_w
                    candidates.append(
                        (f"{std_name}/{part.subcategory}/{part.filename}", score)
                    )

        candidates.sort(key=lambda x: x[1], reverse=True)
        top3 = candidates[:3]
        print(f"\n[{q.part_no}] {q.name_cn}")
        for name, score in top3:
            print(f"    {score:.3f}  {name}")

        if top3:
            all_top_scores.append(top3[0][1])
            all_other_scores.extend([s for _, s in top3[1:]])

    print("\n─── 直方图 ───")
    bins = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    for low, high in zip(bins[:-1], bins[1:]):
        n_top = sum(1 for s in all_top_scores if low <= s < high)
        n_other = sum(1 for s in all_other_scores if low <= s < high)
        bar = "█" * (n_top + n_other)
        print(f"  [{low:.1f}-{high:.1f}) top1={n_top:3d} other={n_other:3d}  {bar}")

    if all_other_scores:
        noise_mean = statistics.mean(all_other_scores)
        noise_std = (
            statistics.stdev(all_other_scores) if len(all_other_scores) > 1 else 0.0
        )
        recommended = max(noise_mean + 2 * noise_std, 0.30)
    else:
        noise_mean = 0.0
        noise_std = 0.0
        recommended = 0.30

    print(f"\n推荐 min_score: {recommended:.2f}")
    print(f"  (noise_mean={noise_mean:.3f}, noise_std={noise_std:.3f}, 下界 0.30)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SW Toolbox min_score 校准（决策 #32）"
    )
    parser.add_argument("--bom", required=True, type=Path, help="BOM CSV 路径")
    args = parser.parse_args()
    return run_calibration(args.bom)


if __name__ == "__main__":
    sys.exit(main())
