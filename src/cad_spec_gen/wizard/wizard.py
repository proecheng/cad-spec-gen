"""6-step interactive setup wizard for cad-spec-gen."""

import sys
from pathlib import Path

from .. import __version__
from . import ui
from .i18n import t
from . import env_detect
from . import dep_installer
from . import blender_setup
from . import config_gen
from . import skill_register

TOTAL_STEPS = 6


def run_wizard(
    lang=None,
    target=None,
    skip_deps=False,
    update=False,
    agent="claude",
    codex_dir=None,
):
    """Run the interactive setup wizard.

    Args:
        lang: "zh" or "en" — skip language prompt if set
        target: Target directory — skip target prompt if set
        skip_deps: Skip dependency installation step
        update: Update existing installation
        agent: "claude", "codex", or "both" — selects generated agent adapters
        codex_dir: Codex global skills directory
    """
    version = __version__

    # --- Banner ---
    # Always show bilingual banner before language is chosen
    ui.banner("cad-spec-gen", version)

    # === Step 1: Language ===
    if lang is None:
        ui.step_header(1, TOTAL_STEPS, "语言 / Language")
        choice = ui.prompt_choice(
            "Select / 选择",
            [("中文", ""), ("English", "")],
            default=1,
        )
        lang = "zh" if choice == 1 else "en"
    else:
        ui.step_header(1, TOTAL_STEPS, "语言 / Language")
    lang_display = t(f"lang_{lang}", lang)
    ui.success(t("lang_selected", lang, lang_name=lang_display))

    # Check Python version
    py_ver, py_ok = env_detect.check_python()
    if not py_ok:
        ui.error(t("python_too_old", lang, ver=py_ver))
        ui.error(t("abort", lang))
        return 1

    # === Step 2: Environment Check ===
    ui.step_header(2, TOTAL_STEPS, t("step_env", lang))
    env_results = env_detect.run_full_check()

    # Display results
    ui.status_line("Python", env_results["python"]["version"],
                   ok=env_results["python"]["ok"])
    for pkg_name, (pkg_ver, pkg_ok) in env_results["packages"].items():
        hint = ""
        if not pkg_ok:
            dep_info = next(
                (d for d in dep_installer.OPTIONAL_DEPS if d["name"] == pkg_name),
                None,
            )
            if dep_info:
                hint = t(dep_info["desc_key"], lang)
            elif pkg_name == "jinja2":
                hint = "required" if lang == "en" else "必需"
        ui.status_line(
            pkg_name,
            pkg_ver or ("not installed" if lang == "en" else "未安装"),
            ok=pkg_ok,
            hint=hint,
        )

    blender_path = env_results["blender"]["path"]
    blender_ver = env_results["blender"]["version"]
    ui.status_line(
        "Blender",
        blender_ver or ("not found" if lang == "en" else "未找到"),
        ok=blender_path is not None,
        hint="" if blender_path else ("optional — 3D rendering" if lang == "en" else "可选 — 3D渲染"),
    )

    gemini_path = env_results["gemini"]["path"]
    ui.status_line(
        "Gemini",
        ("configured" if lang == "en" else "已配置") if gemini_path else
        ("not configured" if lang == "en" else "未配置"),
        ok=gemini_path is not None,
        hint="" if gemini_path else ("optional — AI enhance" if lang == "en" else "可选 — AI增强"),
    )

    level = env_results["level"]
    level_key = f"env_level_{level}"
    print()
    ui.info(t("env_level", lang, level=level, name=t(level_key, lang)))

    # === Step 3: Install Optional Dependencies ===
    ui.step_header(3, TOTAL_STEPS, t("step_deps", lang))

    if skip_deps:
        ui.info(t("deps_skip", lang))
    else:
        missing = dep_installer.get_missing_deps(env_results["packages"])
        if not missing:
            ui.success("All optional packages installed" if lang == "en" else "所有可选包已安装")
        else:
            items = [(d["name"], t(d["desc_key"], lang)) for d in missing]
            selected = ui.prompt_select_indices(t("deps_prompt", lang), items)

            if selected:
                to_install = [missing[i] for i in sorted(selected)]
                for dep in to_install:
                    ui.info(t("deps_installing", lang, spec=dep["spec"]))
                succeeded, failed = dep_installer.install_selected(to_install)
                if succeeded:
                    ui.success(t("deps_done", lang, count=len(succeeded)))
                if failed:
                    ui.warn(t("deps_failed", lang, count=len(failed),
                              names=", ".join(failed)))
                # Refresh env results after install
                env_results = env_detect.run_full_check()
            else:
                ui.info(t("deps_skip", lang))

    # === Step 4: Blender ===
    ui.step_header(4, TOTAL_STEPS, t("step_blender", lang))
    blender_path = blender_setup.run_blender_step(lang, env_results)

    # === Step 5: Generate Config ===
    ui.step_header(5, TOTAL_STEPS, t("step_config", lang))
    if target is None:
        target = ui.prompt(
            t("config_target", lang, target="."),
            default=".",
        )
    target = str(Path(target).resolve())
    config_gen.generate_config(target, blender_path, lang)

    # === Step 6: Register Skill Files ===
    ui.step_header(6, TOTAL_STEPS, t("step_register", lang))
    ui.info(t("register_target", lang, target=target))
    print()

    if not ui.confirm(t("register_confirm", lang)):
        ui.warn(t("register_cancel", lang))
        return 0

    ui.info(t("register_copying", lang))
    count = skill_register.register_skill(
        target,
        lang=lang,
        version=version,
        update=update,
        agent=agent,
        codex_dir=codex_dir,
    )
    print()

    # === Completion ===
    line = "=" * 55
    print(f"\n{ui.bold(line)}")
    ui.success(t("complete_title", lang))
    ui.info(t("complete_version", lang, version=version))
    print()
    ui.info(t("complete_commands", lang))
    if agent in ("claude", "both"):
        if lang == "zh":
            ui.info("  /cad-help              — 交互式帮助")
            ui.info("  /cad-spec <file.md>    — 生成 CAD Spec")
            ui.info("  /cad-codegen <子系统>   — 生成代码脚手架")
        else:
            ui.info("  /cad-help              — interactive help")
            ui.info("  /cad-spec <file.md>    — generate CAD Spec")
            ui.info("  /cad-codegen <subsys>  — generate code scaffolds")
    if agent in ("codex", "both"):
        effective_codex_dir = (
            Path(codex_dir).expanduser()
            if codex_dir is not None
            else skill_register.default_codex_skills_dir()
        )
        if lang == "zh":
            ui.info(f"  Codex skills          — {effective_codex_dir}")
            ui.info("  新开 Codex 会话后，可直接用自然语言请求 CAD spec/codegen/render")
        else:
            ui.info(f"  Codex skills          — {effective_codex_dir}")
            ui.info("  Start a new Codex session, then ask for CAD spec/codegen/render work")
    print()
    ui.info(t("complete_verify", lang))
    print(f"{ui.bold(line)}\n")

    return 0
