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

# 尺寸 token 正则：数字（含小数）+ 任意分隔符 + 数字 / 单 M\d+
_SIZE_TOKEN_RE = re.compile(r"[ΦΦϕφ]?\s*[Mm]?\d+(?:\.\d+)?(?:\s*[×xX×*]\s*\d+(?:\.\d+)?)?")


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


def _match_config_by_rule(
    bom_dim_signature: str,
    available: list[str],
) -> tuple[str, float] | None:
    """两层匹配（spec §4.4 #2）。

    L1 精确归一化（confidence=1.0）：尺寸 token 与 available 字符串归一化后等值
    L2 包含子串（confidence=0.7~0.95）：available 字符串归一化后包含尺寸 token
      （L2 在 Task 5 实现）

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

    # L2 在下个 task 实现
    return None


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
