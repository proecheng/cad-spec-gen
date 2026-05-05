from __future__ import annotations


def test_provider_presets_expose_stable_ordinary_user_copy():
    from tools.photo3d_provider_presets import public_provider_presets

    presets = public_provider_presets()
    by_id = {preset["id"]: preset for preset in presets}

    assert list(by_id) == [
        "default",
        "engineering",
        "gemini",
        "fal",
        "fal_comfy",
        "comfyui",
    ]
    for preset in presets:
        assert preset["ordinary_user_title"]
        assert preset["ordinary_user_summary"]
        assert preset["recommended_when"]
        assert isinstance(preset["requires_setup"], bool)

    assert "默认" in by_id["default"]["ordinary_user_title"]
    assert "项目" in by_id["default"]["ordinary_user_summary"]
    assert by_id["engineering"]["requires_setup"] is False
    assert "离线" in by_id["engineering"]["ordinary_user_summary"]
    assert "工程" in by_id["engineering"]["recommended_when"]
    assert by_id["gemini"]["requires_setup"] is True
    assert by_id["fal"]["requires_setup"] is True
    assert by_id["fal_comfy"]["requires_setup"] is True
    assert by_id["comfyui"]["requires_setup"] is True


def test_provider_presets_do_not_expose_secret_or_endpoint_fields():
    from tools.photo3d_provider_presets import public_provider_presets

    forbidden = {"api_key", "key", "secret", "url", "base_url", "endpoint"}
    for preset in public_provider_presets():
        assert forbidden.isdisjoint(preset), preset["id"]
