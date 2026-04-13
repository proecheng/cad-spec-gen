"""
adapters/parts/sw_toolbox_adapter.py — SolidWorks Toolbox COM adapter。

实现 PartsAdapter 接口。is_available() 做 6 项检查（v4 §5.3）；
resolve() 编排 catalog 匹配 + com_session 转换（Task 9 实现）。

熔断状态委托给 SwComSession（v4 决策 #22）。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from adapters.parts.base import PartsAdapter

log = logging.getLogger(__name__)


class SwToolboxAdapter(PartsAdapter):
    """v4 决策 #14: 从 SolidWorksToolboxAdapter 改名为 SwToolboxAdapter。"""

    name = "sw_toolbox"

    def __init__(self, project_root: str = "", config: Optional[dict] = None) -> None:
        self.project_root = project_root
        self.config = config or {}

    def is_available(self) -> bool:
        """v4 §5.3: 6 项检查全通过。

        检查顺序（短路优先）：
        1. 非 Windows 平台 → False
        2. SolidWorks 未安装 → False
        3. 版本低于 2024 → False
        4. pywin32 不可用 → False
        5. Toolbox 目录为空 → False
        6. Toolbox Add-In 未启用 → False（v4 决策 #13）
        7. SwComSession 熔断 → False（v4 决策 #22）
        """
        if sys.platform != "win32":
            return False

        try:
            from adapters.solidworks.sw_detect import detect_solidworks
            from adapters.solidworks.sw_com_session import get_session
        except ImportError:
            return False

        info = detect_solidworks()
        if not info.installed:
            return False
        if info.version_year < 2024:
            return False
        if not info.pywin32_available:
            return False
        if not info.toolbox_dir:
            return False
        if not info.toolbox_addin_enabled:
            return False

        # v4 决策 #22: 熔断委托给 SwComSession
        session = get_session()
        if not session.is_healthy():
            return False

        return True

    def can_resolve(self, query) -> bool:
        """总是 True（具体匹配由 resolve 决定）。"""
        return True

    def resolve(self, query, spec: dict):
        """主编排流程（v4 §3.2）。

        步骤：
        1. 加载 Toolbox 索引
        2. 解析 spec（standard / subcategories / part_category）
        3. 抽尺寸（决策 #9：失败 → miss）
        4. 构造加权 tokens
        5. token overlap 打分
        6. sldprt 路径遍历防御（决策 #20）
        7. 构造缓存 STEP 路径
        8. 缓存命中 → 直接返回（不触发 COM）
        9. 缓存未命中 → 触发 COM 转换
        """
        from parts_resolver import ResolveResult
        from adapters.solidworks import sw_toolbox_catalog
        from adapters.solidworks.sw_com_session import get_session
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
        if size_dict is None:
            return self._miss("size extraction failed or out of scope")

        # 4. 构造加权 tokens
        weights = self.config.get("token_weights", {})
        query_tokens = sw_toolbox_catalog.build_query_tokens_weighted(
            query, size_dict, weights,
        )

        # 5. token overlap 打分
        min_score = self.config.get("min_score", 0.30)
        match = sw_toolbox_catalog.match_toolbox_part(
            index, query_tokens, standards, subcategories, min_score,
        )
        if match is None:
            return self._miss("token overlap below min_score")

        part, score = match

        # 6. 路径遍历防御（决策 #20）
        if not sw_toolbox_catalog._validate_sldprt_path(part.sldprt_path, toolbox_dir):
            return self._miss("sldprt path validation failed (possible index tampering)")

        # 7. 构造缓存 STEP 路径
        cache_root = sw_toolbox_catalog.get_toolbox_cache_root(self.config)
        step_relative = (
            Path(part.standard) / part.subcategory / (Path(part.filename).stem + ".step")
        )
        step_abs = cache_root / step_relative

        # 8. 缓存命中 → 直接返回
        if step_abs.exists():
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
                    "configuration": "<default>",
                },
            )

        # 9. 缓存未命中 → 触发 COM
        session = get_session()
        if not session.is_healthy():
            return self._miss("COM session unhealthy (circuit breaker tripped)")

        ok = session.convert_sldprt_to_step(part.sldprt_path, str(step_abs))
        if not ok:
            return self._miss("COM convert failed")

        dims = self._probe_step_bbox(step_abs)
        return ResolveResult(
            status="hit",
            kind="step_import",
            adapter=self.name,
            step_path=str(step_abs),
            real_dims=dims,
            source_tag=f"sw_toolbox:{part.standard}/{part.subcategory}/{part.filename}",
            metadata={"dims": dims, "match_score": score, "configuration": "<default>"},
        )

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

        size_patterns = self.config.get("size_patterns", {}).get(
            spec.get("part_category", "fastener"), {}
        )
        size_dict = sw_toolbox_catalog.extract_size_from_name(
            getattr(query, "name_cn", ""), size_patterns,
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
            query, size_dict, weights,
        )
        match = sw_toolbox_catalog.match_toolbox_part(
            index, query_tokens, standards, spec.get("subcategories", []),
            self.config.get("min_score", 0.30),
        )
        if match is None:
            return None

        part, _ = match
        cache_root = sw_toolbox_catalog.get_toolbox_cache_root(self.config)
        step_abs = cache_root / part.standard / part.subcategory / (
            Path(part.filename).stem + ".step"
        )
        if not step_abs.exists():
            return None  # 决策 #4: 缓存未命中 → 不触发 COM

        return self._probe_step_bbox(step_abs)
