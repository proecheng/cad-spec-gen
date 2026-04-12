#!/usr/bin/env python3
"""
Environment Detector — Hybrid Rendering Pipeline

Checks installed tools and reports capability level (1–5).
Prints actionable install guidance for missing components.

Usage:
    python tools/hybrid_render/check_env.py
    python tools/hybrid_render/check_env.py --json   # machine-readable output

No dependencies — runs with any Python ≥3.8.
"""

import importlib
import json
import os
import shutil
import sys

# ═════════════════════════════════════════════════════════════════════════════
# Detection helpers
# ═════════════════════════════════════════════════════════════════════════════

def _check_module(name):
    """Try importing a Python module, return (ok, version_or_error)."""
    try:
        mod = importlib.import_module(name)
        ver = getattr(mod, "__version__", getattr(mod, "VERSION", "installed"))
        return True, str(ver)
    except ImportError as e:
        return False, str(e)


def _find_blender():
    """Search for Blender executable. Returns (path, version) or (None, reason)."""
    # 1. BLENDER_PATH env var
    env_path = os.environ.get("BLENDER_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path, "from BLENDER_PATH env var"

    # 2. pipeline_config.json (authoritative per-machine override)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_root = os.path.normpath(os.path.join(script_dir, "..", ".."))
    config_path = os.path.join(skill_root, "pipeline_config.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg_blender = cfg.get("blender_path", "")
            if cfg_blender and os.path.isfile(cfg_blender):
                return cfg_blender, "from pipeline_config.json"
        except (OSError, json.JSONDecodeError):
            pass

    # 3. Project-local portable install
    local_path = os.path.join(skill_root, "tools", "blender", "blender.exe")
    if os.path.isfile(local_path):
        return local_path, "project-local portable"

    # Also check blender (no .exe) for Linux/Mac
    local_path2 = os.path.join(skill_root, "tools", "blender", "blender")
    if os.path.isfile(local_path2):
        return local_path2, "project-local portable"

    # 4. System PATH
    system_blender = shutil.which("blender")
    if system_blender:
        return system_blender, "system PATH"

    # 5. Platform-specific common install locations
    common = [
        os.path.expandvars(r"%ProgramFiles%\Blender Foundation\Blender\blender.exe"),
        "/usr/bin/blender",
        "/Applications/Blender.app/Contents/MacOS/Blender",
    ]
    for c in common:
        if c and os.path.isfile(c):
            return c, "platform default"

    return None, "not found"


def _check_gemini():
    """Check if Gemini image generation is configured."""
    # Check for gemini_gen.py
    gen_path = os.environ.get("GEMINI_GEN_PATH", "D:/imageProduce/gemini_gen.py")
    if not os.path.isfile(gen_path):
        return False, f"gemini_gen.py not found at {gen_path}"

    # Check for config file
    config_paths = [
        os.path.expanduser("~/.claude/gemini_image_config.json"),
        os.path.expanduser("~/gemini_image_config.json"),
    ]
    for cp in config_paths:
        if os.path.isfile(cp):
            return True, f"config at {cp}"

    return False, "gemini_image_config.json not found"


# ═════════════════════════════════════════════════════════════════════════════
# Main detection
# ═════════════════════════════════════════════════════════════════════════════

def detect_environment():
    """Run all checks, return structured result dict."""
    result = {
        "python": {
            "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "ok": sys.version_info >= (3, 8),
        },
        "cadquery": {},
        "ezdxf": {},
        "matplotlib": {},
        "blender": {},
        "gemini": {},
    }

    # Python modules
    for mod_name in ("cadquery", "ezdxf", "matplotlib"):
        ok, detail = _check_module(mod_name)
        result[mod_name] = {"ok": ok, "detail": detail}

    # Blender
    blender_path, blender_detail = _find_blender()
    result["blender"] = {
        "ok": blender_path is not None,
        "path": blender_path,
        "detail": blender_detail,
    }

    # Gemini
    gemini_ok, gemini_detail = _check_gemini()
    result["gemini"] = {"ok": gemini_ok, "detail": gemini_detail}

    # Compute capability level
    cq = result["cadquery"]["ok"]
    ez = result["ezdxf"]["ok"]
    bl = result["blender"]["ok"]
    gm = result["gemini"]["ok"]
    mp = result["matplotlib"]["ok"]

    if cq and ez and bl and gm and mp:
        level = 5
    elif cq and bl:
        level = 4
    elif cq and ez:
        level = 3
    elif bl or os.path.exists("cad/output"):
        level = 2
    else:
        level = 1

    # ─── 增强源检测（不影响 level） ───
    enhancements = {}
    try:
        from adapters.solidworks.sw_detect import detect_solidworks
        sw = detect_solidworks()
        enhancements["solidworks"] = {
            "ok": sw.installed and (sw.version_year or 0) >= 2020,
            "version": sw.version,
            "path_a": (sw.version_year or 0) >= 2020,
            "path_b": (sw.version_year or 0) >= 2024 and sw.com_available,
            "pywin32": sw.pywin32_available,
            "materials": len(sw.sldmat_paths),
        }
    except ImportError:
        enhancements["solidworks"] = {"ok": False}
    result["enhancements"] = enhancements

    result["level"] = level
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Display
# ═════════════════════════════════════════════════════════════════════════════

LEVEL_NAMES = {
    5: ("FULL",    "全管线：CAD建模 + 2D图 + 3D渲染 + AI增强"),
    4: ("RENDER",  "CAD + 3D渲染，无AI增强"),
    3: ("CAD",     "CAD + 2D工程图，无3D渲染"),
    2: ("IMPORT",  "仅有STEP/GLB文件，可手动导入Blender"),
    1: ("MINIMAL", "无CAD工具，仅输出prompt文本供手动使用"),
}

INSTALL_HINTS = {
    "cadquery": "pip install cadquery          # 参数化3D建模",
    "ezdxf":    "pip install ezdxf             # 2D DXF工程图",
    "matplotlib": "pip install matplotlib      # DXF→PNG渲染",
    "blender":  (
        "下载 Blender 4.x portable 并解压到 tools/blender/\n"
        "    https://www.blender.org/download/\n"
        "    或设置环境变量: set BLENDER_PATH=C:\\path\\to\\blender.exe"
    ),
    "gemini":   (
        "配置 Gemini 图像生成:\n"
        "    python D:/imageProduce/gemini_gen.py --config\n"
        "    或设置 GEMINI_GEN_PATH 指向 gemini_gen.py 路径"
    ),
}


def print_report(result):
    """Print human-readable environment report."""
    level = result["level"]
    level_name, level_desc = LEVEL_NAMES[level]

    print("=" * 62)
    print("  混合渲染管线 — 环境检测报告")
    print("=" * 62)
    print()
    print(f"  能力等级: Level {level} ({level_name})")
    print(f"  说明: {level_desc}")
    print()

    # Status table
    checks = [
        ("Python ≥3.8",  result["python"]["ok"],    result["python"]["version"]),
        ("CadQuery",      result["cadquery"]["ok"],  result["cadquery"]["detail"]),
        ("ezdxf",         result["ezdxf"]["ok"],     result["ezdxf"]["detail"]),
        ("matplotlib",    result["matplotlib"]["ok"], result["matplotlib"]["detail"]),
        ("Blender",       result["blender"]["ok"],   result["blender"]["detail"]),
        ("Gemini AI",     result["gemini"]["ok"],    result["gemini"]["detail"]),
    ]

    print("  检测项          状态    详情")
    print("  " + "-" * 56)
    for name, ok, detail in checks:
        icon = "[OK]" if ok else "[  ]"
        print(f"  {name:<16s} {icon}    {detail}")

    # Missing items → install hints
    missing = []
    for key in ("cadquery", "ezdxf", "matplotlib", "blender", "gemini"):
        if not result[key]["ok"]:
            missing.append(key)

    if missing:
        print()
        print("  缺失组件安装指引:")
        print("  " + "-" * 56)
        for key in missing:
            print(f"    {INSTALL_HINTS[key]}")

    # Capability matrix
    print()
    print("  各等级可用功能:")
    print("  " + "-" * 56)
    print("  Level 5 FULL:    STEP + DXF + PNG三视图 + Blender渲染 + Gemini增强")
    print("  Level 4 RENDER:  STEP + DXF + PNG三视图 + Blender渲染")
    print("  Level 3 CAD:     STEP + DXF + PNG三视图")
    print("  Level 2 IMPORT:  手动导入已有GLB到Blender渲染")
    print("  Level 1 MINIMAL: 仅生成prompt文本，手动粘贴到Gemini/ChatGPT")

    # 增强源
    enhancements = result.get("enhancements", {})
    sw_enh = enhancements.get("solidworks", {})
    print()
    print("  增强源（可选，不影响能力等级）")
    print("  " + "-" * 56)
    if sw_enh.get("ok"):
        sw_ver = sw_enh.get("version", "?")
        path_a = "材质 ✓" if sw_enh.get("path_a") else "材质 ✗"
        if sw_enh.get("path_b"):
            path_b = "Toolbox ✓"
        elif sw_enh.get("pywin32"):
            path_b = "Toolbox ✗ (版本 < 2024)"
        else:
            path_b = "Toolbox ✗ (pywin32 未安装)"
        print(f"  SolidWorks    [OK]    {sw_ver} — {path_a} / {path_b}")
    else:
        print("  SolidWorks    [  ]    未检测到安装")
        print("                        已有 SolidWorks 许可？安装后可自动集成材质库和标准件。")
    print("  " + "-" * 56)

    # Next steps
    print()
    if level == 5:
        print("  [下一步] 环境完整！运行渲染:")
        print("    python tools/hybrid_render/validate_config.py "
              "cad/end_effector/render_config.json")
    elif level >= 3:
        print(f"  [下一步] 安装缺失组件可升级到 Level {min(level+1, 5)}:")
        print(f"    {INSTALL_HINTS[missing[0]]}")
    else:
        print("  [下一步] 安装 CadQuery 开始参数化建模:")
        print(f"    {INSTALL_HINTS['cadquery']}")

    print()
    print("=" * 62)


def main():
    result = detect_environment()

    if "--json" in sys.argv:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)

    return result["level"]


if __name__ == "__main__":
    sys.exit(0 if main() >= 3 else 1)
