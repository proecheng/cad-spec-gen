"""adapters/solidworks/sw_config_broker.py — SW Toolbox 配置名匹配 broker。

设计参见 docs/superpowers/specs/2026-04-25-sw-toolbox-llm-config-broker-design.md (rev 2)。

主流程：
1. SW COM 列 SLDPRT 当前可用 configurations
2. 读 spec_decisions.json 缓存命中 + 三项校验 → 直接返回 cached_decision
3. 规则匹配 BOM dim → config (L1 精确 / L2 子串)，confidence ≥ 0.7 → auto
4. 含糊匹配 → 看 CAD_AMBIGUOUS_CONFIG_POLICY env：
   - "halt"（默认）→ 抛 NeedsUserDecision
   - "fallback_cadquery" → 返回 policy_fallback ConfigResolution（仍累积 pending）
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

# review I-2: invalidation_reason 受控枚举（spec §5.2 三项失效条件之一）。
# 在 _move_decision_to_history 头部校验防 caller 传错值进 history 后无法 group by 审计。
INVALIDATION_REASONS = frozenset({
    "bom_dim_signature_changed",
    "sldprt_filename_changed",
    "config_name_not_in_available_configs",
})


@dataclass
class ConfigResolution:
    """broker 返回的解析结果。

    confidence 取值表（详见 spec §4.1）:
        source="cached_decision":  1.0 （用户已确认）
        source="auto" + L1 精确:    1.0 （字面完全匹配）
        source="auto" + L2 子串:    0.7 ~ 0.95 （依命中长度）
        source="policy_fallback":   0.0 （非匹配，env var 强制 fallback）
    """

    config_name: str | None
    source: str  # "cached_decision" | "auto" | "policy_fallback"
    confidence: float
    available_configs: list[str]
    notes: str = ""


class NeedsUserDecision(Exception):
    """broker 在含糊匹配 + policy="halt" 时抛此异常。

    sw_toolbox_adapter 捕获后 return miss；
    gen_std_parts 累积所有抛出的 record 后一次性原子写 pending 文件。
    broker 自身不写 pending（rev 2 修订）—— 异常携带 record，避免进程崩溃时部分写入。
    """

    def __init__(self, part_no: str, subsystem: str, pending_record: dict[str, Any]):
        super().__init__(f"User decision needed for {subsystem}/{part_no}")
        self.part_no = part_no
        self.subsystem = subsystem
        self.pending_record = pending_record


AUTO_MATCH_THRESHOLD = 0.7

# 尺寸 token 正则：要求 M\d+ 前缀，或含乘号的 \d+×\d+ 形式；排除孤立小数（如标准编号 70.1）
# 分支1：[Φϕφ]? M\d+...（螺栓类，可带乘号后缀）
# 分支2：[Φϕφ]? \d+×\d+...（密封件类，必须含乘号，不接受孤立小数）
_SIZE_TOKEN_RE = re.compile(
    r"[Φϕφ]?\s*(?:[Mm]\d+(?:\.\d+)?(?:\s*[×xX*]\s*\d+(?:\.\d+)?)?)"
    r"|[Φϕφ]?\s*\d+(?:\.\d+)?\s*[×xX*]\s*\d+(?:\.\d+)?"
)


def _normalize_for_match(s: str) -> str:
    """统一归一化：× → x，Φ → 空，去 [-_\\s]，lowercase。"""
    s = s.replace("×", "x").replace("Φ", "").replace("ϕ", "").replace("φ", "")
    s = re.sub(r"[-_\s]", "", s)
    return s.lower()


def _extract_size_tokens(bom_dim_signature: str) -> list[str]:
    """从 bom_dim_signature 提取所有可能的尺寸子串（含 'M8x20', '80x2.4', 'MR105ZZ' 等）。
    返回归一化后的 token 列表。"""
    matches = _SIZE_TOKEN_RE.findall(bom_dim_signature)
    return [_normalize_for_match(m) for m in matches if m.strip()]


def _tok_in_cfg_with_boundary(tok: str, cfg_norm: str) -> bool:
    """L2 子串包含 + 右边界守卫：tok 命中位置后不能紧跟数字。

    防御 'm1' in 'm10x20' 类假阳性（'m1' 是 'm10x20' 真子串但语义不同）。
    左边界由 token 自身格式（含 m 前缀或乘号）保证，无需额外检查。
    """
    idx = cfg_norm.find(tok)
    while idx != -1:
        end = idx + len(tok)
        if end >= len(cfg_norm) or not cfg_norm[end].isdigit():
            return True
        idx = cfg_norm.find(tok, idx + 1)
    return False


def _match_config_by_rule(
    bom_dim_signature: str,
    available: list[str],
) -> tuple[str, float] | None:
    """两层匹配（spec §4.4 #2）。

    L1 精确归一化（confidence=1.0）：尺寸 token 与 available 字符串归一化后等值
    L2 包含子串（confidence=0.7~0.95）：available 字符串归一化后包含尺寸 token

    返回 (matched_config, confidence) 或 None。
    同 confidence 多个候选时取**字符串最短**的（最少干扰）。
    """
    if not available:
        return None

    tokens = _extract_size_tokens(bom_dim_signature)
    if not tokens:
        return None

    # L1: 尺寸 token 与候选归一化后等值
    l1_hits: list[tuple[str, float]] = []
    for cfg in available:
        cfg_norm = _normalize_for_match(cfg)
        for tok in tokens:
            if cfg_norm == tok:
                l1_hits.append((cfg, 1.0))
                break

    if l1_hits:
        # 取字符串最短的
        l1_hits.sort(key=lambda x: len(x[0]))
        return l1_hits[0]

    # L2: 包含子串匹配，优先匹配最长 token（最具体）
    l2_hits: list[tuple[str, float]] = []
    for cfg in available:
        cfg_norm = _normalize_for_match(cfg)
        # 按 token 长度降序遍历，命中最长 token 后即 break
        for tok in sorted(tokens, key=len, reverse=True):
            if tok and _tok_in_cfg_with_boundary(tok, cfg_norm):
                # confidence 随 token 长度增长，短 token 置信度低
                conf = min(0.95, 0.7 + len(tok) / 100.0)
                l2_hits.append((cfg, conf))
                break

    if not l2_hits:
        return None

    # 防御性过滤：当前公式 conf 最低 0.71（len(tok)>=1）≥ 阈值 0.7，no-op；
    # 但保留以便未来 spec 调整阈值/公式下界时自动生效
    l2_hits = [(c, conf) for c, conf in l2_hits if conf >= AUTO_MATCH_THRESHOLD]
    if not l2_hits:
        return None

    # 同 confidence 取字符串最短的（最少干扰）；confidence 高者优先
    l2_hits.sort(key=lambda x: (-x[1], len(x[0])))
    return l2_hits[0]


def _build_bom_dim_signature(bom_row: dict[str, Any]) -> str:
    """组合 name_cn 和 material 为稳定签名（spec §5.1 rev 2）。

    用于决策缓存的 invalidation 比对（bom_dim_signature_changed 触发）。
    缺字段或 None 当空字符串。

    例:
        fastener: '内六角螺栓|GB/T 70.1 M8×20'
        bearing:  '深沟球轴承 6205|GCr15'
        seal:     'O型圈|FKM Φ80×2.4'
    """
    name_cn = bom_row.get("name_cn") or ""
    material = bom_row.get("material") or ""
    return f"{name_cn}|{material}"


def _validate_cached_decision(
    decision: dict[str, Any],
    current_bom_signature: str,
    current_sldprt_filename: str,
    current_available_configs: list[str],
) -> tuple[bool, str | None]:
    """三项校验（spec §5.2）。返回 (is_valid, invalidation_reason)。

    - bom_dim_signature_changed: BOM 行字段变了（用户改了 spec）
    - sldprt_filename_changed: SW 升级换了 SLDPRT 文件
    - config_name_not_in_available_configs: SW 升级后该 config 改名/删除
      （仅 decision="use_config" 时检查；fallback_cadquery 跳过）
    """
    if decision.get("bom_dim_signature") != current_bom_signature:
        return False, "bom_dim_signature_changed"

    if decision.get("sldprt_filename") != current_sldprt_filename:
        return False, "sldprt_filename_changed"

    if decision.get("decision") == "use_config":
        config_name = decision.get("config_name")
        if config_name not in current_available_configs:
            return False, "config_name_not_in_available_configs"

    return True, None


def _build_pending_record(
    bom_row: dict[str, Any],
    sldprt_path: str,
    available: list[str],
    match_failure_reason: str,
    attempted_match: dict[str, Any] | None,
) -> dict[str, Any]:
    """构造单 item 的 pending record（spec §5.3）。

    schema 按 match_failure_reason 分支：
    - no_exact_or_fuzzy_match_with_high_confidence: 推 best L2 + fallback
    - multiple_high_confidence_matches: 列出全部 ≥ 0.7 候选 + fallback
    - com_open_failed: 仅 fallback
    - empty_config_list: use_config "Default" + fallback
    """
    sldprt_filename = Path(sldprt_path).name
    suggested: list[dict[str, Any]] = []

    if match_failure_reason == "no_exact_or_fuzzy_match_with_high_confidence":
        if available:
            tokens = _extract_size_tokens(_build_bom_dim_signature(bom_row))
            best_below: tuple[str, float] | None = None
            for cfg in available:
                cfg_norm = _normalize_for_match(cfg)
                for tok in sorted(tokens, key=len, reverse=True):
                    # 不卡 0.95 上限：让用户看真实近似度
                    if tok and tok in cfg_norm:
                        conf = 0.7 + len(tok) / 100.0
                        if best_below is None or conf > best_below[1]:
                            best_below = (cfg, conf)
                        break
            if best_below:
                suggested.append({
                    "action": "use_config",
                    "config_name": best_below[0],
                    "rationale": f"模糊匹配最近候选（confidence={best_below[1]:.2f}，未达自动阈值 0.7）",
                })
        suggested.append({
            "action": "fallback_cadquery",
            "rationale": "SW 配置略有差异时可用尺寸正确的 CadQuery 近似体",
        })

    elif match_failure_reason == "multiple_high_confidence_matches":
        for cfg in available:
            suggested.append({
                "action": "use_config",
                "config_name": cfg,
                "rationale": "高置信度候选之一",
            })
        suggested.append({
            "action": "fallback_cadquery",
            "rationale": "SW 多候选难辨时可用 CadQuery 近似体",
        })

    elif match_failure_reason == "com_open_failed":
        suggested.append({
            "action": "fallback_cadquery",
            "rationale": "COM 列配置失败，建议使用 CadQuery 近似",
        })

    elif match_failure_reason == "empty_config_list":
        suggested.append({
            "action": "use_config",
            "config_name": "Default",
            "rationale": "SLDPRT 仅含 Default 配置",
        })
        suggested.append({
            "action": "fallback_cadquery",
            "rationale": "默认配置尺寸不匹配时用 CadQuery 近似",
        })

    return {
        "part_no": bom_row.get("part_no", ""),
        "name_cn": bom_row.get("name_cn") or "",
        "material": bom_row.get("material") or "",
        "bom_dim_signature": _build_bom_dim_signature(bom_row),
        "sldprt_path": sldprt_path,
        "sldprt_filename": sldprt_filename,
        "available_configs": available,
        "attempted_match": attempted_match,
        "match_failure_reason": match_failure_reason,
        "suggested_options": suggested,
    }


def _decisions_path() -> Path:
    """返回 spec_decisions.json 路径。

    函数内 import：让 cad_paths.PROJECT_ROOT 实时读，配合 tmp_project_dir
    fixture 的 reload(cad_paths) 机制保证测试隔离。
    """
    from cad_paths import PROJECT_ROOT

    return Path(PROJECT_ROOT) / ".cad-spec-gen" / "spec_decisions.json"


def _empty_envelope() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "last_updated": "",
        "decisions_by_subsystem": {},
        "decisions_history": [],
    }


def _load_decisions_envelope() -> dict[str, Any]:
    """从 spec_decisions.json 读完整 envelope（spec §4.3 / §6）。

    - 文件不存在 → 返回空 envelope（含 schema_version=2）
    - JSON syntax error → ValueError（含行号 + detail）
    - schema_version 不一致 → ValueError 提示删文件重做交互（不自动 migrate）
    """
    path = _decisions_path()
    if not path.exists():
        return _empty_envelope()

    text = path.read_text(encoding="utf-8")
    try:
        env = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"decisions 文件 {path} 第 {exc.lineno} 行 syntax error: {exc.msg}"
        ) from exc

    # 防御 review I-3：合法 JSON 但顶层不是 object 时（如 [1,2,3]），
    # env.get() 会 AttributeError，违反 spec §6 "fail loud 含 detail" 承诺。
    if not isinstance(env, dict):
        raise ValueError(
            f"decisions 文件 {path} 顶层必须是 JSON object，实测 {type(env).__name__}"
        )

    if env.get("schema_version") != SCHEMA_VERSION:
        old_ver = env.get("schema_version")
        backup_path = path.with_suffix(f".v{old_ver}.bak")
        raise ValueError(
            f"决策 schema_version 已升级 v{old_ver}→v{SCHEMA_VERSION}，"
            f"请先备份原文件至 {backup_path}（保留历史决策记录），"
            f"再删除 {path} 后重跑 codegen 让 agent 引导重新决策"
        )

    env.setdefault("decisions_by_subsystem", {})
    env.setdefault("decisions_history", [])
    return env


def _save_decisions_envelope(envelope: dict[str, Any]) -> None:
    """原子写入 spec_decisions.json（先写 .tmp 再 os.replace）。

    review I-1: 不 mutate 入参 — 落盘前 shallow-copy 注入 last_updated，
    避免 caller 多次 save 同一引用时 last_updated 被反复覆盖造成审计混乱。
    """
    path = _decisions_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    to_write = {**envelope, "last_updated": datetime.now(timezone.utc).isoformat()}

    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(to_write, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _get_decision_for_part(
    envelope: dict[str, Any], subsystem: str, part_no: str
) -> dict[str, Any] | None:
    """从 envelope[decisions_by_subsystem][subsystem][part_no] 取，缺失返回 None。

    三层 chained .get(..., {}) 不 mutate envelope（每层 default 是临时空 dict）。
    """
    return (
        envelope.get("decisions_by_subsystem", {})
        .get(subsystem, {})
        .get(part_no)
    )


def _move_decision_to_history(
    envelope: dict[str, Any],
    subsystem: str,
    part_no: str,
    invalidation_reason: str,
) -> None:
    """把 decision 拷贝到 envelope[decisions_history] 并删除原位（in-place）。

    调用方负责 _save_decisions_envelope 持久化。
    invalidation_reason 必须是 INVALIDATION_REASONS 之一（review I-2 校验）。
    """
    if invalidation_reason not in INVALIDATION_REASONS:
        raise ValueError(
            f"未知 invalidation_reason: {invalidation_reason!r}，"
            f"合法值为 {sorted(INVALIDATION_REASONS)}"
        )

    decision = envelope["decisions_by_subsystem"][subsystem].pop(part_no)
    envelope.setdefault("decisions_history", []).append({
        "subsystem": subsystem,
        "part_no": part_no,
        "previous_decision": decision,
        "invalidated_at": datetime.now(timezone.utc).isoformat(),
        "invalidation_reason": invalidation_reason,
    })
