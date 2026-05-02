from pathlib import Path


def build_artifact_index(subsystem: str) -> dict:
    return {
        "schema_version": 1,
        "subsystem": subsystem,
        "active_run_id": None,
        "runs": {},
    }


def register_run_artifacts(
    index: dict,
    run_id: str,
    artifacts: dict[str, str | Path],
    active: bool = True,
) -> dict:
    if active:
        for run in index.setdefault("runs", {}).values():
            run["active"] = False
        index["active_run_id"] = run_id
    elif index.get("active_run_id") == run_id:
        index["active_run_id"] = None

    index.setdefault("runs", {})[run_id] = {
        "run_id": run_id,
        "active": active,
        "artifacts": {key: str(path) for key, path in artifacts.items()},
    }
    return index


def get_active_artifacts(index: dict) -> dict:
    active_run_id = index.get("active_run_id")
    if not active_run_id:
        raise ValueError("No active run in artifact index")

    run = index.get("runs", {}).get(active_run_id)
    if not run or not run.get("active"):
        raise ValueError("No active run in artifact index")
    return dict(run.get("artifacts", {}))
