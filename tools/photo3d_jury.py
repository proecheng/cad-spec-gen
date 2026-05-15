"""photo3d-jury cli 薄壳 — 顶层 try/finally + 报告组装（Tasks 17+18）。

走 cad_pipeline.py jury subcommand dispatch 调用；不进 pyproject [project.scripts]。

主流程（spec rev 5 §4.7）：
    1) parse args + resolve config_path
    2) --list-profiles 走快速分支返 0
    3) load_jury_config（FileNotFoundError / JuryConfigSchemaError / JuryConfigError → exit 2）
    4) Layer 0 输入证据绑定（fail → exit 1）
    5) 重跑保护：archive 已有 PHOTO3D_JURY_REPORT.json
    6) cost gate（dry-run 跑到这里就停；real run 超 budget 无 --confirm-cost → exit 3）
    7) Layer 1 字段自洽（per_view_failures 不阻断 Layer 2 但影响 overall status）
    8) Layer 2 LLM 调用（acquire_lock；逐视角 try/except；失败计入 needs_review）
    9) sha256 重读校验 enhancement_report → drift 时 status="blocked"
   10) 写 PHOTO3D_JURY_REPORT.json + (accepted) jury_review_input.json
   11) 异常兜底（JuryDisabledByEnv / JuryLockBusy / 其它 → 99 + redact_traceback）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools._file_lock import LockBusy as JuryLockBusy
from tools._file_lock import acquire_lock
from tools.contract_io import file_sha256, write_json_atomic
from tools.jury.config import (
    JuryConfigError,
    JuryConfigSchemaError,
    load_jury_config,
)
from tools.jury.cost import compute_cost_decision
from tools.jury.deterministic_gate import run_layer1
from tools.jury.input_evidence_binding import run_layer0
from tools.jury.llm_client import (
    JuryDisabledByEnv,
    JuryLlmError,
    request_jury_verdict,
)
from tools.jury.redact import redact_traceback_str
from tools.jury.stderr_messages import format_stderr_message
from tools.jury.verdict import (
    RunVerdict,
    ViewVerdict,
    aggregate_run_verdict,
    parse_view_verdict,
)
from tools.jury_loop.llm_fallback import _request_chat_text


class _FeatureExtractorClient:
    """text endpoint 适配器，给 feature_extractor.extract 用（spec F8）。

    feature_extractor 鸭子类型要求 `.complete_text(prompt)` 或 `.complete(prompt)`；
    这里复用 jury_loop.llm_fallback._request_chat_text（chat-completions text-only），
    与 jury vision endpoint 同款 base_url + api_key，不引入新配置项。
    """

    def __init__(self, profile: Any) -> None:  # noqa: ANN401 — JuryProfile 鸭子类型即可
        self._profile = profile

    def complete_text(self, prompt: str) -> str:
        """调 chat-completions 纯文本接口；feature_extractor 自行 fail-safe。"""
        return _request_chat_text(self._profile, prompt)  # noqa: SLF001 — 复用私有 helper


_JURY_PROMPT = """\
你是一名 CAD 渲染照片级验收员。下面这张图来自一台机械产品的多视角渲染增强后输出。
请按以下 5 项判断（各只出 true/false）：
1. geometry_preserved   — 几何与设计一致，无明显形变/丢件
2. material_consistent  — 材质风格统一，无明显错配
3. photorealistic       — 视觉质感像真实拍摄而非 3D 渲染
4. no_extra_parts       — 没有 LLM 凭空加出的零件、装饰、文字
5. no_missing_parts     — 没有把原本存在的零件擦除

另给 photoreal_score（0-100 整数，单独度量第 3 项的强度）。

只返回严格 JSON：
{"semantic_checks":{"geometry_preserved":bool,"material_consistent":bool,
"photorealistic":bool,"no_extra_parts":bool,"no_missing_parts":bool},
"photoreal_score":int,"reason":"<= 80 字"}

