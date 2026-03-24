"""Install optional Python dependencies via pip subprocess."""

import subprocess
import sys


OPTIONAL_DEPS = [
    {"name": "cadquery", "spec": "cadquery>=2.0",
     "import": "cadquery", "desc_key": "dep_cadquery"},
    {"name": "ezdxf", "spec": "ezdxf>=0.18",
     "import": "ezdxf", "desc_key": "dep_ezdxf"},
    {"name": "matplotlib", "spec": "matplotlib>=3.5",
     "import": "matplotlib", "desc_key": "dep_matplotlib"},
    {"name": "Pillow", "spec": "Pillow>=9.0",
     "import": "PIL", "desc_key": "dep_pillow"},
]


def get_missing_deps(pkg_results):
    """Return list of OPTIONAL_DEPS entries that are not installed."""
    missing = []
    for dep in OPTIONAL_DEPS:
        name = dep["name"]
        if not pkg_results.get(name, (None, False))[1]:
            missing.append(dep)
    return missing


def install_package(spec):
    """Install a single package. Returns (ok, output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", spec],
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    return result.returncode == 0, result.stdout + result.stderr


def install_selected(deps):
    """Install a list of dep dicts. Returns (succeeded, failed)."""
    succeeded = []
    failed = []
    for dep in deps:
        ok, output = install_package(dep["spec"])
        if ok:
            succeeded.append(dep["name"])
        else:
            failed.append(dep["name"])
    return succeeded, failed
