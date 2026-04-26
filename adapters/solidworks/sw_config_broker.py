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

import re
from dataclasses import dataclass
from typing import Any


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
