"""
adapters/parts/sw_parametric_adapter.py — SW COM API 参数化建模适配器。

当 SolidWorks 可用时，用 SW API 创建参数化特征并导出 STEP；
不可用时返回 None，调用方回退到 CadQuery 路径。

SW API 尺寸单位为米（m），内部统一 /1000 换算。
"""
from __future__ import annotations

import logging
import math
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_VALID_TEMPLATES = {
    "flange", "housing", "bracket", "spring_mechanism",
    "sleeve", "plate", "arm", "cover",
}

try:
    import win32com.client as _wc
    import pythoncom as _pc
    _VARIANT_NULL = _wc.VARIANT(_pc.VT_DISPATCH, None)
except ImportError:
    _VARIANT_NULL = None  # 非 Windows；_build_* 仅在 is_available()=True 后调用


def detect_solidworks():
    """封装 sw_detect.detect_solidworks，便于测试 patch。"""
    from adapters.solidworks.sw_detect import detect_solidworks as _det
    return _det()


class SwParametricAdapter:
    """SW COM API 参数化建模适配器（Task 15 框架 + Task 16-18 完整实现）。"""

    def is_available(self) -> tuple[bool, str | None]:
        """复用 sw_toolbox_adapter 的 6 项检查模式（平台 / 安装 / 版本 / pywin32 / toolbox / COM）。"""
        if sys.platform != "win32":
            return False, "非 Windows 平台"
        try:
            from adapters.solidworks.sw_com_session import get_session
        except ImportError:
            return False, "sw_com_session 不可导入"

        info = detect_solidworks()
        if not info.installed:
            return False, "SolidWorks 未安装"
        if info.version_year < 2024:
            return False, f"SW 版本 {info.version_year} < 2024"
        if not info.pywin32_available:
            return False, "pywin32 不可用"

        session = get_session()
        if not session.is_healthy():
            return False, "COM session 熔断"

        return True, None

    def build_part(
        self,
        tpl_type: str,
        params: dict,
        output_dir: Path,
        part_no: str,
    ) -> Path | None:
        """调用对应 SW 建模方法，导出 STEP 到 output_dir/{part_no}.step。

        Returns:
            STEP 绝对路径（Path）；任意步骤失败返回 None。
        """
        ok, _ = self.is_available()
        if not ok:
            return None
        if tpl_type not in _VALID_TEMPLATES:
            log.warning("未知模板类型: %s", tpl_type)
            return None

        step_path = Path(output_dir) / f"{part_no}.step"

        # 缓存检查在 is_available() 之后：SW 不可用时不信任旧缓存，强制回退 CadQuery 路径。
        # 缓存必须可被 CadQuery 导入为实体；仅“文件存在”不足以证明导出成功。
        if step_path.exists():
            if (self._validate_step_geometry(step_path)
                    and self._validate_step_contract(tpl_type, params, step_path)):
                return step_path
            log.warning("SW STEP 缓存不满足几何契约，删除并重建: %s", step_path)
            self._unlink_step(step_path)

        try:
            build_fn = getattr(self, f"_build_{tpl_type}", None)
            if build_fn is None:
                log.debug("_build_%s 尚未实现，回退 CadQuery", tpl_type)
                return None
            built = build_fn(params, step_path)
            if built is None:
                return None
            built_path = Path(built)
            if self._validate_step_geometry(built_path):
                return built_path
            log.warning("SW 导出 STEP 无可导入几何，回退 CadQuery: %s", built_path)
            self._unlink_step(built_path)
            return self._build_cadquery_fallback(tpl_type, params, step_path)
        except Exception as exc:
            log.warning("SW 建模失败 [%s/%s]: %s", tpl_type, part_no, exc, exc_info=True)
            return None

    def _validate_step_geometry(self, step_path: Path) -> bool:
        """Return True only when STEP imports to at least one shape object."""
        try:
            if not step_path.exists() or step_path.stat().st_size <= 0:
                return False
            import cadquery as cq

            wp = cq.importers.importStep(str(step_path))
            objects = list(getattr(wp, "objects", []) or [])
            if not objects and hasattr(wp, "vals"):
                objects = list(wp.vals() or [])

            for obj in objects:
                if not hasattr(obj, "BoundingBox"):
                    continue
                try:
                    obj.BoundingBox()
                    return True
                except Exception:
                    continue
            return False
        except Exception as exc:
            log.warning("STEP 几何校验失败 [%s]: %s", step_path, exc)
            return False

    def _validate_step_contract(
        self, tpl_type: str, params: dict, step_path: Path
    ) -> bool:
        """Validate template-specific STEP axis/dimension contract.

        A STEP can be importable while still violating the downstream CAD
        convention. For plates, assembly.py assumes X=width, Y=depth, and
        Z=thickness with bottom face at Z=0. Old Top-Plane exports produced
        X=width, Y=thickness, Z=depth; reject those caches so force/codegen can
        rebuild them with the corrected Front-Plane implementation.
        """
        if tpl_type != "plate":
            return True
        try:
            import cadquery as cq

            wp = cq.importers.importStep(str(step_path))
            bbox = wp.val().BoundingBox()
            actual = (
                float(bbox.xlen),
                float(bbox.ylen),
                float(bbox.zlen),
            )
            expected = (
                float(params.get("width") or 0),
                float(params.get("depth") or 0),
                float(params.get("thickness") or 0),
            )
            if any(v <= 0 for v in expected):
                return True
            tol = 0.5  # mm; enough for STEP/export numeric noise
            return all(abs(a - e) <= tol for a, e in zip(actual, expected))
        except Exception as exc:
            log.warning("STEP 契约校验失败 [%s]: %s", step_path, exc)
            return False

    def _unlink_step(self, step_path: Path) -> None:
        try:
            step_path.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("无法删除无效 STEP [%s]: %s", step_path, exc)

    def _build_cadquery_fallback(
        self, tpl_type: str, params: dict, step_path: Path
    ) -> Path | None:
        """Export a CadQuery fallback when SW returns an empty STEP."""
        try:
            import cadquery as cq

            body = self._make_cadquery_fallback_body(tpl_type, params)
            if body is None:
                return None
            step_path.parent.mkdir(parents=True, exist_ok=True)
            cq.exporters.export(body, str(step_path))
            if self._validate_step_geometry(step_path):
                return step_path
            self._unlink_step(step_path)
            return None
        except Exception as exc:
            log.warning("CadQuery 回退建模失败 [%s/%s]: %s", tpl_type, step_path, exc)
            self._unlink_step(step_path)
            return None

    def _make_cadquery_fallback_body(self, tpl_type: str, params: dict):
        """Return a minimal valid body matching the SW template contract."""
        if tpl_type == "flange":
            return self._make_fallback_flange(params)
        if tpl_type == "spring_mechanism":
            return self._make_fallback_spring_mechanism(params)
        return None

    def _make_fallback_flange(self, params: dict):
        import cadquery as cq

        od = float(params.get("od") or 0)
        thickness = float(params.get("thickness") or 0)
        if od <= 0 or thickness <= 0:
            return None
        id_ = float(params.get("id") or 0) or od * 0.25
        if id_ >= od:
            return None
        pcd = float(params.get("bolt_pcd") or 0) or od * 0.75
        bolt_n = max(0, int(params.get("bolt_count") or 6))
        boss_h = max(0.0, float(params.get("boss_h") or 0))
        bolt_d = max(od * 0.07, 5.0)

        body = cq.Workplane("XY").circle(od / 2).extrude(thickness)
        body = body.faces(">Z").workplane().circle(id_ / 2).cutThruAll()
        if bolt_n > 0 and pcd > 0:
            points = [
                (
                    pcd / 2 * math.cos(2 * math.pi * i / bolt_n),
                    pcd / 2 * math.sin(2 * math.pi * i / bolt_n),
                )
                for i in range(bolt_n)
            ]
            body = (
                body.faces(">Z")
                .workplane()
                .pushPoints(points)
                .circle(bolt_d / 2)
                .cutThruAll()
            )
        if boss_h > 0:
            boss_od = min(id_ * 1.5, od * 0.5) if id_ > 0 else od * 0.4
            boss = (
                cq.Workplane("XY")
                .circle(boss_od / 2)
                .circle(id_ / 2)
                .extrude(boss_h)
                .translate((0, 0, thickness))
            )
            body = body.union(boss)
        return body

    def _make_fallback_spring_mechanism(self, params: dict):
        import cadquery as cq

        od = float(params.get("od") or 0)
        free_length = float(params.get("free_length") or 0)
        if od <= 0 or free_length <= 0:
            return None
        id_ = float(params.get("id") or 0) or od * 0.5
        if id_ >= od:
            return None
        wire_d = float(params.get("wire_d") or 0) or od * 0.08
        coil_n = max(1, int(params.get("coil_n") or 6))
        flange_od = od * 1.25
        flange_h = wire_d * 2

        body = cq.Workplane("XY").circle(od / 2).circle(id_ / 2).extrude(free_length)
        bottom = (
            cq.Workplane("XY")
            .circle(flange_od / 2)
            .circle(id_ / 2)
            .extrude(flange_h)
            .translate((0, 0, -flange_h))
        )
        top = (
            cq.Workplane("XY")
            .circle(flange_od / 2)
            .circle(id_ / 2)
            .extrude(flange_h)
            .translate((0, 0, free_length))
        )
        body = body.union(bottom).union(top)

        seg_od = od + wire_d * 0.8
        seg_h = min(free_length / coil_n * 0.4, wire_d * 3)
        pitch = free_length / coil_n
        for i in range(coil_n):
            z = i * pitch + (pitch - seg_h) / 2
            ring = (
                cq.Workplane("XY")
                .circle(seg_od / 2)
                .circle(od / 2 * 0.98)
                .extrude(seg_h)
                .translate((0, 0, z))
            )
            body = body.union(ring)
        return body

    # ── 各模板 SW 建模方法（Task 16-18 实现） ──────────────────────────────

    def _build_flange(self, params: dict, step_path: Path) -> Path | None:
        """法兰建模（Task 16 实现）。

        SW COM API 实机验证约定（SW 2024）：
        - FeatureExtrusion3 有 23 个参数（含 UseFeatScope/UseAutoSelect/T0/StartOffset/FlipStartOffset）
        - FeatureCut3 有 26 个参数（含 NormalCut/AssemblyFeatureScope/AutoSelectComponents/PropagateFeatureToParts）
        - swEndCondBlind=0，swEndCondThroughAll=6
        - FeatureCut3 在 Python 中返回 None 是正常的 COM 编组行为，特征实际已创建
        """
        od_mm = float(params.get("od") or 0)
        thick_mm = float(params.get("thickness") or 0)
        if od_mm <= 0 or thick_mm <= 0:
            return None

        id_mm = float(params.get("id") or 0)
        pcd_mm = float(params.get("bolt_pcd") or 0) or od_mm * 0.75
        bolt_n = int(params.get("bolt_count") or 6)
        boss_h_mm = float(params.get("boss_h") or 0)
        bolt_d_mm = max(od_mm * 0.07, 5.0)

        od = od_mm / 1000
        thick = thick_mm / 1000
        id_ = id_mm / 1000 if id_mm > 0 else od * 0.25
        pcd = pcd_mm / 1000
        bolt_d = bolt_d_mm / 1000
        boss_h = boss_h_mm / 1000

        swapp = self._get_swapp()
        model = None
        try:
            model = self._new_part_doc(swapp)
            if model is None:
                return None
            import math
            ftMgr = model.FeatureManager
            skMgr = model.SketchManager

            # 法兰盘体：外圆 + 内孔同草图 → 环形截面 extrude（向+Y）
            # FeatureExtrusion3 参数：Sd, Flip, Dir, T1, T2, D1, D2,
            #   Dchk1, Dchk2, Ddir1, Ddir2, Dang1, Dang2,
            #   OffsetReverse1, OffsetReverse2, TranslateSurface1, TranslateSurface2,
            #   Merge, UseFeatScope, UseAutoSelect, T0, StartOffset, FlipStartOffset
            model.Extension.SelectByID2(
                "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCircleByRadius(0, 0, 0, od / 2)
            skMgr.CreateCircleByRadius(0, 0, 0, id_ / 2)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                True, False, False, 0, 0, thick, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                True, True, True, 0, 0.0, False)

            # 螺栓孔 Cut（Through All = swEndCondThroughAll = 6）
            # FeatureCut3 参数：Sd, Flip, Dir, T1, T2, D1, D2,
            #   Dchk1, Dchk2, Ddir1, Ddir2, Dang1, Dang2,
            #   OffsetReverse1, OffsetReverse2, TranslateSurface1, TranslateSurface2,
            #   NormalCut, UseFeatScope, UseAutoSelect,
            #   AssemblyFeatureScope, AutoSelectComponents, PropagateFeatureToParts,
            #   T0, StartOffset, FlipStartOffset
            # 注：Python COM 编组 FeatureCut3 返回 None 但特征已创建（SW 2024 实机验证）
            if bolt_n > 0 and pcd > 0:
                model.Extension.SelectByID2(
                    "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
                skMgr.InsertSketch(True)
                for i in range(bolt_n):
                    angle = 2 * math.pi * i / bolt_n
                    cx = pcd / 2 * math.cos(angle)
                    cz = pcd / 2 * math.sin(angle)
                    skMgr.CreateCircleByRadius(cx, cz, 0, bolt_d / 2)
                skMgr.InsertSketch(True)
                ftMgr.FeatureCut3(
                    True, False, False, 6, 0, 0.0, 0.0,
                    False, False, False, False, 0.0, 0.0,
                    False, False, False, False,
                    False, True, True,
                    False, False, False,
                    0, 0.0, False)

            # Boss 凸台（可选，Flip=True 向-Y 方向）
            if boss_h > 0:
                boss_od = min(id_ * 1.5, od * 0.5) if id_ > 0 else od * 0.4
                model.Extension.SelectByID2(
                    "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
                skMgr.InsertSketch(True)
                skMgr.CreateCircleByRadius(0, 0, 0, boss_od / 2)
                skMgr.CreateCircleByRadius(0, 0, 0, id_ / 2)
                skMgr.InsertSketch(True)
                ftMgr.FeatureExtrusion3(
                    True, True, False, 0, 0, boss_h, 0.0,
                    False, False, False, False, 0.0, 0.0,
                    False, False, False, False,
                    True, True, True, 0, 0.0, False)

            if not self._export_step(model, step_path):
                return None
            return step_path
        except Exception as exc:
            log.warning("_build_flange 失败: %s", exc, exc_info=True)
            return None
        finally:
            self._close_doc(swapp, model)

    def _build_housing(self, params: dict, step_path: Path) -> Path | None:
        """外壳建模（Task 17 实现）。

        绘制外壳 Box，再用 FeatureExtrusion3 盲切挖内腔（留底壁和侧壁）。
        结果：开顶盒体 — 4 侧壁 + 1 底壁，无顶盖。
        """
        w_mm = float(params.get("width") or 0)
        d_mm = float(params.get("depth") or 0)
        h_mm = float(params.get("height") or 0)
        if w_mm <= 0 or d_mm <= 0 or h_mm <= 0:
            return None

        # C1 修复：fallback 必须在 mm 域计算，/1000 统一在最后
        wall_t_mm = float(params.get("wall_t") or 0) or (max(w_mm, d_mm) * 0.12)
        w = w_mm / 1000
        d = d_mm / 1000
        h = h_mm / 1000
        wall = wall_t_mm / 1000

        swapp = self._get_swapp()
        model = None
        try:
            model = self._new_part_doc(swapp)
            if model is None:
                return None
            ftMgr = model.FeatureManager
            skMgr = model.SketchManager

            # 外壳 Box（上视基准面 = XZ 平面，向+Y）
            model.Extension.SelectByID2(
                "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCenterRectangle(0, 0, 0, w / 2, d / 2, 0)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                True, False, False, 0, 0, h, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                True, True, True, 0, 0.0, False)

            # 内腔 Cut（从顶面向下盲切，深度 h-wall，留底壁）
            # FeatureExtrusion3：T1=0=swEndCondBlind，Dir=True（反向切入）；SW 2024 实机验证
            cut_depth = h - wall
            if cut_depth > 0:
                model.Extension.SelectByID2(
                    "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
                skMgr.InsertSketch(True)
                skMgr.CreateCenterRectangle(
                    0, 0, 0, (w - 2 * wall) / 2, (d - 2 * wall) / 2, 0)
                skMgr.InsertSketch(True)
                # FeatureExtrusion3 参数（23 params）同 _build_flange — SW 2024 实机验证
                # 第 3 参数 True = 反向（切入实体），T1=0 = Blind，D1=cut_depth
                ftMgr.FeatureExtrusion3(
                    True, False, True, 0, 0, cut_depth, 0.0,
                    False, False, False, False, 0.0, 0.0,
                    False, False, False, False,
                    True, True, True, 0, 0.0, False)

            if not self._export_step(model, step_path):
                return None
            return step_path
        except Exception as exc:
            log.warning("_build_housing 失败: %s", exc, exc_info=True)
            return None
        finally:
            self._close_doc(swapp, model)

    def _build_bracket(self, params: dict, step_path: Path) -> Path | None:
        """支架建模（Task 17 实现）。

        L 形截面轮廓（XY 平面）沿+Z 方向 extrude，构成直角支架。
        """
        w_mm = float(params.get("width") or 0)
        h_mm = float(params.get("height") or 0)
        t_mm = float(params.get("thickness") or 0)
        if w_mm <= 0 or h_mm <= 0 or t_mm <= 0:
            return None

        w = w_mm / 1000      # extrude 深度（Z 方向）
        h = h_mm / 1000      # 竖壁高度
        t = t_mm / 1000      # 板厚
        base_d = h * 0.6     # 底板水平长度

        swapp = self._get_swapp()
        model = None
        try:
            model = self._new_part_doc(swapp)
            if model is None:
                return None
            ftMgr = model.FeatureManager
            skMgr = model.SketchManager

            # 前视基准面 = XY 平面，Extrude 沿+Z
            model.Extension.SelectByID2(
                "前视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
            skMgr.InsertSketch(True)
            # L 轮廓（XY 坐标，逆时针闭合）
            skMgr.CreateLine(0,      0,  0, base_d, 0,  0)
            skMgr.CreateLine(base_d, 0,  0, base_d, t,  0)
            skMgr.CreateLine(base_d, t,  0, t,      t,  0)
            skMgr.CreateLine(t,      t,  0, t,      h,  0)
            skMgr.CreateLine(t,      h,  0, 0,      h,  0)
            skMgr.CreateLine(0,      h,  0, 0,      0,  0)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                True, False, False, 0, 0, w, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                True, True, True, 0, 0.0, False)

            if not self._export_step(model, step_path):
                return None
            return step_path
        except Exception as exc:
            log.warning("_build_bracket 失败: %s", exc, exc_info=True)
            return None
        finally:
            self._close_doc(swapp, model)

    def _build_sleeve(self, params: dict, step_path: Path) -> Path | None:
        """套筒建模（Task 17 实现）。

        同心双圆环形截面 extrude，构成空心套筒。
        """
        od_mm = float(params.get("od") or 0)
        len_mm = float(params.get("length") or 0)
        if od_mm <= 0 or len_mm <= 0:
            return None

        id_mm = float(params.get("id") or 0) or od_mm * 0.5
        od = od_mm / 1000
        id_ = id_mm / 1000
        length = len_mm / 1000

        swapp = self._get_swapp()
        model = None
        try:
            model = self._new_part_doc(swapp)
            if model is None:
                return None
            ftMgr = model.FeatureManager
            skMgr = model.SketchManager

            # 同心双圆 → 环形截面 extrude（向+Y）
            model.Extension.SelectByID2(
                "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCircleByRadius(0, 0, 0, od / 2)
            skMgr.CreateCircleByRadius(0, 0, 0, id_ / 2)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                True, False, False, 0, 0, length, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                True, True, True, 0, 0.0, False)

            if not self._export_step(model, step_path):
                return None
            return step_path
        except Exception as exc:
            log.warning("_build_sleeve 失败: %s", exc, exc_info=True)
            return None
        finally:
            self._close_doc(swapp, model)

    def _build_spring_mechanism(self, params: dict, step_path: Path) -> Path | None:
        """弹簧机构建模（Task 18 实现）。

        主体：中空圆柱（外径 od，内径 id，高度 free_length）向+Y extrude。
        底端法兰：外径 flange_od = od*1.25，厚度 flange_h = wire_d*2，向-Y extrude。
        顶端法兰：同外径，向+Y extrude。
        coil_n 外凸环：外径 od + wire_d*0.8，薄壁环，每段独立 try，失败只记 warning。
        """
        od_mm = float(params.get("od") or 0)
        fl_mm = float(params.get("free_length") or 0)
        if od_mm <= 0 or fl_mm <= 0:
            return None

        id_mm = float(params.get("id") or 0) or od_mm * 0.5
        wire_d_mm = float(params.get("wire_d") or 0) or od_mm * 0.08
        coil_n = int(params.get("coil_n") or 6)

        od = od_mm / 1000
        id_ = id_mm / 1000
        fl = fl_mm / 1000
        wire_d = wire_d_mm / 1000
        flange_od = od * 1.25
        flange_h = wire_d * 2

        swapp = self._get_swapp()
        model = None
        try:
            model = self._new_part_doc(swapp)
            if model is None:
                return None
            ftMgr = model.FeatureManager
            skMgr = model.SketchManager

            # 主体中空圆柱（向+Y，高度 fl）
            model.Extension.SelectByID2(
                "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCircleByRadius(0, 0, 0, od / 2)
            skMgr.CreateCircleByRadius(0, 0, 0, id_ / 2)
            skMgr.InsertSketch(True)
            # FeatureExtrusion3 参数（23 params）— SW 2024 实机验证
            ftMgr.FeatureExtrusion3(
                True, False, False, 0, 0, fl, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                True, True, True, 0, 0.0, False)

            # 底端法兰（同平面 Flip=True 向-Y）
            model.Extension.SelectByID2(
                "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCircleByRadius(0, 0, 0, flange_od / 2)
            skMgr.CreateCircleByRadius(0, 0, 0, id_ / 2)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                True, True, False, 0, 0, flange_h, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                True, True, True, 0, 0.0, False)

            # 顶端法兰（同平面 Flip=False 向+Y）
            model.Extension.SelectByID2(
                "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCircleByRadius(0, 0, 0, flange_od / 2)
            skMgr.CreateCircleByRadius(0, 0, 0, id_ / 2)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                True, False, False, 0, 0, flange_h, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                True, True, True, 0, 0.0, False)

            # coil_n 外凸环段（每段独立 try，失败只记 warning 继续）
            seg_od = od + wire_d * 0.8
            seg_h = min(fl / max(coil_n, 1) * 0.4, wire_d * 3)
            for _ in range(coil_n):
                try:
                    model.Extension.SelectByID2(
                        "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
                    skMgr.InsertSketch(True)
                    skMgr.CreateCircleByRadius(0, 0, 0, seg_od / 2)
                    skMgr.CreateCircleByRadius(0, 0, 0, od / 2 * 0.98)
                    skMgr.InsertSketch(True)
                    ftMgr.FeatureExtrusion3(
                        True, False, False, 0, 0, seg_h, 0.0,
                        False, False, False, False, 0.0, 0.0,
                        False, False, False, False,
                        True, True, True, 0, 0.0, False)
                except Exception as exc:
                    log.warning("_build_spring_mechanism 外环段失败（跳过）: %s", exc)

            if not self._export_step(model, step_path):
                return None
            return step_path
        except Exception as exc:
            log.warning("_build_spring_mechanism 失败: %s", exc, exc_info=True)
            return None
        finally:
            self._close_doc(swapp, model)

    def _build_plate(self, params: dict, step_path: Path) -> Path | None:
        """平板建模（Task 18 实现）。

        矩形平板 Box，n_hole 个均匀分布穿透孔（FeatureCut3 Through All）。
        """
        w_mm = float(params.get("width") or 0)
        d_mm = float(params.get("depth") or 0)
        t_mm = float(params.get("thickness") or 0)
        if w_mm <= 0 or d_mm <= 0 or t_mm <= 0:
            return None

        n_hole = int(params.get("n_hole") or 4)
        hole_d_mm = min(w_mm, d_mm) * 0.08
        margin_mm = hole_d_mm * 2

        w = w_mm / 1000
        d = d_mm / 1000
        t = t_mm / 1000
        hole_d = hole_d_mm / 1000
        margin = margin_mm / 1000

        swapp = self._get_swapp()
        model = None
        try:
            import math
            model = self._new_part_doc(swapp)
            if model is None:
                return None
            ftMgr = model.FeatureManager
            skMgr = model.SketchManager

            # 平板 Box：前视基准面 = XY 平面，厚度沿 +Z 挤出。
            # 这与 CadQuery 生成件和 assembly.py 的约定一致：
            # local origin 位于 XY 中心，底面 Z=0。
            model.Extension.SelectByID2(
                "前视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCenterRectangle(0, 0, 0, w / 2, d / 2, 0)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                True, False, False, 0, 0, t, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                True, True, True, 0, 0.0, False)

            # 均匀分布孔 Cut（FeatureCut3 Through All）
            if n_hole > 0 and hole_d > 0:
                if n_hole == 4:
                    cx, cz = w / 2 - margin, d / 2 - margin
                    positions = [(cx, cz), (-cx, cz), (cx, -cz), (-cx, -cz)]
                else:
                    r = min(w, d) / 2 - margin
                    positions = [
                        (r * math.cos(2 * math.pi * i / n_hole),
                         r * math.sin(2 * math.pi * i / n_hole))
                        for i in range(n_hole)
                    ]
                model.Extension.SelectByID2(
                    "前视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
                skMgr.InsertSketch(True)
                for cx, cz in positions:
                    skMgr.CreateCircleByRadius(cx, cz, 0, hole_d / 2)
                skMgr.InsertSketch(True)
                ftMgr.FeatureCut3(
                    True, False, False, 6, 0, 0.0, 0.0,
                    False, False, False, False, 0.0, 0.0,
                    False, False, False, False,
                    False, True, True,
                    False, False, False,
                    0, 0.0, False)

            if not self._export_step(model, step_path):
                return None
            return step_path
        except Exception as exc:
            log.warning("_build_plate 失败: %s", exc, exc_info=True)
            return None
        finally:
            self._close_doc(swapp, model)

    def _build_arm(self, params: dict, step_path: Path) -> Path | None:
        """臂型件建模（Task 18 实现）。

        矩形臂体（长 l 沿 X，宽 w 沿 Z，高 t 沿 Y），两端穿透孔 Cut。
        """
        l_mm = float(params.get("length") or 0)
        w_mm = float(params.get("width") or 0)
        t_mm = float(params.get("thickness") or 0)
        if l_mm <= 0 or w_mm <= 0 or t_mm <= 0:
            return None

        end_hole_d_mm = float(params.get("end_hole_d") or 0) or w_mm * 0.3
        l = l_mm / 1000
        w = w_mm / 1000
        t = t_mm / 1000
        end_hole_d = end_hole_d_mm / 1000

        swapp = self._get_swapp()
        model = None
        try:
            model = self._new_part_doc(swapp)
            if model is None:
                return None
            ftMgr = model.FeatureManager
            skMgr = model.SketchManager

            # 矩形臂体（长 l 沿 X，宽 w 沿 Z，高 t 沿 Y）
            model.Extension.SelectByID2(
                "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCenterRectangle(0, 0, 0, l / 2, w / 2, 0)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                True, False, False, 0, 0, t, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                True, True, True, 0, 0.0, False)

            # 两端孔 Cut（Through All，孔轴沿 Y 方向）
            offset = l / 2 - end_hole_d
            if end_hole_d > 0 and offset > 0:
                model.Extension.SelectByID2(
                    "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
                skMgr.InsertSketch(True)
                skMgr.CreateCircleByRadius(offset,  0, 0, end_hole_d / 2)
                skMgr.CreateCircleByRadius(-offset, 0, 0, end_hole_d / 2)
                skMgr.InsertSketch(True)
                ftMgr.FeatureCut3(
                    True, False, False, 6, 0, 0.0, 0.0,
                    False, False, False, False, 0.0, 0.0,
                    False, False, False, False,
                    False, True, True,
                    False, False, False,
                    0, 0.0, False)

            if not self._export_step(model, step_path):
                return None
            return step_path
        except Exception as exc:
            log.warning("_build_arm 失败: %s", exc, exc_info=True)
            return None
        finally:
            self._close_doc(swapp, model)

    def _build_cover(self, params: dict, step_path: Path) -> Path | None:
        """盖板建模（Task 18 实现）。

        圆盘（可含内孔）extrude，n_hole 个均匀紧固孔 Cut（Through All）。
        """
        od_mm = float(params.get("od") or 0)
        t_mm = float(params.get("thickness") or 0)
        if od_mm <= 0 or t_mm <= 0:
            return None

        id_mm = float(params.get("id") or 0)
        n_hole = int(params.get("n_hole") or 4)
        bolt_pcd_mm = od_mm * 0.75
        bolt_d_mm = max(od_mm * 0.07, 4.0)

        od = od_mm / 1000
        t = t_mm / 1000
        id_ = id_mm / 1000 if id_mm > 0 else 0
        bolt_pcd = bolt_pcd_mm / 1000
        bolt_d = bolt_d_mm / 1000

        swapp = self._get_swapp()
        model = None
        try:
            import math
            model = self._new_part_doc(swapp)
            if model is None:
                return None
            ftMgr = model.FeatureManager
            skMgr = model.SketchManager

            # 圆盘（可含内孔）Extrude
            model.Extension.SelectByID2(
                "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
            skMgr.InsertSketch(True)
            skMgr.CreateCircleByRadius(0, 0, 0, od / 2)
            if id_ > 0:
                skMgr.CreateCircleByRadius(0, 0, 0, id_ / 2)
            skMgr.InsertSketch(True)
            ftMgr.FeatureExtrusion3(
                True, False, False, 0, 0, t, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                True, True, True, 0, 0.0, False)

            # 紧固孔环 Cut（Through All）
            if n_hole > 0:
                model.Extension.SelectByID2(
                    "上视基准面", "PLANE", 0, 0, 0, False, 0, _VARIANT_NULL, 0)
                skMgr.InsertSketch(True)
                for i in range(n_hole):
                    angle = 2 * math.pi * i / n_hole
                    cx = bolt_pcd / 2 * math.cos(angle)
                    cz = bolt_pcd / 2 * math.sin(angle)
                    skMgr.CreateCircleByRadius(cx, cz, 0, bolt_d / 2)
                skMgr.InsertSketch(True)
                ftMgr.FeatureCut3(
                    True, False, False, 6, 0, 0.0, 0.0,
                    False, False, False, False, 0.0, 0.0,
                    False, False, False, False,
                    False, True, True,
                    False, False, False,
                    0, 0.0, False)

            if not self._export_step(model, step_path):
                return None
            return step_path
        except Exception as exc:
            log.warning("_build_cover 失败: %s", exc, exc_info=True)
            return None
        finally:
            self._close_doc(swapp, model)

    # ── SW API 工具方法 ────────────────────────────────────────────────────

    def _get_swapp(self):
        """直连 SldWorks COM Application 对象。"""
        import win32com.client
        return win32com.client.Dispatch("SldWorks.Application")

    def _new_part_doc(self, swapp) -> object:
        """新建 GB 零件文档（动态搜索 gb_part.prtdot，避免中文版返回空路径）。"""
        import glob as _glob
        import os.path as _osp
        tpl = r"C:\ProgramData\SolidWorks\SOLIDWORKS 2024\templates\gb_part.prtdot"
        if not _osp.exists(tpl):
            candidates = (
                _glob.glob(r"C:\ProgramData\SolidWorks\SOLIDWORKS *\templates\gb_part.prtdot")
                + _glob.glob(r"C:\ProgramData\SolidWorks\SOLIDWORKS *\templates\Part.prtdot")
            )
            tpl = candidates[0] if candidates else ""
        return swapp.NewDocument(tpl, 1, 0, 0)

    def _close_doc(self, swapp, model) -> None:
        """通过 GetTitle（COM 属性，不加括号）关闭新建文档。"""
        try:
            if model is not None:
                title = model.GetTitle  # BSTR property，非方法调用
                if title:
                    swapp.CloseDoc(title)
        except Exception:
            pass

    def _export_step(self, model, step_path: Path) -> bool:
        """将当前 model 导出为 STEP，返回是否成功。"""
        step_path.parent.mkdir(parents=True, exist_ok=True)
        # swSaveAsCurrentVersion = 0, swSaveAsOptions_Silent = 1
        model.SaveAs3(str(step_path), 0, 1)
        return step_path.exists()
