"""
adapters/parts/sw_parametric_adapter.py — SW COM API 参数化建模适配器。

当 SolidWorks 可用时，用 SW API 创建参数化特征并导出 STEP；
不可用时返回 None，调用方回退到 CadQuery 路径。

SW API 尺寸单位为米（m），内部统一 /1000 换算。
"""
from __future__ import annotations

import logging
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
        # 缓存：同一文件已存在则跳过（避免重复 NewDocument）
        if step_path.exists():
            return step_path

        try:
            build_fn = getattr(self, f"_build_{tpl_type}", None)
            if build_fn is None:
                log.debug("_build_%s 尚未实现，回退 CadQuery", tpl_type)
                return None
            return build_fn(params, step_path)
        except Exception as exc:
            log.warning("SW 建模失败 [%s/%s]: %s", tpl_type, part_no, exc, exc_info=True)
            return None

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
        model = self._new_part_doc(swapp)
        if model is None:
            return None
        try:
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
        """外壳建模（Task 17 实现）。"""
        return None  # Task 17 实现

    def _build_bracket(self, params: dict, step_path: Path) -> Path | None:
        """支架建模（Task 17 实现）。"""
        return None  # Task 17 实现

    def _build_sleeve(self, params: dict, step_path: Path) -> Path | None:
        """套筒建模（Task 17 实现）。"""
        return None  # Task 17 实现

    def _build_spring_mechanism(self, params: dict, step_path: Path) -> Path | None:
        """弹簧机构建模（Task 18 实现）。"""
        return None  # Task 18 实现

    def _build_plate(self, params: dict, step_path: Path) -> Path | None:
        """平板建模（Task 18 实现）。"""
        return None  # Task 18 实现

    def _build_arm(self, params: dict, step_path: Path) -> Path | None:
        """臂型件建模（Task 18 实现）。"""
        return None  # Task 18 实现

    def _build_cover(self, params: dict, step_path: Path) -> Path | None:
        """盖板建模（Task 18 实现）。"""
        return None  # Task 18 实现

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
