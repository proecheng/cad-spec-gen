import json

import pytest

from tools.contract_io import (
    file_sha256,
    hash_existing_files,
    load_json_required,
    stable_json_hash,
    write_json_atomic,
)


def test_write_json_atomic_creates_parent_and_writes_stable_utf8_json(tmp_path):
    target = tmp_path / "nested" / "data.json"

    result = write_json_atomic(target, {"name": "alpha", "items": [1, 2]})

    assert result == target
    assert target.read_text(encoding="utf-8") == (
        '{\n  "name": "alpha",\n  "items": [\n    1,\n    2\n  ]\n}\n'
    )
    assert load_json_required(target, "payload") == {"name": "alpha", "items": [1, 2]}


def test_stable_json_hash_ignores_key_order():
    left = {"b": 2, "a": {"y": 1, "x": 0}}
    right = {"a": {"x": 0, "y": 1}, "b": 2}

    assert stable_json_hash(left) == stable_json_hash(right)
    assert stable_json_hash(left).startswith("sha256:")


def test_file_sha256_hashes_content_not_path(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "dir" / "second.txt"
    second.parent.mkdir()
    first.write_text("same content", encoding="utf-8")
    second.write_text("same content", encoding="utf-8")

    assert file_sha256(first) == file_sha256(second)


def test_load_json_required_reports_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="config"):
        load_json_required(tmp_path / "missing.json", "config")


def test_load_json_required_rejects_non_object_json(tmp_path):
    target = tmp_path / "array.json"
    target.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ValueError, match="payload"):
        load_json_required(target, "payload")


def test_hash_existing_files_skips_missing_files_and_uses_input_path_keys(tmp_path):
    existing = tmp_path / "exists.txt"
    missing = tmp_path / "missing.txt"
    existing.write_text("present", encoding="utf-8")

    result = hash_existing_files([str(existing), str(missing)])

    assert result == {str(existing): file_sha256(existing)}
