import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: str | Path, data: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            delete=False,
        ) as temp_file:
            temp_name = temp_file.name
            temp_file.write(payload)
        os.replace(temp_name, target)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)

    return target


def load_json_required(path: str | Path, label: str) -> dict:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Required {label} JSON file not found: {target}")

    try:
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {label} JSON file: {target}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected {label} JSON file to contain an object: {target}")
    return data


def stable_json_hash(data: Any) -> str:
    payload = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def hash_existing_files(paths: list[str | Path]) -> dict[str, str]:
    result = {}
    for path in paths:
        target = Path(path)
        if target.exists():
            result[str(path)] = file_sha256(target)
    return result
