"""
engineering_enhancer.py — 零 AI 工程可视化后端。

用途：Blender PBR 渲染的 PNG → 轻量后处理 → JPG。几何绝对锁定，
      成本为零，适合内部工程评审 / 无法访问 AI 云服务时兜底。

函数签名与 comfyui_enhancer / fal_enhancer 一致，便于 cad_pipeline.cmd_enhance
以表驱动方式调用：

    raw_path = engineering_enhancer.enhance_image(
        png_path, prompt, engineering_cfg, view_key, rc,
    )

参数释义：
    png_path:      Blender 产出的 V*.png 绝对路径
    prompt:        统一 enhance prompt（本后端仅用于日志）
    engineering_cfg: pipeline_config.json["enhance"]["engineering"]
                   可选字段：sharpness / contrast / saturation / quality
    view_key:      "V1" / "V2" ...（日志用）
    rc:            render_config.json 全量 dict（本后端不使用）

返回：
    str: 写入的 JPG 绝对路径（临时位置，caller 负责改名）
"""

import logging
import os
import tempfile

from PIL import Image, ImageEnhance

log = logging.getLogger("engineering_enhancer")

DEFAULT_SHARPNESS = 1.3
DEFAULT_CONTRAST = 1.1
DEFAULT_SATURATION = 1.0
DEFAULT_QUALITY = 95


def enhance_image(png_path: str, prompt: str, engineering_cfg: dict,
                  view_key: str, rc: dict) -> str:
    """将 Blender PNG 转为工程风格的 JPG。

    步骤：
      1) 以 RGB 模式打开源图（若为 RGBA，合成到纯白背景上避免透明）
      2) 依次应用 ImageEnhance 的 Contrast / Sharpness / Color
      3) 保存到临时 .jpg 文件，返回路径

    参数全部从 engineering_cfg 读取，缺省值保守（轻微锐化 + 微增对比度）。
    """
    if not os.path.isfile(png_path):
        raise FileNotFoundError(f"engineering enhance: source PNG missing: {png_path}")

    sharpness = float(engineering_cfg.get("sharpness", DEFAULT_SHARPNESS))
    contrast = float(engineering_cfg.get("contrast", DEFAULT_CONTRAST))
    saturation = float(engineering_cfg.get("saturation", DEFAULT_SATURATION))
    quality = int(engineering_cfg.get("quality", DEFAULT_QUALITY))

    log.info(
        "  [engineering] %s: sharpness=%.2f contrast=%.2f saturation=%.2f quality=%d",
        view_key, sharpness, contrast, saturation, quality,
    )

    img = Image.open(png_path)
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if sharpness != 1.0:
        img = ImageEnhance.Sharpness(img).enhance(sharpness)
    if saturation != 1.0:
        img = ImageEnhance.Color(img).enhance(saturation)

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    img.save(tmp.name, "JPEG", quality=quality, optimize=True)
    return tmp.name
