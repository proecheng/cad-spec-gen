"""
adapters/parts/sw_toolbox_adapter.py — SolidWorks Toolbox COM adapter。

实现 PartsAdapter 接口。is_available() 做 6 项检查（v4 §5.3）；
resolve() 编排 catalog 匹配 + com_session 转换（Task 9 实现）。

熔断状态委托给 SwComSession（v4 决策 #22）。
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

from adapters.parts.base import PartsAdapter

log = logging.getLogger(__name__)


def get_toolbox_addin_guid() -> Optional[str]:
    """对外暴露的 Toolbox Add-In GUID 发现入口（Track B1 更新）。

    使用三段式 discover_toolbox_addin_guid()，覆盖历史用户 + 新装机场景。
    """
    from adapters.solidworks.sw_detect import discover_toolbox_addin_guid

    guid, _ = discover_toolbox_addin_guid()
    return guid


_SPEC_RE = re.compile(
    r'^(?P<standard>(?:GB[/／]T|ISO|DIN|JIS)\s*[\d.]+(?:\s+Part\s+\d+)?)'
    r'\s+(?P<size>.+)$'
)
# 已知不覆盖：GB 93（弹垫，无 /T）、ANSI 等 → target_config=None → 使用默认 config


def extract_full_spec(material: str) -> tuple[str, str] | None:
    """从 BOM material 字段解析 (standard, size) 二元组，失败返回 None。"""
    m = _SPEC_RE.match(material.strip())
    return (m.group("standard"), m.group("size")) if m else None


def _build_candidate_config(material: str, resolver_cfg: dict) -> str | None:
    """用 yaml resolver_cfg 将 material 字段转为 SW config 候选名。

    示例: "GB/T 70.1 M6×20" → "GB_T70.1-M6x20"
    resolver_cfg 为空或缺 standard_transforms 时返回 None。
    """
    if not resolver_cfg.get("standard_transforms"):
        return None
    result = extract_full_spec(material)
    if result is None:
        return None
    standard, size = result
    for rule in resolver_cfg["standard_transforms"]:
        standard = standard.replace(rule["from"], rule["to"])
    for rule in resolver_cfg.get("size_transforms", []):
        size = size.replace(rule["from"], rule["to"])
    return f"{standard}{resolver_cfg['separator']}{size}"


class SwToolboxAdapter(PartsAdapter):
    """v4 决策 #14: 从 SolidWorksToolboxAdapter 改名为 SwToolboxAdapter。"""

    name = "sw_toolbox"

    def __init__(self, project_root: str = "", config: Optional[dict] = None) -> None:
        self.project_root = project_root
        self.config = config or {}

        # I-2: 决策 #19 ReDoS 防御必须在配置进入子系统的唯一入口挂钩，
        # 否则 catalog 下游 extract_size_from_name 会对恶意 pattern 运行 re.search。
        # 空 size_patterns 时校验为 no-op，不影响默认构造路径。
        size_patterns = self.config.get("size_patterns", {})
        if size_patterns:
            from adapters.solidworks.sw_toolbox_catalog import validate_size_patterns

            validate_size_patterns(size_patterns)

    def is_available(self) -> tuple[bool, Optional[str]]:
        """B-2 重写：解耦 Add-in 硬门，Add-in 未启用降为 advisory。

        检查顺序：
        1. 非 Windows → False
        2. SW 未安装 → False
        3. 版本 < 2024 → False
        4. pywin32 不可用 → False
        5. toolbox_dir 为空 → False
        6. Standard 版（B-13）→ False
        7. toolbox 物理路径不健康（B-8）→ False
        8. Add-in 未启用 → advisory log only（B-2），不 return False
        9. SwComSession 熔断 → False（v4 决策 #22）
        """
        if sys.platform != "win32":
            return False, "not windows"

        try:
            from adapters.solidworks.sw_detect import detect_solidworks, check_toolbox_path_healthy
            from adapters.solidworks.sw_com_session import get_session
        except ImportError as e:
            return False, f"import failed: {e}"

        info = detect_solidworks()
        if not info.installed:
            return False, "SW not installed"
        if info.version_year < 2024:
            return False, f"SW {info.version_year} too old (need 2024+)"
        if not info.pywin32_available:
            return False, "pywin32 not available"
        if not info.toolbox_dir:
            return False, "toolbox_dir empty"

        # B-13: Standard 版直接拒
        if info.edition == "standard":
            return False, "SW Standard edition does not ship Toolbox Browser DLL"

        # B-8: 物理路径健康校验
        healthy, path_reason = check_toolbox_path_healthy(info)
        if not healthy:
            return False, f"toolbox path unhealthy: {path_reason}"

        # B-2: Add-in 未启用 → advisory log，不阻断
        if not info.toolbox_addin_enabled:
            log.info(
                "SwToolboxAdapter: Toolbox Add-in 未在 SW 菜单里启用 —— "
                "将通过 COM 直接打开 sldprt，不经 Add-in Browser（Track B 决策 B-2）。"
            )

        # v4 决策 #22: 熔断
        session = get_session()
        if not session.is_healthy():
            return False, (
                f"SwComSession circuit breaker tripped; edition={info.edition}"
            )

        return True, None

    def can_resolve(self, query) -> bool:
        """总是 True（具体匹配由 resolve 决定）。"""
        return True

    def resolve(self, query, spec: dict):
        """主编排流程（rev 2 接入 sw_config_broker）。

        步骤：
        1. 加载 Toolbox 索引
        2. 解析 spec（standard / subcategories / part_category）
        3. 抽尺寸（决策 #9：失败 → miss）
        4. 构造加权 tokens
        5. token overlap 打分
        6. sldprt 路径遍历防御（决策 #20）
        7. 委托 broker.resolve_config_for_part 解析 config_name
           - source=auto / cached_decision use_config → 触发 STEP 导出
           - source=cached_decision fallback / policy_fallback → miss 让 CadQuery 兜底
           - 抛 NeedsUserDecision → propagate 给 caller (gen_std_parts)
        """
        from parts_resolver import ResolveResult
        from adapters.solidworks import sw_toolbox_catalog
        from adapters.solidworks.sw_com_session import get_session
        from adapters.solidworks.sw_config_broker import (
            ConfigResolution,
            resolve_config_for_part,
        )
        from adapters.solidworks.sw_detect import detect_solidworks

        info = detect_solidworks()
        toolbox_dir = Path(info.toolbox_dir)

        # 1. 加载索引
        index_path = sw_toolbox_catalog.get_toolbox_index_path(self.config)
        try:
            index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
        except Exception as e:
            log.warning("toolbox 索引加载失败: %s", e)
            return self._miss("index load failed")

        # 2. 解析 spec
        standards = spec.get("standard")
        if isinstance(standards, str):
            standards = [standards]
        subcategories = spec.get("subcategories", [])
        part_category = spec.get("part_category", "fastener")

        # 3. 抽尺寸（决策 #9）
        size_patterns = self.config.get("size_patterns", {}).get(part_category, {})
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""),
            size_patterns,
        )
        if size_dict is None and part_category == "bearing":
            # bearing 型号常见于 material 字段（如 MR105ZZ），name_cn 失败时二次查询
            size_dict = sw_toolbox_catalog.extract_size_from_name(
                getattr(query, "material", "") or "",
                size_patterns,
            )
        if size_dict is None:
            return self._miss("size extraction failed or out of scope")

        # 4. 构造加权 tokens
        weights = self.config.get("token_weights", {})
        query_tokens = sw_toolbox_catalog.build_query_tokens_weighted(
            query,
            size_dict,
            weights,
        )

        # 5. token overlap 打分（spec 层可覆盖全局 min_score）
        min_score = spec.get("min_score", self.config.get("min_score", 0.30))
        match = sw_toolbox_catalog.match_toolbox_part(
            index,
            query_tokens,
            standards,
            subcategories,
            min_score,
        )
        if match is None:
            return self._miss("token overlap below min_score")

        part, score = match

        # 6. 路径遍历防御（决策 #20）
        if not sw_toolbox_catalog._validate_sldprt_path(part.sldprt_path, toolbox_dir):
            return self._miss(
                "sldprt path validation failed (possible index tampering)"
            )

        # 7. 委托 broker 解析 config_name（rev 2 接入 sw_config_broker）
        bom_row = {
            "part_no": getattr(query, "part_no", "") or "",
            "name_cn": getattr(query, "name_cn", "") or "",
            "material": getattr(query, "material", "") or "",
        }
        subsystem = (
            getattr(query, "subsystem", "")
            or spec.get("subsystem", "")
            or "default"
        )

        # NeedsUserDecision 不在此层捕获 —— gen_std_parts 累积 pending 后一次性原子写。
        resolution: ConfigResolution = resolve_config_for_part(
            bom_row=bom_row,
            sldprt_path=part.sldprt_path,
            subsystem=subsystem,
        )

        # broker 已宣告 fallback（cached_decision fallback_cadquery / policy_fallback）
        # → adapter 返回 miss 让 CadQuery 兜底
        if resolution.config_name is None:
            return ResolveResult(
                status="miss",
                kind="miss",
                adapter=self.name,
                metadata={
                    "config_match": resolution.source,
                    "config_confidence": resolution.confidence,
                },
                warnings=[
                    f"broker fallback ({resolution.source}): {resolution.notes}",
                ],
            )

        # 8. config_name 有值 → 构造 cache STEP 路径（含 config 后缀）
        cache_root = sw_toolbox_catalog.get_toolbox_cache_root(self.config)
        safe_config = re.sub(r'[^\w.\-]', '_', resolution.config_name)
        cache_stem = f"{Path(part.filename).stem}_{safe_config}"
        step_abs = cache_root / part.standard / part.subcategory / (cache_stem + ".step")

        # 9. 缓存命中 → 直接返回；未命中 → 触发 COM 转换
        if not step_abs.exists():
            session = get_session()
            if not session.is_healthy():
                return self._miss("COM session unhealthy (circuit breaker tripped)")

            ok = session.convert_sldprt_to_step(
                part.sldprt_path, str(step_abs), resolution.config_name,
            )
            if not ok:
                return self._miss(
                    f"COM convert failed for config={resolution.config_name}"
                )

        dims = self._probe_step_bbox(step_abs)
        return ResolveResult(
            status="hit",
            kind="step_import",
            adapter=self.name,
            step_path=str(step_abs),
            real_dims=dims,
            source_tag=f"sw_toolbox:{part.standard}/{part.subcategory}/{part.filename}",
            metadata={
                "dims": dims,
                "match_score": score,
                "configuration": resolution.config_name,
                "config_match": resolution.source,
                "config_confidence": resolution.confidence,
            },
        )

    def find_sldprt(self, query, spec: dict):
        """公开的 sldprt 匹配 API（不触发 COM）。

        从 resolve() 中抽出 step 1-6（索引加载 + 尺寸提取 + token 打分 + 路径校验），
        返回匹配结果元组，供 sw-warmup --bom / 外部脚本 / 未来 sw-inspect 子命令
        等调用方决定后续动作（COM 转换或其他）。

        Returns:
            (SwToolboxPart, score) — 匹配成功；或 None — 任意步骤失败。
        """
        from adapters.solidworks import sw_toolbox_catalog
        from adapters.solidworks.sw_detect import detect_solidworks

        info = detect_solidworks()
        if not info.toolbox_dir:
            return None
        toolbox_dir = Path(info.toolbox_dir)

        # 解析 spec
        standards = spec.get("standard")
        if isinstance(standards, str):
            standards = [standards]
        subcategories = spec.get("subcategories", [])
        part_category = spec.get("part_category", "fastener")

        # 抽尺寸（决策 #9：失败 → None）
        size_patterns = self.config.get("size_patterns", {}).get(part_category, {})
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""),
            size_patterns,
        )
        if size_dict is None and part_category == "bearing":
            size_dict = sw_toolbox_catalog.extract_size_from_name(
                getattr(query, "material", "") or "",
                size_patterns,
            )
        if size_dict is None:
            return None

        # 加载索引
        index_path = sw_toolbox_catalog.get_toolbox_index_path(self.config)
        try:
            index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
        except Exception:
            return None

        # 构造加权 tokens + 打分
        weights = self.config.get("token_weights", {})
        query_tokens = sw_toolbox_catalog.build_query_tokens_weighted(
            query,
            size_dict,
            weights,
        )
        match = sw_toolbox_catalog.match_toolbox_part(
            index,
            query_tokens,
            standards,
            subcategories,
            self.config.get("min_score", 0.30),
        )
        if match is None:
            return None

        part, score = match

        # 路径遍历防御（决策 #20）
        if not sw_toolbox_catalog._validate_sldprt_path(part.sldprt_path, toolbox_dir):
            return None

        return (part, score)

    def _miss(self, reason: str):
        """构造 miss ResolveResult 并记录调试日志。"""
        from parts_resolver import ResolveResult

        log.debug("sw_toolbox miss: %s", reason)
        return ResolveResult(
            status="miss",
            kind="miss",
            adapter=self.name,
            warnings=[reason],
        )

    def _probe_step_bbox(self, step_path: Path) -> Optional[tuple]:
        """复用 step_pool_adapter 的 bbox 探测逻辑。失败返回 None。

        尝试用 cadquery 加载 STEP 并读取包围盒（xlen, ylen, zlen），单位 mm。
        cadquery 不可用或加载失败时静默返回 None（§1.3 已知限制）。
        """
        try:
            import cadquery as cq

            obj = cq.importers.importStep(str(step_path))
            bb = obj.val().BoundingBox()
            return (
                round(bb.xlen, 2),
                round(bb.ylen, 2),
                round(bb.zlen, 2),
            )
        except Exception:
            return None

    def prewarm(self, candidates) -> None:
        """Pre-warm broker config_lists cache（Task 14.6 / spec §3.1）。

        candidates: list[tuple[PartQuery, dict]] — PartsResolver 已 rule-match
        派发到本 adapter 的 (query, rule.spec) 列表。

        流程：
          1. 对每对 (query, spec) 调 find_sldprt 收集 sldprt_path（catalog-only，不触发 COM）
          2. 收集到 ≥1 个 sldprt → 调 broker.prewarm_config_lists 触发 batch spawn worker
          3. 收集到 0 个 → broker 不调（避免 prewarm 空 batch overhead）

        失败容忍：本层不嵌套 try/except；PartsResolver.prewarm 已有 per-adapter 兜底。
        """
        from adapters.solidworks.sw_config_broker import prewarm_config_lists

        sldprt_paths = []
        for query, spec in candidates:
            match = self.find_sldprt(query, spec)
            if match is None:
                continue
            part, _score = match
            sldprt_paths.append(part.sldprt_path)

        if not sldprt_paths:
            return

        prewarm_config_lists(sldprt_paths)

    def probe_dims(self, query, spec: dict) -> Optional[tuple]:
        """v4 §1.3 已知限制: 缓存未命中 → None。

        避免为了测尺寸而触发 COM 启动。建议用户 sw-warmup 预热。
        """
        from adapters.solidworks import sw_toolbox_catalog
        from adapters.solidworks.sw_detect import detect_solidworks

        info = detect_solidworks()
        if not info.toolbox_dir:
            return None
        toolbox_dir = Path(info.toolbox_dir)

        _probe_part_category = spec.get("part_category", "fastener")
        size_patterns = self.config.get("size_patterns", {}).get(
            _probe_part_category, {}
        )
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""),
            size_patterns,
        )
        if size_dict is None and _probe_part_category == "bearing":
            size_dict = sw_toolbox_catalog.extract_size_from_name(
                getattr(query, "material", "") or "",
                size_patterns,
            )
        if size_dict is None:
            return None

        index_path = sw_toolbox_catalog.get_toolbox_index_path(self.config)
        try:
            index = sw_toolbox_catalog.load_toolbox_index(index_path, toolbox_dir)
        except Exception:
            return None

        standards = spec.get("standard")
        if isinstance(standards, str):
            standards = [standards]

        weights = self.config.get("token_weights", {})
        query_tokens = sw_toolbox_catalog.build_query_tokens_weighted(
            query,
            size_dict,
            weights,
        )
        match = sw_toolbox_catalog.match_toolbox_part(
            index,
            query_tokens,
            standards,
            spec.get("subcategories", []),
            self.config.get("min_score", 0.30),
        )
        if match is None:
            return None

        part, _ = match
        cache_root = sw_toolbox_catalog.get_toolbox_cache_root(self.config)
        # 镜像 resolve() 步骤 7：有 config_name_resolver 时使用带后缀的缓存路径（M-1 修复）
        resolver_cfg = self.config.get("config_name_resolver", {})
        material = getattr(query, "material", "") or ""
        target_config = _build_candidate_config(material, resolver_cfg) if resolver_cfg else None
        safe_config = re.sub(r'[^\w.\-]', '_', target_config) if target_config else ""
        cache_stem = (
            f"{Path(part.filename).stem}_{safe_config}"
            if safe_config
            else Path(part.filename).stem
        )
        step_abs = (
            cache_root
            / part.standard
            / part.subcategory
            / (cache_stem + ".step")
        )
        if not step_abs.exists():
            return None  # 决策 #4: 缓存未命中 → 不触发 COM

        return self._probe_step_bbox(step_abs)