不要 markdown 代码块。不要解释。
"""


def _utc_z() -> str:
    """UTC 时间戳（ISO8601 with Z 后缀），用于 generated_at。"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_compact() -> str:
    """紧凑 UTC 时间戳（YYYYMMDDTHHMMSSZ），用于 archive 文件名。"""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_parser() -> argparse.ArgumentParser:
    """构造 argparse；所有 flag 与 spec rev 5 §4.7 对齐。"""
    p = argparse.ArgumentParser(
        prog="photo3d-jury", description="自动照片级验收（vision LLM jury）"
    )
    p.add_argument("--subsystem")
    p.add_argument(
        "--override-subsystem",
        dest="override_subsystem",
        default=None,
        help="alias flag (v2.37.7 §11-N2)：cli --subsystem 项目名 + "
        "--override-subsystem 实际 subsystem；jury Layer 0 用 override 解析 "
        "run_dir + report 加 effective_subsystem 字段；默认不指定时 "
        "effective = --subsystem（零行为变化）",
    )
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--allow-external-config", action="store_true")
    p.add_argument("--profile-id")
    p.add_argument("--list-profiles", action="store_true")
    p.add_argument("--last-status", action="store_true")
    p.add_argument("--budget", type=float, default=0.1)
    p.add_argument("--confirm-cost", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--debug-output", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    # CP-6 Task 6.1：jury_loop orchestrator 调本工具单视角调度（隐藏 help，外行用户不误用）
    p.add_argument("--single-view", help=argparse.SUPPRESS)
    p.add_argument("--image", nargs="+", help=argparse.SUPPRESS)
    # v2.37 Task 6：matches_spec 维度入口（缺一项则跳 features 抽取 → 向后兼容 v2.36）
    p.add_argument(
        "--spec-md",
        dest="spec_md",
        default=None,
        help="CAD_SPEC.md 路径；默认 cad/<subsystem>/CAD_SPEC.md",
    )
    p.add_argument(
        "--design-doc",
        dest="design_doc",
        default=None,
        help="设计文档路径（如 examples/04-末端执行机构设计.md）；缺则跳过 matches_spec 抽特征",
    )
    return p


def _resolve_config_path(args: argparse.Namespace) -> Path:
    """解析 jury config 路径；--config 优先，否则 ~/.claude/cad_jury_config.json。"""
    if args.config:
        return Path(args.config).resolve()
    home = Path(
        os.environ.get("USERPROFILE") or os.environ.get("HOME") or "~"
    ).expanduser()
    return home / ".claude" / "cad_jury_config.json"


def _archive_existing_report(report_path: Path, force: bool) -> None:
    """重跑保护：rename 已有报告（force → forced.json，否则 timestamp+sha 短哈希）。

    用 Path.replace（atomic rename + cross-drive fallback）防 race。
    """
    if not report_path.exists():
        return
    if force:
        archived = report_path.parent / "PHOTO3D_JURY_REPORT.forced.json"
    else:
        body = report_path.read_bytes()
        short = hashlib.sha256(body).hexdigest()[:6]
        archived = (
            report_path.parent / f"PHOTO3D_JURY_REPORT.{_utc_compact()}.{short}.json"
        )
    report_path.replace(archived)


def _decide_status(layer1_pass: bool, view_verdicts: list[dict[str, Any]]) -> str:
    """整体 status 决策（layer 0 已 pass 前提下）。

    层 1 fail → preview；任一视角 needs_review → needs_review；
    任一视角 preview → preview；否则 accepted。
    """
    if not layer1_pass:
        return "preview"
    if any(v.get("verdict") == "needs_review" for v in view_verdicts):
        return "needs_review"
    if any(v.get("verdict") == "preview" for v in view_verdicts):
        return "preview"
    return "accepted"


def _derive_matches_spec_status(run: RunVerdict) -> str:
    """v2.37 Task 7：决策 matches_spec_status（'pass' | 'warn' | 'fail' | 'blocked'）。

    本 task 简化决策（Task 9 retry 接入后再扩 'warn'/'blocked'）：
    - overall_matches_spec=True → 'pass'（无 features 或全 visible 都走这条）
    - overall_matches_spec=False → 'fail'（Task 9 retry 中间态再改 'warn'，
      达 N retry 上限再升 'blocked'）

    Args:
        run: aggregate_run_verdict 返回的 RunVerdict

    Returns:
        'pass' | 'fail'（Task 9 扩 'warn' / 'blocked'）
    """
    if run.overall_matches_spec:
        return "pass"
    return "fail"


# CP-6 Task 6.1.2: --single-view view 名校验（防 path traversal；与 metadata 模块同 pattern）
_SINGLE_VIEW_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,63}$")


