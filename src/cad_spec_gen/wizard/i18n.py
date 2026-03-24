"""Bilingual string tables for the setup wizard UI."""

STRINGS = {
    "zh": {
        # Banner
        "banner_title": "cad-spec-gen 安装向导",
        # Step 1: Language
        "step_lang": "语言 / Language",
        "lang_zh": "中文",
        "lang_en": "English",
        "lang_selected": "语言: {lang_name}",
        # Step 2: Environment
        "step_env": "环境检查",
        "env_checking": "正在检查环境...",
        "env_level": "能力等级: Level {level} ({name})",
        "env_level_5": "FULL — 全流程可用",
        "env_level_4": "RENDER — CAD + 渲染",
        "env_level_3": "CAD — 3D建模 + 2D工程图",
        "env_level_2": "IMPORT — 仅Blender导入",
        "env_level_1": "MINIMAL — 仅spec提取和代码生成",
        # Step 3: Dependencies
        "step_deps": "安装可选依赖",
        "deps_prompt": "安装全部?",
        "deps_installing": "正在安装 {spec}...",
        "deps_done": "{count} 个包安装完成",
        "deps_failed": "{count} 个包安装失败: {names}",
        "deps_skip": "跳过依赖安装",
        "dep_cadquery": "3D参数化建模 (~200MB)",
        "dep_ezdxf": "2D DXF工程图",
        "dep_matplotlib": "DXF渲染为PNG",
        "dep_pillow": "组件标注",
        # Step 4: Blender
        "step_blender": "Blender 配置",
        "blender_found": "Blender {version} 已检测到",
        "blender_not_found": "未检测到 Blender。3D渲染需要 Blender 4.x。",
        "blender_download": "下载地址: https://www.blender.org/download/",
        "blender_win": "Windows: 下载 portable zip 解压到任意目录",
        "blender_mac": "macOS: 拖入 /Applications",
        "blender_linux": "Linux: 解压到 ~/blender 或通过包管理器安装",
        "blender_path_prompt": "输入 Blender 路径 (留空跳过)",
        "blender_verified": "Blender {version} 已确认",
        "blender_invalid": "无法验证 Blender: {path}",
        # Step 5: Config
        "step_config": "生成配置",
        "config_target": "目标目录: {target}",
        "config_generated": "配置已生成",
        "config_exists": "配置已存在，保留现有配置",
        # Step 6: Register
        "step_register": "注册技能文件",
        "register_target": "将复制到: {target}",
        "register_confirm": "确认安装?",
        "register_copying": "正在复制技能文件...",
        "register_done": "{count} 个文件已安装",
        "register_cancel": "已取消安装",
        # Completion
        "complete_title": "安装完成!",
        "complete_version": "cad-spec-gen v{version} 已就绪",
        "complete_commands": "可用命令:",
        "complete_verify": "验证: cad-skill-check",
        # Update
        "update_checking": "检查更新...",
        "update_available": "发现新版本: {old} → {new}",
        "update_current": "已是最新版本 v{version}",
        "update_modified": "以下用户配置已修改，新版本将保存为 .new 文件:",
        # Errors
        "python_too_old": "Python {ver} 不满足最低要求 >=3.10",
        "abort": "安装已中止",
    },
    "en": {
        # Banner
        "banner_title": "cad-spec-gen Setup Wizard",
        # Step 1: Language
        "step_lang": "Language / 语言",
        "lang_zh": "中文",
        "lang_en": "English",
        "lang_selected": "Language: {lang_name}",
        # Step 2: Environment
        "step_env": "Environment Check",
        "env_checking": "Checking environment...",
        "env_level": "Capability: Level {level} ({name})",
        "env_level_5": "FULL — complete pipeline available",
        "env_level_4": "RENDER — CAD + rendering",
        "env_level_3": "CAD — 3D modeling + 2D drawings",
        "env_level_2": "IMPORT — Blender import only",
        "env_level_1": "MINIMAL — spec extraction and codegen only",
        # Step 3: Dependencies
        "step_deps": "Install Optional Dependencies",
        "deps_prompt": "Install all?",
        "deps_installing": "Installing {spec}...",
        "deps_done": "{count} package(s) installed",
        "deps_failed": "{count} package(s) failed: {names}",
        "deps_skip": "Skipping dependency installation",
        "dep_cadquery": "3D parametric modeling (~200MB)",
        "dep_ezdxf": "2D DXF drawings",
        "dep_matplotlib": "DXF-to-PNG rendering",
        "dep_pillow": "Component annotation",
        # Step 4: Blender
        "step_blender": "Blender Setup",
        "blender_found": "Blender {version} detected",
        "blender_not_found": "Blender not detected. 3D rendering requires Blender 4.x.",
        "blender_download": "Download: https://www.blender.org/download/",
        "blender_win": "Windows: Download portable zip and extract anywhere",
        "blender_mac": "macOS: Drag to /Applications",
        "blender_linux": "Linux: Extract to ~/blender or install via package manager",
        "blender_path_prompt": "Enter Blender path (leave empty to skip)",
        "blender_verified": "Blender {version} verified",
        "blender_invalid": "Cannot verify Blender: {path}",
        # Step 5: Config
        "step_config": "Generate Configuration",
        "config_target": "Target directory: {target}",
        "config_generated": "Configuration generated",
        "config_exists": "Config exists, keeping current",
        # Step 6: Register
        "step_register": "Register Skill Files",
        "register_target": "Will copy to: {target}",
        "register_confirm": "Confirm installation?",
        "register_copying": "Copying skill files...",
        "register_done": "{count} files installed",
        "register_cancel": "Installation cancelled",
        # Completion
        "complete_title": "Installation complete!",
        "complete_version": "cad-spec-gen v{version} is ready",
        "complete_commands": "Available commands:",
        "complete_verify": "Verify: cad-skill-check",
        # Update
        "update_checking": "Checking for updates...",
        "update_available": "New version available: {old} → {new}",
        "update_current": "Already up to date v{version}",
        "update_modified": "The following user configs were modified. New versions saved as .new:",
        # Errors
        "python_too_old": "Python {ver} does not meet minimum >=3.10",
        "abort": "Installation aborted",
    },
}


def t(key, lang="zh", **kwargs):
    """Get translated string with format substitution."""
    text = STRINGS.get(lang, STRINGS["zh"]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text
