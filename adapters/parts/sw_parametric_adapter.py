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
from typing import Optional

log = logging.getLogger(__name__)

_VALID_TEMPLATES = {
    "flange", "housing", "bracket", "spring_mechanism",
    "sleeve", "plate", "arm", "cover",
}


def detect_solidworks():
    """封装 sw_detect.detect_solidworks，便于测试 patch。"""
    from adapters.solidworks.sw_detect import detect_solidworks as _det
    return _det()


class SwParametricAdapter:
    """SW COM API 参数化建模适配器（Task 15 框架 + Task 16-18 完整实现）。"""

    def is_available(self) -> tuple[bool, Optional[str]]:
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
    ) -> Optional[Path]:
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
            log.debug("SW 建模失败 [%s/%s]: %s", tpl_type, part_no, exc)
            return None

    # ── 各模板 SW 建模方法（Task 16-18 实现） ──────────────────────────────

    def _build_flange(self, params: dict, step_path: Path) -> Optional[Path]:
        """法兰建模（Task 16 实现）。"""
        return None  # Task 16 实现

    def _build_housing(self, params: dict, step_path: Path) -> Optional[Path]:
        """外壳建模（Task 17 实现）。"""
        return None  # Task 17 实现

    def _build_bracket(self, params: dict, step_path: Path) -> Optional[Path]:
        """支架建模（Task 17 实现）。"""
        return None  # Task 17 实现

    def _build_sleeve(self, params: dict, step_path: Path) -> Optional[Path]:
        """套筒建模（Task 17 实现）。"""
        return None  # Task 17 实现

    def _build_spring_mechanism(self, params: dict, step_path: Path) -> Optional[Path]:
        """弹簧机构建模（Task 18 实现）。"""
        return None  # Task 18 实现

    def _build_plate(self, params: dict, step_path: Path) -> Optional[Path]:
        """平板建模（Task 18 实现）。"""
        return None  # Task 18 实现

    def _build_arm(self, params: dict, step_path: Path) -> Optional[Path]:
        """臂型件建模（Task 18 实现）。"""
        return None  # Task 18 实现

    def _build_cover(self, params: dict, step_path: Path) -> Optional[Path]:
        """盖板建模（Task 18 实现）。"""
        return None  # Task 18 实现

    # ── SW API 工具方法 ────────────────────────────────────────────────────

    def _get_swapp(self):
        """获取 ISldWorks Application 对象（通过 sw_com_session）。"""
        from adapters.solidworks.sw_com_session import get_session
        session = get_session()
        return session.sldworks  # ISldWorks IDispatch

    def _new_part_doc(self, swapp) -> object:
        """新建空白零件文档，返回 IModelDoc2。"""
        # swDocumentTypes_Part = 1
        template = swapp.GetUserPreferenceStringValue(9)  # swUserPreferenceStringValue_DefaultPartTemplate = 9
        doc = swapp.NewDocument(template, 1, 0, 0)
        return doc

    def _close_doc(self, swapp, path: str) -> None:
        """静默关闭文档（不保存）。"""
        try:
            swapp.CloseDoc(path)
        except Exception:
            pass

    def _export_step(self, model, step_path: Path) -> bool:
        """将当前 model 导出为 STEP，返回是否成功。"""
        step_path.parent.mkdir(parents=True, exist_ok=True)
        # swSaveAsCurrentVersion = 0, swSaveAsOptions_Silent = 1
        model.SaveAs3(str(step_path), 0, 1)
        return step_path.exists()
