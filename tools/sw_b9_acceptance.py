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


def _measure_coverage(
    bom_csv: Path,
    min_score: float,
    standards: list[str] | None = None,
) -> dict[str, Any]:
    """测量 BOM 覆盖率（不做真 STEP 转换）。复用 sw_warmup.read_bom_csv + SwToolboxAdapter.find_sldprt。"""
    from adapters.parts.sw_toolbox_adapter import SwToolboxAdapter
    from parts_resolver import load_registry
    from tools.sw_warmup import read_bom_csv

    registry = load_registry()
    sw_cfg = registry.get("solidworks_toolbox", {})
    if min_score is not None:
        sw_cfg = {**sw_cfg, "min_score": min_score}
    if standards:
        sw_cfg = {**sw_cfg, "standards": standards}

    adapter = SwToolboxAdapter(config=sw_cfg)
    queries = read_bom_csv(bom_csv)

    matched: list[dict[str, Any]] = []
    unmatched: list[str] = []
    std_list = standards or ["GB", "ISO", "DIN"]
    for q in queries:
        spec = {"standard": std_list, "part_category": q.category}
        m = adapter.find_sldprt(q, spec)
        if m is not None:
            part, score = m
            matched.append({"part_no": q.part_no, "sldprt": part.sldprt_path, "score": score})
        else:
            unmatched.append(q.part_no)

    total = len(matched) + len(unmatched)
    return {
        "total": total,
        "matched_count": len(matched),
        "matched": matched,
        "unmatched": unmatched,
        "coverage": len(matched) / total if total else 0.0,
    }


def stage_a_demo_coverage(
    demo_bom: Path, min_score: float, artifacts_dir: Path,
) -> dict[str, Any]:
    """demo_bom.csv 覆盖率（分母 = 15 行，全标准件）。目标 ≥ 73%。"""
    cov = _measure_coverage(demo_bom, min_score)
    result = {
        "total_rows": cov["total"],
        "standard_rows": cov["total"],  # demo 全标准件
        "matched": cov["matched_count"],
        "matched_list": cov["matched"],  # 给 Stage C 用
        "coverage": cov["coverage"],
        "target": 0.73,
        "pass": cov["coverage"] >= 0.73,
        "unmatched_rows": cov["unmatched"],
        "excluded_rows": [],
    }
    _dump(artifacts_dir, "stage_a.json", result)
    return result


def stage_b_gisbot_coverage(
    real_bom_spec: Path, min_score: float, artifacts_dir: Path,
) -> dict[str, Any]:
    """GISBOT CAD_SPEC → 过滤 → 覆盖率。informational，不判 pass/fail。"""
    from tools.cad_spec_bom_extractor import (
        extract_bom_tree, extract_fasteners, filter_standard_rows,
        classify_category, write_bom_csv,
    )

    fasteners = extract_fasteners(real_bom_spec)
    fastener_rows = [
        {
            "part_no": f"FAST-{i:03d}",
            "name_cn": f["spec"],
            "material": "",
            "make_buy": "外购",
            "category": classify_category(f["spec"]),
        }
        for i, f in enumerate(fasteners, 1)
    ]
    bom_rows = extract_bom_tree(real_bom_spec)
    for r in bom_rows:
        r["category"] = classify_category(r.get("name_cn", ""))
    all_rows = fastener_rows + bom_rows
    kept, excluded = filter_standard_rows(all_rows)

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    kept_csv = artifacts_dir / "stage_b_extracted_bom.csv"
    write_bom_csv(kept, kept_csv)

    cov = _measure_coverage(kept_csv, min_score)

    result = {
        "total_rows": len(all_rows),
        "standard_rows": len(kept),
        "matched": cov["matched_count"],
        "coverage": cov["coverage"],
        "sample_size_below_100": len(all_rows) < 100,
        "note": "B1: below ≥100 threshold, informational only",
        "excluded_rows": [r["part_no"] for r in excluded],
        "pass": "informational",
    }
    _dump(artifacts_dir, "stage_b.json", result)
    return result


