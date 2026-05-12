"""单测 cad_pipeline._derive_subsystem_status —— 子系统状态标签推导（D1 顺手修：has_spec 接上线）。"""
from cad_pipeline import _derive_subsystem_status


def test_empty_when_no_spec_no_build():
    assert _derive_subsystem_status(has_spec=False, has_build=False, has_steps=False, has_pngs=False) == "empty"


def test_spec_only_when_spec_present_but_no_build():
    assert _derive_subsystem_status(has_spec=True, has_build=False, has_steps=False, has_pngs=False) == "spec-only"


def test_buildable_when_has_build():
    assert _derive_subsystem_status(has_spec=False, has_build=True, has_steps=False, has_pngs=False) == "buildable"
    # has_build 命中时不看 has_spec
    assert _derive_subsystem_status(has_spec=True, has_build=True, has_steps=False, has_pngs=False) == "buildable"


def test_built_when_has_steps():
    assert _derive_subsystem_status(has_spec=False, has_build=False, has_steps=True, has_pngs=False) == "built"


def test_rendered_when_has_pngs():
    assert _derive_subsystem_status(has_spec=False, has_build=False, has_steps=False, has_pngs=True) == "rendered"


def test_pngs_take_top_priority():
    assert _derive_subsystem_status(has_spec=True, has_build=True, has_steps=True, has_pngs=True) == "rendered"