def _resolve_effective_subsystem(args: argparse.Namespace) -> str:
    """v2.37.7 §11-N2：从 args 派生 effective subsystem（path/Layer 0 用值）。

    args.subsystem = cli 项目名（保 report.subsystem 不变 forward-compat）；
    args.override_subsystem = 实际 subsystem（jury Layer 0/run_dir/ARTIFACT_INDEX 用此值）；
    默认（override 未指定）effective = args.subsystem 零行为变化。

    main() 已在入口对 args.override_subsystem 做 strip + 校验；
    helper 调用方拿到的 args 已是规范化值。
    """
    if getattr(args, "override_subsystem", None):
        return str(args.override_subsystem)
    return str(args.subsystem)


def _load_cached_features_for_subsystem(
    subsystem: str, project_root: Path
) -> list[dict[str, Any]]:
    """Task 9 v2.37 (B)：从 cad/<sub>/.cad-spec-gen/matches_spec_features.json 读 features。

    spec D1：single-view subprocess 复用主 path Task 4+6 写的 cache，
    避免 subprocess 自行调 feature_extractor（无 design_doc 入口，且重复 LLM 计费）。

    fail-safe（任何异常返 []，行为同 v2.36）：
    - 文件不存在：cache 未建 → 空 features → prompt 等同 _JURY_PROMPT
    - JSON 烂：上一次写盘断电 / 手动篡改 → 空 features
    - features 字段缺/非 list：schema 漂移 → 空 features

    Args:
        subsystem: 子系统名（如 end_effector）；要与 main path 写 cache 时同名
        project_root: 项目根目录（cwd 或 --project-root 解析后）

    Returns:
        features list（每条至少含 feature_id；description_cn / expected_in_views
        可缺）；任何错误一律 []
    """
    cache_path = (
        project_root
        / "cad"
        / subsystem
        / ".cad-spec-gen"
        / "matches_spec_features.json"
    )
    try:
        if not cache_path.is_file():
            return []
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    features = payload.get("features", [])
    if not isinstance(features, list):
        return []
    return [f for f in features if isinstance(f, dict)]


def _handle_single_view_mode(
    args: argparse.Namespace, profile: Any, caps: Any,  # noqa: ANN401
) -> int:
    """--single-view 分支：单视角调度 LLM 评 N 张图，stdout JSON list，不写盘。

    契约（spec §6）：
    - exit 0 + stdout 必为合法 JSON list[dict]（即使某些图 LLM 失败也作 needs_review item 写入）
    - exit 2 + stderr 表参数错（缺 --image / view 名非法）
    - 任一 LLM 调用失败 → 该项 verdict=needs_review + parse_anomalies 含 "llm_call_failed"
      调用方（orchestrator）检测到 needs_review 走 loop_status=jury_unavailable

    v2.37 Task 9 (B)：subprocess 启动时读 cad/<sub>/.cad-spec-gen/matches_spec_features.json
    用 _build_view_prompt 给 prompt 附 features 列表（与主 path Task 6 一致）；
    cache 缺/烂 → 回落 _JURY_PROMPT（向后兼容 v2.36）。
    """
    if not args.image:
        sys.stderr.write("✗ --single-view 要求 --image PATH [PATH ...]\n")
        return 2
    if not _SINGLE_VIEW_NAME_PATTERN.fullmatch(args.single_view):
        sys.stderr.write(
            f"✗ --single-view 名非法（必须匹配 {_SINGLE_VIEW_NAME_PATTERN.pattern}）：{args.single_view}\n"
        )
        return 2

    # Task 9 (B)：读 cache + 构造视角 prompt（无 cache / 不相关 feature → _JURY_PROMPT 原文）
    # project_root 同 main() 默认 = cwd（_handle_single_view_mode 短路在 args.project_root
    # resolve 之前；直接用 Path(args.project_root) 与 main() 后半段保持一致语义）
    project_root = Path(args.project_root).resolve()
    # v2.37.7 §11-N2：path 解析用 effective subsystem（与主 path Task 6 一致）
    effective_subsystem = _resolve_effective_subsystem(args)
    features = _load_cached_features_for_subsystem(effective_subsystem, project_root)
    view_prompt = _build_view_prompt(args.single_view, features)

    results: list[dict[str, Any]] = []
    for img in args.image:
        img_path = Path(img).resolve()
        if not img_path.is_file():
            results.append(_single_view_needs_review_item(
                args.single_view, img, reason=f"图片不存在: {img}",
                anomaly="image_not_found",
            ))
            continue
        try:
            resp = request_jury_verdict(
                profile=profile,
                image_path=img_path,
                prompt=view_prompt,
                max_retries=args.max_retries,
            )
            vv = parse_view_verdict(
                resp.content_text,
                finish_reason=resp.finish_reason or "stop",
                min_photoreal_score=caps.min_photoreal_score,
            )
            results.append({
                "view": args.single_view,
                "image_path": img,
                "verdict": vv.verdict,
                "photoreal_score": vv.photoreal_score,
                "semantic_checks": vv.semantic_checks,
                "reason": vv.reason,
                # Task 9 (B)：透传 features_status 给 orchestrator
                # 让 _call_jury_subprocess 能识别 matches_spec 失败 → 触发 retry
                "features_status": list(vv.features_status),
                "parse_status": vv.parse_status,
                "parse_anomalies": list(vv.parse_anomalies),
            })
        except Exception as exc:  # noqa: BLE001 — 任何 LLM/parse 失败 → needs_review 由调用方处理
            results.append(_single_view_needs_review_item(
                args.single_view, img,
                reason=f"LLM call failed: {type(exc).__name__}: {exc}",
                anomaly="llm_call_failed",
            ))

    sys.stdout.write(json.dumps(results, ensure_ascii=False) + "\n")
    return 0


