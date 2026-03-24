"""Terminal UI helpers: colored output, prompts, progress indicators.

Uses only stdlib — no rich/click dependency.
"""

import os
import sys

# Enable ANSI on Windows 10+
if sys.platform == "win32":
    os.system("")

SUPPORTS_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if SUPPORTS_COLOR else str(text)


def green(text):  return _c("32", text)
def yellow(text): return _c("33", text)
def red(text):    return _c("31", text)
def cyan(text):   return _c("36", text)
def bold(text):   return _c("1", text)
def dim(text):    return _c("2", text)


def banner(title, version):
    """Print startup banner."""
    line = "=" * 55
    print(f"\n{bold(line)}")
    print(f"  {bold(title)} v{version}")
    print(f"{bold(line)}\n")


def step_header(step, total, title):
    """Print [Step N/M] Title."""
    print(f"\n{bold(f'[Step {step}/{total}]')} {bold(title)}")


def status_line(name, value, ok=True, hint=""):
    """Print status: 'Name:  value  ✅/⚠️'."""
    icon = green("OK") if ok else yellow("!!")
    line = f"  {name + ':':16s} {value:16s} {icon}"
    if hint:
        line += f"  {dim(hint)}"
    print(line)


def success(msg):
    print(f"  {green('OK')} {msg}")


def warn(msg):
    print(f"  {yellow('!!')} {msg}")


def error(msg):
    print(f"  {red('ERR')} {msg}")


def info(msg):
    print(f"  {dim(msg)}")


def prompt(message, default=None):
    """Interactive text prompt with optional default."""
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {message}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val if val else default


def prompt_choice(message, choices, default=1):
    """Numbered choice prompt. Returns 1-based index."""
    for i, (label, desc) in enumerate(choices, 1):
        marker = bold("*") if i == default else " "
        print(f"  {marker} [{i}] {label}  {dim(desc) if desc else ''}")
    try:
        val = input(f"  {message} [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    try:
        idx = int(val)
        if 1 <= idx <= len(choices):
            return idx
    except ValueError:
        pass
    return default


def confirm(message, default=True):
    """Yes/no prompt."""
    hint = "Y/n" if default else "y/N"
    try:
        val = input(f"  {message} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if val in ("y", "yes"):
        return True
    if val in ("n", "no"):
        return False
    return default


def prompt_select_indices(message, items, default_all=True):
    """Let user select from numbered list. Returns set of 0-based indices.

    User can type: Y (all), n (none), or comma-separated numbers like 1,3.
    """
    for i, (name, desc) in enumerate(items, 1):
        print(f"  [{i}] {name:20s} {dim(desc)}")
    hint = "Y/n/1,3" if default_all else "y/N/1,3"
    try:
        val = input(f"  {message} [{hint}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return set(range(len(items))) if default_all else set()
    if not val:
        return set(range(len(items))) if default_all else set()
    if val.lower() in ("y", "yes"):
        return set(range(len(items)))
    if val.lower() in ("n", "no"):
        return set()
    # Parse comma-separated 1-based indices
    selected = set()
    for part in val.split(","):
        try:
            idx = int(part.strip()) - 1
            if 0 <= idx < len(items):
                selected.add(idx)
        except ValueError:
            pass
    return selected
