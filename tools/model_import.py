"""cad_pipeline.py model-import 子命令实现。

把用户提供的 STEP 文件稳定纳入项目模型库：
1. 以 CAD_PROJECT_ROOT 为相对路径锚点定位源文件
2. 复制到 std_parts/user_provided/
3. prepend parts_library.yaml 的 step_pool 映射
4. 用 resolver probe 验证下一次 codegen 会实际消费该 STEP
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cad_paths import PROJECT_ROOT


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root(project_root: str | Path | None = None) -> Path:
    return Path(project_root or PROJECT_ROOT).resolve()


def resolve_step_source(
    source: str,
    *,
    project_root: str | Path | None = None,
    source_search_dirs: list[str | Path] | None = None,
) -> Path:
    """Resolve a user STEP path with PROJECT_ROOT as the stable first anchor."""
    expanded = os.path.expandvars(os.path.expanduser(str(source)))
    p = Path(expanded)
    if p.is_absolute():
        return p.resolve()

    root = _project_root(project_root)
    candidates = [root / expanded]
    for base in source_search_dirs or []:
        candidates.append(Path(base).resolve() / expanded)
    candidates.append(Path.cwd() / expanded)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve()


def import_user_step_model(
    *,
    part_no: str,
    step: str,
    name_cn: str = "",
    subsystem: str | None = None,
    project_root: str | Path | None = None,
    source_search_dirs: list[str | Path] | None = None,
    verify: bool = True,
) -> dict[str, Any]:
    """Copy a user STEP into std_parts and update resolver-facing YAML."""
    root = _project_root(project_root)
    part_no = (part_no or "").strip()
    name_cn = (name_cn or "").strip()
    if not part_no:
        return {"applied": False, "reason": "missing part_no"}
    if not step:
        return {"applied": False, "reason": "missing step file path", "part_no": part_no}

    source_path = resolve_step_source(
        step,
        project_root=root,
        source_search_dirs=source_search_dirs,
    )
    if not source_path.is_file():
        return {
            "applied": False,
            "reason": f"STEP file not found: {source_path}",
            "part_no": part_no,
        }
    if source_path.suffix.lower() not in {".step", ".stp"}:
        return {
            "applied": False,
            "reason": f"not a STEP file: {source_path}",
            "part_no": part_no,
        }

    target_rel = (
        Path("user_provided")
        / _safe_model_filename(part_no, name_cn, source_path)
    ).as_posix()
    target_abs = root / "std_parts" / target_rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    if not _same_file(source_path, target_abs):
        shutil.copy2(source_path, target_abs)

    yaml_path = _prepend_step_pool_mapping(
        part_no=part_no,
        name_cn=name_cn,
        source_path=source_path,
        target_rel=target_rel,
        project_root=root,
    )

    result: dict[str, Any] = {
        "applied": True,
        "part_no": part_no,
        "name_cn": name_cn,
        "step_file": target_rel,
        "target_path": str(target_abs),
        "source_path": _portable_source_path(source_path, root),
        "source_hash": _sha256_file(source_path),
        "parts_library": str(yaml_path),
    }
    result["verification"] = (
        verify_model_import_consumed(
            part_no=part_no,
            name_cn=name_cn,
            project_root=root,
        )
        if verify
        else {"matched": None, "skipped": True}
    )
    result["record_path"] = str(
        _record_model_import(result, project_root=root, subsystem=subsystem)
    )
    return result


def verify_model_import_consumed(
    *,
    part_no: str,
    name_cn: str = "",
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Inspect resolver routing after YAML update without parsing the STEP file."""
    from adapters.parts.step_pool_adapter import StepPoolAdapter
    from parts_resolver import PartQuery, _match_rule, load_registry

    root = _project_root(project_root)
    registry = load_registry(project_root=str(root))
    query = PartQuery(
        part_no=part_no,
        name_cn=name_cn,
        material="",
        category="",
        make_buy="外购",
    )
    for index, rule in enumerate(registry.get("mappings", []) or []):
        if not isinstance(rule, dict) or not _match_rule(rule.get("match", {}), query):
            continue
        adapter = rule.get("adapter", "")
        if adapter != "step_pool":
            return {
                "matched": False,
                "status": "shadowed",
                "kind": "",
                "adapter": adapter,
                "rule_index": index,
                "step_path": None,
                "source_tag": "",
                "warnings": [f"first matching rule is {adapter}, not step_pool"],
            }
        step_adapter = StepPoolAdapter(
            project_root=str(root),
            config=registry.get("step_pool", {}),
        )
        resolution = step_adapter._resolve_spec_path(rule.get("spec", {}), query)
        if resolution.warning:
            return {
                "matched": False,
                "status": "miss",
                "kind": "miss",
                "adapter": "step_pool",
                "rule_index": index,
                "step_path": resolution.path,
                "source_tag": "",
                "warnings": [resolution.warning],
            }
        if not resolution.path or not Path(resolution.path).is_file():
            return {
                "matched": False,
                "status": "miss",
                "kind": "miss",
                "adapter": "step_pool",
                "rule_index": index,
                "step_path": resolution.path,
                "source_tag": "",
                "warnings": [f"STEP file not found: {resolution.path}"],
            }
        step_path = step_adapter._to_project_relative(resolution.path)
        return {
            "matched": True,
            "status": "hit",
            "kind": "step_import",
            "adapter": "step_pool",
            "rule_index": index,
            "step_path": step_path,
            "source_tag": f"STEP:{step_path}",
            "warnings": [],
        }

    return {
        "matched": False,
        "status": "miss",
        "kind": "miss",
        "adapter": "",
        "rule_index": None,
        "step_path": None,
        "source_tag": "",
        "warnings": ["no matching parts_library.yaml rule"],
    }