def _build_view_prompt(view_name: str, features: list[dict[str, Any]]) -> str:
    """v2.37 Task 6：构造单视角 vision prompt，按 expected_in_views 过滤后挂相关 features。

    - features=[] / 无相关 feature → 返回原 _JURY_PROMPT（向后兼容 v2.36 老 fixture 不变）
    - 否则在原 prompt 后追加中文段 + features 列表 + 要求 LLM 返回 features_status
    - 不动 _JURY_PROMPT 模板字面（spec §8 不变量 #1：保护 5 bool key 评审主路径）

    Args:
        view_name: 视角名（如 V4 / iso / front）
        features: feature_extractor.extract 返回的 features list

    Returns:
        完整 prompt 字符串
    """
    relevant = [
        f
        for f in features
        if not f.get("expected_in_views") or view_name in f.get("expected_in_views", [])
    ]
    if not relevant:
        return _JURY_PROMPT

    features_lines = "\n".join(
        f"- {f.get('feature_id', '?')}: {f.get('description_cn', '')}"
        for f in relevant
    )
    addon = (
        "\n\n另外，请对照设计文档列出的关键特征，判断它们在图里**实际可见**了没（视觉对账）：\n"
        f"{features_lines}\n\n"
        "输出 JSON 多加一个字段 features_status:\n"
        '"features_status":[{"feature_id":"...","visible":bool,"reason":"<= 80 字"}, ...]\n'
    )
    return _JURY_PROMPT.rstrip() + addon


def _extract_features_for_run(
    *,
    args: Any,  # noqa: ANN401 — argparse.Namespace 鸭子类型够
    profile: Any,  # noqa: ANN401 — JuryProfile 鸭子类型够
    project_root: Path,
    frozen_run_id: str,
) -> list[dict[str, Any]]:
    """v2.37 Task 6：进程启动调 feature_extractor.extract 一次（spec D1 per-process）。

    决策矩阵：
    - args.spec_md 显式提供 → 用之；否则 derive cad/<subsystem>/CAD_SPEC.md
    - args.design_doc 未提供 → 跳过抽取（无通用 convention 必须用户指明，spec D5 fail-safe）
    - 任一文件不存在 → 跳过抽取（不阻断主流程，matches_spec 走 ViewVerdict 默认 True）
    - extract 抛任何异常 → 兜底返 []（feature_extractor 内已有 fail-safe，本层再防一层）

    Returns:
        features list（可能为 []，调用方按空 list 退化 _build_view_prompt）
    """
    if not args.design_doc:
        return []
    # v2.37.7 §11-N2：path 解析用 effective subsystem（与主 path 一致）
    effective_subsystem = _resolve_effective_subsystem(args)
    spec_md_path = (
        Path(args.spec_md)
        if args.spec_md
        else project_root / "cad" / effective_subsystem / "CAD_SPEC.md"
    )
    design_doc_path = Path(args.design_doc)
    if not spec_md_path.exists() or not design_doc_path.exists():
        return []

    cache_dir = project_root / "cad" / effective_subsystem / ".cad-spec-gen"
    try:
        # 延迟 import 防 tools.jury.feature_extractor 任何 top-level 异常炸 main
        from tools.jury import feature_extractor as _fe

        fx_client = _FeatureExtractorClient(profile)
        fx_result = _fe.extract(
            spec_md_path,
            design_doc_path,
            cache_dir=cache_dir,
            llm_client=fx_client,
            subsystem=effective_subsystem,
            run_id=frozen_run_id,
        )
        features = fx_result.get("features", [])
        return features if isinstance(features, list) else []
    except Exception:  # noqa: BLE001 — spec D5 fail-safe：抽特征故障不阻断 jury 主流程
        return []


