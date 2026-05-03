from pathlib import Path


def build_artifact_index(subsystem: str) -> dict:
    return {
        "schema_version": 1,
        "subsystem": subsystem,
        "active_run_id": None,
        "accepted_baseline_run_id": None,
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


def accept_run_baseline(index: dict, run_id: str) -> dict:
    runs = index.setdefault("runs", {})
    run = runs.get(run_id)
    if not run:
        raise ValueError(f"Run not found in artifact index: {run_id}")

    artifacts = dict(run.get("artifacts") or {})
    if not artifacts.get("assembly_signature"):
        raise ValueError("Accepted baseline run must include assembly_signature artifact")

    previous = index.get("accepted_baseline_run_id")
    if previous and previous in runs:
        runs[previous]["accepted_baseline"] = False

    run["accepted_baseline"] = True
    index["accepted_baseline_run_id"] = run_id
    return index


def get_accepted_baseline(index: dict) -> dict:
    run_id = index.get("accepted_baseline_run_id")
    if not run_id:
        raise ValueError("No accepted baseline in artifact index")

    run = index.get("runs", {}).get(run_id)
    if not run or not run.get("accepted_baseline"):
        raise ValueError("No accepted baseline in artifact index")

    artifacts = dict(run.get("artifacts") or {})
    assembly_signature = artifacts.get("assembly_signature")
    if not assembly_signature:
        raise ValueError("Accepted baseline run must include assembly_signature artifact")

    return {
        "run_id": run_id,
        "assembly_signature": assembly_signature,
        **artifacts,
    }
