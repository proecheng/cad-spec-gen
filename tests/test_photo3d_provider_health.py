from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _assert_no_forbidden_fields(value: Any) -> None:
    forbidden = {"api_key", "key", "secret", "url", "base_url", "endpoint"}
    if isinstance(value, dict):
        assert forbidden.isdisjoint(value), value
        for child in value.values():
            _assert_no_forbidden_fields(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_fields(child)


def test_provider_health_reports_generic_safe_statuses_without_setup(tmp_path):
    from tools.photo3d_provider_health import provider_health_for_presets
    from tools.photo3d_provider_presets import public_provider_presets

    health = provider_health_for_presets(
        public_provider_presets(),
        tmp_path,
        env={},
        home_dir=tmp_path / "home",
        module_available=lambda _name: False,
    )
    by_id = {item["provider_preset"]: item for item in health}

    assert list(by_id) == [
        "default",
        "engineering",
        "gemini",
        "fal",
        "fal_comfy",
        "comfyui",
    ]
    assert by_id["engineering"]["status"] == "available"
    assert by_id["engineering"]["ordinary_user_status"] == "可用"
    assert by_id["gemini"]["status"] == "needs_setup"
    assert by_id["fal"]["status"] == "needs_setup"
    assert by_id["fal_comfy"]["status"] == "needs_setup"
    assert by_id["comfyui"]["status"] == "needs_setup"

    for item in health:
        assert item["mutates_pipeline_state"] is False
        assert item["executes_enhancement"] is False
        assert item["does_not_scan_directories"] is True
        assert item["checked_by"]
        assert "cloud_credentials" in item["required_capabilities"] or item[
            "provider_preset"
        ] in {"default", "engineering", "comfyui"}
        _assert_no_forbidden_fields(item)


def test_provider_health_uses_config_presence_without_leaking_values(tmp_path):
    from tools.photo3d_provider_health import provider_health_for_presets
    from tools.photo3d_provider_presets import public_provider_presets

    (tmp_path / "gemini_gen.py").write_text("# test", encoding="utf-8")
    home = tmp_path / "home"
    config_path = home / ".claude" / "gemini_image_config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "api_key": "gemini-secret-value",
                "api_base_url": "https://secret.example.invalid",
                "model": "demo-model",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "fal_comfy_workflow_template.json").write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / "templates" / "comfyui_workflow_template.json").write_text(
        "{}", encoding="utf-8"
    )
    comfy_root = tmp_path / "ComfyUI"
    comfy_root.mkdir()

    health = provider_health_for_presets(
        public_provider_presets(),
        tmp_path,
        env={
            "FAL_KEY": "fal-secret-value",
            "COMFYUI_ROOT": str(comfy_root),
        },
        home_dir=home,
        module_available=lambda name: name
        in {"fal_client", "PIL", "numpy", "requests", "cv2"},
    )
    by_id = {item["provider_preset"]: item for item in health}

    assert by_id["gemini"]["status"] == "available"
    assert by_id["fal"]["status"] == "available"
    assert by_id["fal_comfy"]["status"] == "available"
    assert by_id["comfyui"]["status"] == "available"

    dumped = json.dumps(health, ensure_ascii=False)
    assert "gemini-secret-value" not in dumped
    assert "fal-secret-value" not in dumped
    assert "FAL_KEY" not in dumped
    assert "api_base_url" not in dumped
    assert "https://secret.example.invalid" not in dumped
    _assert_no_forbidden_fields(health)


def test_provider_health_default_follows_configured_backend(tmp_path):
    from tools.photo3d_provider_health import provider_health_for_presets
    from tools.photo3d_provider_presets import public_provider_presets

    (tmp_path / "pipeline_config.json").write_text(
        json.dumps({"enhance": {"backend": "fal"}}),
        encoding="utf-8",
    )

    blocked_health = provider_health_for_presets(
        public_provider_presets(),
        tmp_path,
        env={},
        home_dir=tmp_path / "home",
        module_available=lambda _name: False,
    )
    blocked_default = next(
        item for item in blocked_health if item["provider_preset"] == "default"
    )

    assert blocked_default["status"] == "needs_setup"
    assert "project_configuration" in blocked_default["checked_by"]

    available_health = provider_health_for_presets(
        public_provider_presets(),
        tmp_path,
        env={"FAL_KEY": "secret-value"},
        home_dir=tmp_path / "home",
        module_available=lambda name: name == "fal_client",
    )
    available_default = next(
        item for item in available_health if item["provider_preset"] == "default"
    )

    assert available_default["status"] == "available"
    dumped = json.dumps(available_health, ensure_ascii=False)
    assert "secret-value" not in dumped
    assert "FAL_KEY" not in dumped
    _assert_no_forbidden_fields(available_health)