def _safe_model_filename(part_no: str, name_cn: str, source_path: Path) -> str:
    stem = f"{part_no}_{name_cn or source_path.stem}"
    stem = re.sub(r"[^\w.\-]+", "_", stem, flags=re.UNICODE).strip("_")
    stem = stem[:96] or "user_model"
    return stem + ".step"


def _same_file(source: Path, target: Path) -> bool:
    try:
        return source.exists() and target.exists() and source.samefile(target)
    except OSError:
        return False


def _portable_source_path(source_path: Path, project_root: Path) -> str:
    """Return project-relative source provenance when possible."""
    try:
        rel = source_path.resolve().relative_to(project_root.resolve())
        return rel.as_posix()
    except ValueError:
        return str(source_path)


def _prepend_step_pool_mapping(
    *,
    part_no: str,
    name_cn: str,
    source_path: Path,
    target_rel: str,
    project_root: Path,
) -> Path:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyYAML not installed; parts_library.yaml not updated") from exc

    yaml_path = project_root / "parts_library.yaml"
    if yaml_path.is_file():
        with yaml_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {"extends": "default", "mappings": []}

    if not isinstance(cfg, dict):
        cfg = {"extends": "default", "mappings": []}
    mappings = cfg.get("mappings")
    if not isinstance(mappings, list):
        mappings = []

    mappings = [
        m
        for m in mappings
        if not (
            isinstance(m, dict)
            and (m.get("match", {}) or {}).get("part_no") == part_no
            and (m.get("provenance", {}) or {}).get("provided_by_user")
        )
    ]
    new_mapping = {
        "match": {"part_no": part_no},
        "adapter": "step_pool",
        "spec": {"file": target_rel},
        "provenance": {
            "provided_by_user": True,
            "provided_at": _utc_now(),
            "source_path": _portable_source_path(source_path, project_root),
            "source_hash": _sha256_file(source_path),
            "name_cn": name_cn or "",
        },
    }
    cfg["mappings"] = [new_mapping] + mappings

    tmp_path = yaml_path.with_suffix(yaml_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_path, yaml_path)
    return yaml_path


def _record_model_import(
    result: dict[str, Any],
    *,
    project_root: Path,
    subsystem: str | None,
) -> Path:
    if subsystem:
        record_path = (
            project_root
            / "cad"
            / subsystem
            / ".cad-spec-gen"
            / "model_imports.json"
        )
    else:
        record_path = project_root / ".cad-spec-gen" / "model_imports.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if record_path.is_file():
        try:
            existing = json.loads(record_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    imports = existing.get("imports")
    if not isinstance(imports, list):
        imports = []
    imports = [
        item
        for item in imports
        if not (isinstance(item, dict) and item.get("part_no") == result["part_no"])
    ]

    record = {
        "part_no": result["part_no"],
        "name_cn": result.get("name_cn", ""),
        "step_file": result["step_file"],
        "target_path": result["target_path"],
        "source_path": result["source_path"],
        "source_hash": result["source_hash"],
        "parts_library": result["parts_library"],
        "verification": result["verification"],
        "imported_at": _utc_now(),
    }
    envelope = {
        "schema_version": 1,
        "updated_at": _utc_now(),
        "imports": [record] + imports,
    }
    tmp_path = record_path.with_suffix(record_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, record_path)
    return record_path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _print_text(payload: dict[str, Any]) -> None:
    print(f"model-import: {payload['part_no']} -> {payload['step_file']}")
    print(f"copied: {payload['target_path']}")
    print(f"parts_library: {payload['parts_library']}")
    verification = payload.get("verification") or {}
    print(
        "verification: "
        f"matched={verification.get('matched')} "
        f"adapter={verification.get('adapter')} "
        f"kind={verification.get('kind')}"
    )
    print(f"record: {payload['record_path']}")


def run_model_import(args: argparse.Namespace) -> int:
    result = import_user_step_model(
        part_no=args.part_no,
        name_cn=getattr(args, "name_cn", "") or "",
        step=args.step,
        subsystem=getattr(args, "subsystem", None),
        verify=not getattr(args, "no_verify", False),
    )
    if not result.get("applied"):
        print(f"[model-import] {result.get('reason', 'import failed')}", file=sys.stderr)
        return 2

    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_text(result)

    verification = result.get("verification") or {}
    if verification.get("matched") is False:
        return 1
    return 0