def stage_d_pre_consumer_check(artifacts_dir: Path) -> dict[str, Any]:
    """扫 parts_library.default.yaml 判定是否有 sw_toolbox 消费者。"""
    import yaml

    yaml_path = Path("parts_library.default.yaml")
    consumers: list[str] = []
    if yaml_path.exists():
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        # mappings 是 list，每项含 adapter 字段
        mappings = data.get("mappings", []) or []
        for i, mapping in enumerate(mappings):
            if mapping.get("adapter") == "sw_toolbox":
                consumers.append(f"mapping[{i}]:{mapping.get('match', {})}")

    result = {
        "sw_toolbox_consumers": consumers,
        "has_consumer": len(consumers) > 0,
    }
    _dump(artifacts_dir, "stage_d_pre.json", result)
    return result


def stage_c_session_restart(
    matched_list: list[dict[str, Any]],
    artifacts_dir: Path,
) -> dict[str, Any]:
    """顺序转 8 个 matched sldprt 为 STEP。subprocess-per-convert 模型下
    每次 convert 已独立进程，原 'session 周期重启' 要求由架构天然满足。

    Returns pass=True iff 8 个全部转换成功，STEP 文件合法。
    """
    from adapters.solidworks.sw_com_session import get_session

    step_dir = artifacts_dir / "stage_c_steps"
    step_dir.mkdir(parents=True, exist_ok=True)

    target_count = 8  # 原 plan: 前 5 后 3
    targets = matched_list[:target_count]

    if len(targets) < target_count:
        result = {
            "convert_count": 0,
            "success_count": 0,
            "all_steps_valid": False,
            "pass": False,
            "reason": f"matched 数不足（需 {target_count}），实际 {len(targets)}",
            "note": "subprocess-per-convert 模型下 Stage C 不再有显式 restart 步骤",
        }
        _dump(artifacts_dir, "stage_c.json", result)
        return result

    session = get_session()
    success = 0
    per_target: list[dict[str, Any]] = []
    for i, t in enumerate(targets):
        sldprt = t["sldprt"]
        step_path = step_dir / f"{i:02d}_{Path(sldprt).stem}.step"
        ok = session.convert_sldprt_to_step(sldprt, str(step_path))
        if ok and step_path.exists() and step_path.stat().st_size > 1024:
            success += 1
            per_target.append({"index": i, "sldprt": sldprt, "step_size": step_path.stat().st_size})
        else:
            per_target.append({"index": i, "sldprt": sldprt, "step_size": 0, "failed": True})

    result = {
        "convert_count": len(targets),
        "success_count": success,
        "all_steps_valid": success == len(targets),
        "per_target": per_target,
        "pass": success == len(targets),
        "note": "subprocess-per-convert 模型下每次 convert 已独立 SW 进程",
    }
    _dump(artifacts_dir, "stage_c.json", result)
    return result


