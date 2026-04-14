"""读取 artifacts/sw_b9/*.json → 汇总 JSON + markdown 报告。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load(artifacts_dir: Path, name: str) -> dict[str, Any]:
    p = artifacts_dir / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def build_acceptance_summary(artifacts_dir: Path) -> dict[str, Any]:
    """汇总 5 个 stage JSON，按决策 #34 放宽口径计算顶层 pass。"""
    stages = {
        "stage_0": _load(artifacts_dir, "preflight.json"),
        "stage_0_5": _load(artifacts_dir, "stage_0_5.json"),
        "stage_a": _load(artifacts_dir, "stage_a.json"),
        "stage_b": _load(artifacts_dir, "stage_b.json"),
        "stage_d_pre": _load(artifacts_dir, "stage_d_pre.json"),
        "stage_c": _load(artifacts_dir, "stage_c.json"),
        "stage_d": _load(artifacts_dir, "stage_d.json"),
        "stage_e": _load(artifacts_dir, "stage_e.json"),
    }

    d = stages["stage_d"]
    d_skipped = bool(d.get("skipped_with_reason"))
    d_ok = d.get("pass") is True or d_skipped
    stages["stage_d"]["skipped"] = d_skipped

    top_pass = (
        stages["stage_0"].get("pass") is True
        and stages["stage_0_5"].get("pass") is True
        and stages["stage_a"].get("pass") is True
        and stages["stage_c"].get("pass") is True
        and d_ok
    )

    return {
        "schema_version": 1,
        "pass": top_pass,
        "d_skipped": d_skipped,
        "stages": stages,
    }


def _status_label(summary: dict[str, Any]) -> str:
    if not summary["pass"]:
        return "FAIL"
    if summary.get("d_skipped"):
        return "CONDITIONAL"
    return "PASS"


def render_markdown_report(artifacts_dir: Path, report_date: str) -> str:
    summary = build_acceptance_summary(artifacts_dir)
    status = _status_label(summary)
    s = summary["stages"]

    lines = [
        f"# SW-B9 真跑验收报告 — {report_date}",
        "",
        "## 顶层结论",
        "",
        f"- SW-B9 状态: **{status}**（按决策 #34 放宽口径判定）",
        f"- Stage D 是否 skipped: {summary['d_skipped']}",
        f"- 触发 ROI 熔断降级: {s['stage_e'].get('decision') == 'downgrade_gb_only'}",
        "",
        "## Stage 汇总表",
        "",
        "| Stage | 目标 | 实测 | Pass |",
        "| --- | --- | --- | --- |",
        f"| 0 preflight | toolbox 探测 + index 构建 | index={s['stage_0'].get('index_size')} | {s['stage_0'].get('pass')} |",
        f"| 0.5 token 健康 | cn_hit_rate > 0 | {s['stage_0_5'].get('cn_token_hit_rate')} | {s['stage_0_5'].get('pass')} |",
        f"| A demo 覆盖率 | ≥ 73% | {s['stage_a'].get('coverage')} | {s['stage_a'].get('pass')} |",
        f"| B GISBOT 覆盖率 | informational | {s['stage_b'].get('coverage')} | informational |",
        f"| C session 重启 | 前5 后3 STEP 合法 | pre={s['stage_c'].get('pre_restart_count')} post={s['stage_c'].get('post_restart_count')} | {s['stage_c'].get('pass')} |",
        f"| D 装配回归 | after ≥ before | {'skipped' if summary['d_skipped'] else s['stage_d'].get('pass')} | {s['stage_d'].get('pass') or 'skipped'} |",
        f"| E ROI 熔断 | coverage ≥ 55% | {s['stage_e'].get('real_bom_coverage')} → {s['stage_e'].get('decision')} | informational |",
        "",
        "## 样本不足声明（决策 B1 / 决策 #34）",
        "",
        f"真实 BOM 样本为 GISBOT {s['stage_b'].get('total_rows', 'N/A')} 行，低于 ≥100 行门槛。",
        "GISBOT 为 CadQuery 原生设计项目，不消费 SW Toolbox sldprt，Stage D 在此样本下 skipped。",
        "严格版 SW-B9 延至有合适样本时重跑（见 decisions.md #34）。",
        "",
        "## 详细数据",
        "",
        f"- preflight.json: toolbox={s['stage_0'].get('toolbox_root')}, min_score={s['stage_0'].get('min_score_used')}",
        f"- stage_a.json: unmatched={s['stage_a'].get('unmatched_rows')}",
        f"- stage_b.json: excluded={len(s['stage_b'].get('excluded_rows', []))} rows",
        f"- stage_c.json: restart_duration={s['stage_c'].get('restart_duration_s')}s",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-summary", required=True)
    parser.add_argument("--report-date", required=True)
    args = parser.parse_args()

    art_dir = Path(args.artifacts_dir)
    summary = build_acceptance_summary(art_dir)
    md = render_markdown_report(art_dir, args.report_date)

    Path(args.output_summary).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.output_md).write_text(md, encoding="utf-8")
    print(f"[ok] summary pass={summary['pass']} d_skipped={summary['d_skipped']}")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
