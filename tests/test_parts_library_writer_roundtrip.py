"""Round-trip tests for atomic parts_library.yaml user STEP mappings."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.model_context import ModelProjectContext
from tools.parts_library_writer import UserStepMapping, prepend_user_step_mapping


def _mapping(**overrides) -> UserStepMapping:
    values = {
        "part_no": "P-ERR",
        "name_cn": "异常件",
        "file_rel": "user_provided/error.step",
        "source_path": "models/error.step",
        "source_hash": "sha256:error",
    }
    values.update(overrides)
    return UserStepMapping(**values)


def _load_yaml(path: Path) -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_prepend_user_step_mapping_preserves_top_level_config_and_mapping_order(
    tmp_path,
):
    yaml = pytest.importorskip("yaml")
    project_root = tmp_path / "project"
    project_root.mkdir()
    library_path = project_root / "parts_library.yaml"
    library_path.write_text(
        yaml.safe_dump(
            {
                "extends": "custom-default",
                "solidworks_toolbox": {"enabled": False},
                "mappings": [
                    {
                        "match": {"part_no": "A-001"},
                        "adapter": "bd_warehouse",
                        "spec": {"sku": "A-001"},
                    },
                    {
                        "match": {"part_no": "B-001"},
                        "adapter": "step_pool",
                        "spec": {"file": "existing/b.step"},
                    },
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    written = prepend_user_step_mapping(
        ModelProjectContext(project_root=project_root),
        UserStepMapping(
            part_no="P-001",
            name_cn="测试件",
            file_rel="user_provided/p001.step",
            source_path="models/p001.step",
            source_hash="sha256:abc",
            bbox_mm=(1.0, 2.5, 3.25),
        ),
    )

    assert written == library_path
    cfg = _load_yaml(library_path)
    assert cfg["extends"] == "custom-default"
    assert cfg["solidworks_toolbox"] == {"enabled": False}
    assert [m["match"]["part_no"] for m in cfg["mappings"]] == [
        "P-001",
        "A-001",
        "B-001",
    ]
    first = cfg["mappings"][0]
    assert first["match"] == {"part_no": "P-001"}
    assert first["adapter"] == "step_pool"
    assert first["spec"] == {"file": "user_provided/p001.step"}
    assert first["provenance"]["provided_by_user"] is True
    assert first["provenance"]["source_path"] == "models/p001.step"
    assert first["provenance"]["source_hash"] == "sha256:abc"
    assert first["provenance"]["name_cn"] == "测试件"
    assert first["provenance"]["validated"] is True
    assert first["provenance"]["validation_status"] == "resolver_verified"
    assert isinstance(first["provenance"]["bbox_mm"], list)
    assert first["provenance"]["bbox_mm"] == [1.0, 2.5, 3.25]


def test_prepend_user_step_mapping_replaces_only_previous_user_mapping(tmp_path):
    yaml = pytest.importorskip("yaml")
    project_root = tmp_path / "project"
    project_root.mkdir()
    library_path = project_root / "parts_library.yaml"
    library_path.write_text(
        yaml.safe_dump(
            {
                "extends": "default",
                "mappings": [
                    {
                        "match": {"part_no": "P-002"},
                        "adapter": "step_pool",
                        "spec": {"file": "user_provided/old.step"},
                        "provenance": {"provided_by_user": True},
                    },
                    {
                        "match": {"part_no": "P-002"},
                        "adapter": "bd_warehouse",
                        "spec": {"sku": "P-002"},
                    },
                    {
                        "match": {"part_no": "P-003"},
                        "adapter": "step_pool",
                        "spec": {"file": "user_provided/other.step"},
                        "provenance": {"provided_by_user": True},
                    },
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    prepend_user_step_mapping(
        ModelProjectContext(project_root=project_root),
        UserStepMapping(
            part_no="P-002",
            name_cn="新零件",
            file_rel="user_provided/new.step",
            source_path="models/new.step",
            source_hash="sha256:def",
        ),
    )

    cfg = _load_yaml(library_path)
    assert [
        (m["match"]["part_no"], m["adapter"], m["spec"].get("file") or m["spec"].get("sku"))
        for m in cfg["mappings"]
    ] == [
        ("P-002", "step_pool", "user_provided/new.step"),
        ("P-002", "bd_warehouse", "P-002"),
        ("P-003", "step_pool", "user_provided/other.step"),
    ]
    assert cfg["mappings"][0]["provenance"]["provided_by_user"] is True
    assert cfg["mappings"][0]["provenance"]["validated"] is True


@pytest.mark.parametrize("content", ["- not\n- a\n- dict\n", "plain scalar\n"])
def test_prepend_user_step_mapping_rejects_non_dict_top_level_without_writing(
    tmp_path,
    content,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    library_path = project_root / "parts_library.yaml"
    library_path.write_text(content, encoding="utf-8")

    with pytest.raises((RuntimeError, ValueError)):
        prepend_user_step_mapping(
            ModelProjectContext(project_root=project_root),
            _mapping(),
        )

    assert library_path.read_text(encoding="utf-8") == content


def test_prepend_user_step_mapping_rejects_non_list_mappings_without_writing(
    tmp_path,
):
    content = "extends: default\nmappings:\n  bad: value\n"
    project_root = tmp_path / "project"
    project_root.mkdir()
    library_path = project_root / "parts_library.yaml"
    library_path.write_text(content, encoding="utf-8")

    with pytest.raises((RuntimeError, ValueError)):
        prepend_user_step_mapping(
            ModelProjectContext(project_root=project_root),
            _mapping(),
        )

    assert library_path.read_text(encoding="utf-8") == content


def test_prepend_user_step_mapping_rejects_invalid_yaml_without_writing(tmp_path):
    content = "extends: default\nmappings: [\n"
    project_root = tmp_path / "project"
    project_root.mkdir()
    library_path = project_root / "parts_library.yaml"
    library_path.write_text(content, encoding="utf-8")

    with pytest.raises((RuntimeError, ValueError)):
        prepend_user_step_mapping(
            ModelProjectContext(project_root=project_root),
            _mapping(),
        )

    assert library_path.read_text(encoding="utf-8") == content


def test_prepend_user_step_mapping_writes_custom_validation_status(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()

    prepend_user_step_mapping(
        ModelProjectContext(project_root=project_root),
        _mapping(validated=False, validation_status="pending_geometry"),
    )

    cfg = _load_yaml(project_root / "parts_library.yaml")
    provenance = cfg["mappings"][0]["provenance"]
    assert provenance["validated"] is False
    assert provenance["validation_status"] == "pending_geometry"