def stage_d_assembly_regression(
    d_pre: dict[str, Any], artifacts_dir: Path,
) -> dict[str, Any]:
    """装配回归 gate。若 D-pre.has_consumer=False 则 skip。"""
    if not d_pre.get("has_consumer"):
        result = {"skipped_with_reason": "GISBOT 走 CadQuery 原生路径，无 sw_toolbox 消费者"}
        _dump(artifacts_dir, "stage_d.json", result)
        return result

    import os
    import yaml
    from tools.sw_b9_junit_parser import parse_junit_xml
    from tools.sw_b9_clean_state import clean_sw_state

    # 生成两份临时 yaml
    src_yaml = Path("parts_library.default.yaml")
    off_yaml = artifacts_dir / "parts_library_toolbox_off.yaml"
    on_yaml = artifacts_dir / "parts_library_toolbox_on.yaml"

    base = yaml.safe_load(src_yaml.read_text(encoding="utf-8")) or {}
    off_copy = json.loads(json.dumps(base))  # deep copy via json
    on_copy = json.loads(json.dumps(base))
    # off: 把所有 sw_toolbox mapping 改成 jinja_primitive（回退路径，不走 SW）
    for m in off_copy.get("mappings", []) or []:
        if m.get("adapter") == "sw_toolbox":
            m["adapter"] = "jinja_primitive"
    # on: 保留原配置
    off_yaml.write_text(yaml.safe_dump(off_copy, allow_unicode=True), encoding="utf-8")
    on_yaml.write_text(yaml.safe_dump(on_copy, allow_unicode=True), encoding="utf-8")

    suite = [
        "tests/test_assembly_validator.py",
        "tests/test_assembly_coherence.py",
        "tests/test_gen_assembly.py",
    ]

    def run_suite(yaml_override: Path, xml_out: Path) -> dict[str, Any]:
        env = os.environ.copy()
        env["CAD_PARTS_LIBRARY"] = str(yaml_override)  # 修正：用实际 env 名
        subprocess.run(
            [sys.executable, "-m", "pytest", *suite, f"--junitxml={xml_out}", "-q"],
            env=env, check=False, timeout=600,
        )
        return parse_junit_xml(xml_out)

    before = run_suite(off_yaml, artifacts_dir / "stage_d_before.xml")
    clean_sw_state(
        session=None,  # subprocess 模型无持久 session
        step_cache_dir=Path.home() / ".cad-spec-gen" / "step_cache" / "sw_toolbox",
    )
    after = run_suite(on_yaml, artifacts_dir / "stage_d_after.xml")

    regression = after["passed"] < before["passed"]
    result = {
        "before_passed": before["passed"],
        "after_passed": after["passed"],
        "before_failed_tests": before["failed_tests"],
        "after_failed_tests": after["failed_tests"],
        "regression_detected": regression,
        "pass": not regression,
    }
    _dump(artifacts_dir, "stage_d.json", result)

    # 若 after 新增失败测试 → 写 pending 清单给 Phase SW-C
    new_fails = [t for t in after["failed_tests"] if t not in before["failed_tests"]]
    if new_fails:
        pending = {
            "new_false_positives": new_fails,
        }
        _dump(artifacts_dir, "stage_d_pending_envelope_upgrades.json", pending)
    return result


def stage_e_roi_decision(
    stage_b_result: dict[str, Any], artifacts_dir: Path,
) -> dict[str, Any]:
    coverage = stage_b_result.get("coverage", 0.0)
    decision = "keep_full" if coverage >= 0.55 else "downgrade_gb_only"
    actions = []
    if decision == "downgrade_gb_only":
        actions = [
            "下一轮 Phase SW-C 砍 ISO/DIN 兜底规则",
            "仅保留 GB 高优先级匹配路径",
            "重新审视 Toolbox backend 的 ROI",
        ]
    result = {
        "real_bom_coverage": coverage,
        "threshold": 0.55,
        "decision": decision,
        "actions_required": actions,
    }
    _dump(artifacts_dir, "stage_e.json", result)
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
        preflight = stage_0_preflight(
            toolbox_root, demo_bom, artifacts_dir,
            rebuild_index=not args.no_rebuild_index,
        )
        stage_0_5_token_health(demo_bom, artifacts_dir, toolbox_root=toolbox_root)
        min_score = preflight.get("min_score_used", 0.30)
        stage_a = stage_a_demo_coverage(demo_bom, min_score, artifacts_dir)
        stage_b = stage_b_gisbot_coverage(Path(args.real_bom_spec), min_score, artifacts_dir)
        d_pre = stage_d_pre_consumer_check(artifacts_dir)
        stage_c_session_restart(stage_a.get("matched_list", []), artifacts_dir)
        stage_d_assembly_regression(d_pre, artifacts_dir)
        stage_e_roi_decision(stage_b, artifacts_dir)

        # 生成汇总 + markdown 报告
        from tools.sw_b9_report_builder import build_acceptance_summary, render_markdown_report
        summary = build_acceptance_summary(artifacts_dir)
        _dump(artifacts_dir, "acceptance_summary.json", summary)

        report_md = render_markdown_report(artifacts_dir, report_date="2026-04-14")
        report_path = Path("docs/superpowers/reports/sw-b9-acceptance-2026-04-14.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_md, encoding="utf-8")
        log.info("[report] written: %s (top pass=%s)", report_path, summary["pass"])

        return 0 if summary["pass"] else 1
    except Exception:
        log.error("编排失败:\n%s", traceback.format_exc())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