def _single_view_needs_review_item(
    view: str, image_path: str, *, reason: str, anomaly: str,
) -> dict[str, Any]:
    """构造单视角 needs_review item（图缺失 / LLM 失败共用）。

    Task 9：增加 features_status=[] 让 schema 与成功路径一致（orchestrator
    解析时不必 if-check 字段存在性）。
    """
    return {
        "view": view,
        "image_path": image_path,
        "verdict": "needs_review",
        "photoreal_score": 0,
        "semantic_checks": {},
        "reason": reason,
        "features_status": [],
        "parse_status": "ok",
        "parse_anomalies": [anomaly],
    }


def main(argv: list[str] | None = None) -> int:  # noqa: C901,PLR0911,PLR0912,PLR0915
    """photo3d-jury 入口；返回 exit code（0/1/2/3/4/99）。

    复杂度高（cli + 9 步主流程 + 6 类异常分支）；ruff 复杂度告警在本函数显式 noqa。
    """
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    config_path = _resolve_config_path(args)

    # --- --list-profiles 优先级最高（无 --subsystem 也能跑） ---
    if args.list_profiles:
        try:
            profile, _caps = load_jury_config(config_path)
        except (JuryConfigError, FileNotFoundError):
            sys.stderr.write(
                format_stderr_message(
                    exit_code=2,
                    error_kind="config_missing",
                    context={"config_path": str(config_path)},
                )
                + "\n"
            )
            return 2
        cost_str = (
            f"{profile.cost_per_call_usd}"
            if profile.cost_per_call_usd is not None
            else "null"
        )
        print(f"{profile.id}\t{profile.kind}\t{profile.model}\t{cost_str}\t[active]")
        return 0

    # --- 必填 --subsystem ---
    if not args.subsystem:
        sys.stderr.write("✗ 缺 --subsystem 参数\n")
        return 2

    # --- v2.37.7 §11-N2 (E3 fix)：--override-subsystem 输入校验 + effective_subsystem 计算 ---
    # args.subsystem = cli 项目名（report subsystem 字段保留 forward-compat）
    # effective_subsystem = args.override_subsystem or args.subsystem（默认零行为变化）
    effective_subsystem = args.subsystem
    if args.override_subsystem is not None:
        override = args.override_subsystem.strip()
        if not override:
            sys.stderr.write("✗ --override-subsystem 不能为空字符串\n")
            return 2
        if "/" in override or "\\" in override or ".." in override:
            sys.stderr.write(
                f"✗ --override-subsystem={args.override_subsystem!r} 含非法字符 (/ \\ ..)\n"
            )
            return 2
        args.override_subsystem = override  # strip 写回
        effective_subsystem = override

    # --- 校验 budget ---
    if not math.isfinite(args.budget) or args.budget < 0:
        sys.stderr.write(f"✗ --budget={args.budget} 必须为有限非负数\n")
        return 2

    # --- 加载 config ---
    try:
        profile, caps = load_jury_config(config_path)
    except FileNotFoundError:
        sys.stderr.write(
            format_stderr_message(
                exit_code=2,
                error_kind="config_missing",
                context={"config_path": str(config_path)},
            )
            + "\n"
        )
        return 2
    except JuryConfigSchemaError as exc:
        sys.stderr.write(
            format_stderr_message(
                exit_code=2,
                error_kind="schema_version_invalid",
                context={"actual": str(exc)},
            )
            + "\n"
        )
        return 2
    except JuryConfigError as exc:
        sys.stderr.write(f"✗ 配置错: {exc}\n")
        return 2

    # CP-6 Task 6.1.2：--single-view 模式（跳过 Layer 0 / cost gate / batch / 写盘）
    # 必须在 project_root resolve / Layer 0 之前短路，闭环 retry 不依赖 ARTIFACT_INDEX
    if args.single_view:
        return _handle_single_view_mode(args, profile, caps)

    project_root = Path(args.project_root).resolve()

    try:
        # === Layer 0：输入证据绑定 + sha256 freeze ===
        # v2.37.7 §11-N2：Layer 0 + path 用 effective_subsystem（默认 = args.subsystem）
        layer0 = run_layer0(
            project_root=project_root, subsystem=effective_subsystem, caps=caps
        )
        if not layer0.passed:
            sys.stderr.write(f"✗ Layer 0 blocked: {layer0.blocking_reasons}\n")
            return 1

        run_dir = (
            project_root
            / "cad"
            / effective_subsystem
            / ".cad-spec-gen"
            / "runs"
            / layer0.frozen_run_id
        )
        report_path = run_dir / "PHOTO3D_JURY_REPORT.json"

        # === 重跑保护：dry-run 不动盘 ===
        if not args.dry_run:
            _archive_existing_report(report_path, args.force)

        # === Cost 预估（dry-run 仍走此 gate） ===
        n_views = len(layer0.frozen_report.get("views", []))
        cd = compute_cost_decision(
            cost_per_call_usd=profile.cost_per_call_usd or 0.0,
            n_views=n_views,
            budget_per_run_usd=args.budget,
            confirm_cost=args.confirm_cost,
        )

        if args.dry_run:
            print(f"[dry-run] estimated={cd.estimated_usd} USD, allowed={cd.allowed}")
            return 0 if cd.allowed else 3

        if not cd.allowed:
            sys.stderr.write(
                format_stderr_message(
                    exit_code=3,
                    error_kind="budget_exceeded",
                    context={
                        "estimated_cost_usd": cd.estimated_usd,
                        "budget_per_run_usd": args.budget,
                        "n_views": n_views,
                        "cost_per_call_usd": profile.cost_per_call_usd or 0.0,
                    },
                )
                + "\n"
            )
            return 3

        # === Layer 1：字段自洽 ===
        layer1 = run_layer1(layer0.frozen_report)

        # === v2.37 Task 6：进程启动抽 matches_spec features（per-process 1 次） ===
        # 缺 --design-doc / 文件不存在 / extractor 故障 → features=[]，主流程不阻断
        features = _extract_features_for_run(
            args=args,
            profile=profile,
            project_root=project_root,
            frozen_run_id=layer0.frozen_run_id,
        )

        # === Layer 2：LLM 逐视角调用（lock 守 active run dir） ===
        view_verdicts: list[dict[str, Any]] = []
        actual_cost = 0.0
        n_retries_total = 0

        if layer1.passed:
            lock_path = run_dir / ".jury.lock"
            # v2.37.7 §11-N3：per-view 进度 stderr 输出 — 用户实时看到 jury 走到哪
            total_views = len(layer0.frozen_report.get("views", [])) or 1
            with acquire_lock(lock_path):
                for view in layer0.frozen_report.get("views", []):
                    view_name = str(view.get("view", ""))
                    img_rel = str(view.get("enhanced_image", ""))
                    img_path = project_root / img_rel
                    # v2.37 Task 6：按 expected_in_views 过滤后挂 features 到 prompt
                    view_prompt = _build_view_prompt(view_name, features)
                    try:
                        resp = request_jury_verdict(
                            profile=profile,
                            image_path=img_path,
                            prompt=view_prompt,
                            max_retries=args.max_retries,
                        )
                        actual_cost += (
                            profile.cost_per_call_usd or 0.0
                        ) * resp.attempts
                        n_retries_total += resp.attempts - 1
                        vv = parse_view_verdict(
                            resp.content_text,
                            finish_reason=resp.finish_reason or "stop",
                            min_photoreal_score=caps.min_photoreal_score,
                        )
                        view_verdicts.append(
                            {
                                "view": view_name,
                                "verdict": vv.verdict,
                                "semantic_checks": vv.semantic_checks,
                                "photoreal_score": vv.photoreal_score,
                                "reason": vv.reason,
                                # v2.37 Task 6：透传 features_status（Task 1 已 wire 到 ViewVerdict）
                                "features_status": vv.features_status,
                                "llm_meta": {
                                    "http_status": resp.http_status,
                                    "attempts": resp.attempts,
                                    "latency_ms": resp.latency_ms,
                                    "parse_status": vv.parse_status,
                                    "parse_anomalies": vv.parse_anomalies,
                                    "error_kind": None,
                                    "vendor_request_id": resp.vendor_request_id,
                                },
                            }
                        )
                        # v2.37.7 §11-N3 (F1 fix try-success)：成功视角进度行
                        latency_s = round(resp.latency_ms / 1000, 1)
                        sys.stderr.write(
                            f"△ [{view_name}/{total_views}] {profile.model} "
                            f"photoreal={vv.photoreal_score} verdict={vv.verdict} "
                            f"{latency_s}s\n"
                        )
                    except JuryLlmError as exc:
                        # 失败也保守计 1 次成本（vendor 通常已计费）
                        actual_cost += profile.cost_per_call_usd or 0.0
                        view_verdicts.append(
                            {
                                "view": view_name,
                                "verdict": "needs_review",
                                "semantic_checks": {},
                                "photoreal_score": 0,
                                "reason": "",
                                # v2.37 Task 6：失败路径 features_status=[]（保持 schema 一致）
                                "features_status": [],
                                "llm_meta": {
                                    "http_status": exc.http_status,
                                    "attempts": 1,
                                    "latency_ms": 0,
                                    "parse_status": "ok",
                                    "parse_anomalies": [],
                                    "error_kind": exc.error_kind,
                                    "vendor_request_id": None,
                                },
                            }
                        )
                        # v2.37.7 §11-N3 (F1 fix except JuryLlmError)：失败视角进度行
                        sys.stderr.write(
                            f"△ [{view_name}/{total_views}] {profile.model} "
                            f"ERROR {exc.error_kind} 0.0s\n"
                        )
                    except Exception as exc:  # noqa: BLE001 — v2.37.7 §11-N3 E2 fix：non-JuryLlmError 兜底进度 + re-raise
                        # 兜底进度行：让用户至少看到哪个视角崩；不吞异常 → re-raise 走顶层 except
                        sys.stderr.write(
                            f"△ [{view_name}/{total_views}] {profile.model} "
                            f"CRASH {type(exc).__name__}\n"
                        )
                        raise

        # === 写报告前 sha256 重读校验 ENHANCEMENT_REPORT.json ===
        # v2.37.7 §11-N2：renders 目录用 effective_subsystem（与 Layer 0 一致）
        er_path = (
            project_root
            / "cad"
            / "output"
            / "renders"
            / effective_subsystem
            / layer0.frozen_run_id
            / "ENHANCEMENT_REPORT.json"
        )
        new_sha = file_sha256(er_path)
        sha_drift = new_sha != layer0.frozen_sha256.get("enhancement_report")

        # === 整体 status 决策 ===
        overall = (
            "blocked" if sha_drift else _decide_status(layer1.passed, view_verdicts)
        )

        # === v2.37 Task 7：聚合 RunVerdict（F2 wire prompt_rewriter 数据） ===
        # 把 view_verdicts (list[dict]) 转回 dict[view_id, ViewVerdict] 给 aggregate_run_verdict
        # 注：features_status 已由 Task 6 透传，本步只读不改 view_verdicts
        view_verdict_objs: dict[str, ViewVerdict] = {}
        for v in view_verdicts:
            llm_meta = v.get("llm_meta", {})
            parse_anomalies = llm_meta.get("parse_anomalies", [])
            view_verdict_objs[str(v["view"])] = ViewVerdict(
                semantic_checks=v["semantic_checks"],
                photoreal_score=v["photoreal_score"],
                reason=v["reason"],
                parse_status="ok",
                parse_anomalies=list(parse_anomalies),
                verdict=v["verdict"],
                features_status=v.get("features_status", []),
            )
        run_verdict = aggregate_run_verdict(view_verdict_objs)
        matches_spec_status = _derive_matches_spec_status(run_verdict)

        # === 写报告 ===
        run_dir.mkdir(parents=True, exist_ok=True)
        report: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": _utc_z(),
            "subsystem": args.subsystem,
            "run_id": layer0.frozen_run_id,
            "status": overall,
            "ordinary_user_message": (
                "自动验收通过，可作为 enhance-review 的 review-input 输入。"
                if overall == "accepted"
                else "(详见 stderr 中文提示)"
            ),
            "next_step": "",
            "source_reports": {
                "render_manifest": (layer0.frozen_report.get("render_manifest") or ""),
                "render_manifest_sha256": layer0.frozen_sha256.get(
                    "render_manifest", ""
                ),
                "enhancement_report": (
                    layer0.frozen_report.get("enhancement_report") or ""
                ),
                "enhancement_report_sha256": layer0.frozen_sha256.get(
                    "enhancement_report", ""
                ),
            },
            "jury_meta": {
                "profile_id": profile.id,
                "model": profile.model,
                "estimated_cost_usd": cd.estimated_usd,
                "actual_cost_usd": round(actual_cost, 4),
                "budget_per_run_usd": args.budget,
                "min_photoreal_score": caps.min_photoreal_score,
                "n_views": n_views,
                "n_calls": sum(int(v["llm_meta"]["attempts"]) for v in view_verdicts),
                "n_retries_total": n_retries_total,
                "max_image_bytes": caps.max_image_bytes,
                "max_n_views": caps.max_n_views,
                "cost_warning": (
                    "estimated±50%; verify with vendor billing"
                    if profile.cost_per_call_usd is None
                    else None
                ),
            },
            "deterministic_gate": {
                "passed": layer1.passed,
                "per_view_failures": layer1.per_view_failures,
            },
            "views": view_verdicts,
            "blocking_reasons": ([{"code": "freeze_drift"}] if sha_drift else []),
            # v2.37 Task 7：matches_spec 维度顶层字段（schema_version 仍 1，无新 features 时
            # 全是 default value/True/{}/'pass'，老 fixture 不受影响）
            "overall_matches_spec": run_verdict.overall_matches_spec,
            "per_view_failed_features": run_verdict.per_view_failed_features,
            "matches_spec_status": matches_spec_status,
        }
        # v2.37.7 §11-N2：仅 override 时落 effective_subsystem 字段（默认零行为）
        if args.override_subsystem:
            report["effective_subsystem"] = effective_subsystem
        write_json_atomic(report_path, report)

        # === accepted 才写 jury_review_input.json（兼容 enhance-review） ===
        if overall == "accepted":
            review_input = {
                "schema_version": 1,
                "review_type": "auto_jury_v1",
                "subsystem": args.subsystem,
                "run_id": layer0.frozen_run_id,
                "source_reports": report["source_reports"],
                "views": [
                    {
                        "view": v["view"],
                        "semantic_checks": v["semantic_checks"],
                        "reviewer_notes": (
                            f"auto_jury photoreal_score={v['photoreal_score']}"
                        ),
                    }
                    for v in view_verdicts
                ],
            }
            # v2.37.7 §11-N2：仅 override 时落 effective_subsystem 字段（默认零行为）
            if args.override_subsystem:
                review_input["effective_subsystem"] = effective_subsystem
            write_json_atomic(run_dir / "jury_review_input.json", review_input)

        return 0
    except JuryDisabledByEnv:
        sys.stderr.write("△ CAD_JURY_DISABLE_LLM=1，jury 跳过\n")
        return 0
    except JuryLockBusy:
        sys.stderr.write(
            format_stderr_message(
                exit_code=4,
                error_kind="lock_busy",
                context={"held_pid": "(see lock file)", "age_seconds": 0},
            )
            + "\n"
        )
        return 4
    except (JuryConfigError, JuryConfigSchemaError) as exc:
        sys.stderr.write(f"✗ 配置错: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001 — 兜底防 traceback 漏 api_key
        tb_str = traceback.format_exc()
        sys.stderr.write(
            format_stderr_message(
                exit_code=99,
                error_kind="internal",
                context={"exception_type": type(exc).__name__},
            )
            + "\n"
        )
        sys.stderr.write(redact_traceback_str(tb_str)[:500] + "\n")
        return 99


if __name__ == "__main__":
    sys.exit(main())
