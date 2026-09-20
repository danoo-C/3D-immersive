#!/usr/bin/env python3
"""Launch the app inside the project virtual environment.

Run this with *any* Python on the machine:

    python3 launch.py                    # start the app
    python3 launch.py --check            # diagnose the environment, launch nothing
    python3 launch.py --install          # create the venv and install everything
    python3 launch.py --install --run    # install, then start the app
    python3 launch.py --install --dev    # also install the dev tooling
    python3 launch.py -- --verbose       # everything after -- goes to the app

It re-executes itself with the interpreter in ``.venv`` so you never have to
remember to activate anything. Stdlib only, so it runs before the environment
exists and can tell you what is wrong with it.

See docs/08-environment.md.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
SRC = ROOT / "src"
PACKAGE = "immersive"
MIN_PYTHON = (3, 11)

# Pre-M0 fallback only. Once pyproject.toml exists, the dependency check reads
# the installed distribution's own metadata instead of this list, so there is
# exactly one source of truth and it cannot drift. See compute_missing().
REQUIRED = [
    ("PySide6", "PySide6"),
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("sounddevice", "sounddevice"),
    ("soundfile", "soundfile"),
    ("soxr", "soxr"),
    ("sofar", "sofar"),
]

# Installed only with --dev. Never checked at launch; the app runs without them.
DEV_REQUIRED = ["pytest", "pytest-qt", "ruff", "mypy"]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def die(message: str, *hints: str) -> NoReturn:
    print(f"\nlaunch: {message}\n", file=sys.stderr)
    for hint in hints:
        print(f"  {hint}", file=sys.stderr)
    if hints:
        print(file=sys.stderr)
    raise SystemExit(1)


def venv_python() -> Path:
    """Path to the interpreter inside .venv, per platform layout."""
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def in_target_venv() -> bool:
    """True when we are already running as the venv interpreter."""
    try:
        return Path(sys.prefix).resolve() == VENV.resolve()
    except OSError:
        return False


def child_env() -> dict[str, str]:
    """Environment for the app: src/ importable without an editable install."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    parts = [str(SRC)] + ([existing] if existing else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["VIRTUAL_ENV"] = str(VENV)
    # Keep the venv's bin dir first so subprocesses resolve the right tools.
    bindir = str(venv_python().parent)
    env["PATH"] = os.pathsep.join([bindir, env.get("PATH", "")])
    return env


def _requirement_name(req: str) -> tuple[str, str]:
    """Split a PEP 508 requirement into (distribution name, marker)."""
    spec, _, marker = req.partition(";")
    name = re.split(r"[\[<>=!~ (]", spec.strip(), maxsplit=1)[0]
    return name.strip(), marker.strip()


def compute_missing() -> list[str]:
    """Distribution names that are declared but not installed.

    When the project itself is installed we read its declared dependencies
    from package metadata, so this never has to be kept in sync with
    pyproject.toml by hand. REQUIRED is only the bootstrap fallback for a
    tree that has not been installed yet.
    """
    from importlib.metadata import PackageNotFoundError, distribution

    def installed(name: str) -> bool:
        try:
            distribution(name)
        except PackageNotFoundError:
            return False
        return True

    try:
        dist = distribution(PACKAGE)
    except PackageNotFoundError:
        dist = None

    if dist is not None:
        missing = []
        for req in dist.requires or []:
            name, marker = _requirement_name(req)
            if not name or "extra" in marker:
                continue  # optional extras are not needed to run the app
            if not installed(name):
                missing.append(name)
        return missing

    import importlib.util

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    return [d for n, d in REQUIRED if importlib.util.find_spec(n) is None]


def install_hint() -> list[str]:
    """How to fix a missing-dependency situation, given where the tree is."""
    if (ROOT / "pyproject.toml").exists():
        return ["Install them with:", "", "    python3 launch.py --install"]
    return [
        "Install them with:",
        "",
        f"    {venv_python()} -m pip install " + " ".join(d for _, d in REQUIRED),
    ]


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #


def check_bootstrap_python() -> None:
    if sys.version_info < MIN_PYTHON:
        die(
            f"this launcher needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+, "
            f"found {sys.version.split()[0]}",
        )


def check_venv_exists() -> None:
    if not venv_python().exists():
        die(
            f"no virtual environment at {VENV}",
            "Create one with:",
            "",
            f"    {sys.executable} -m venv .venv",
            "",
            "then install the dependencies (see docs/08-environment.md).",
        )


def report(verbose: bool = True) -> int:
    """Print an environment diagnosis. Returns a process exit code."""
    ok = True
    print()
    print("  3d immersive — environment check")
    print("  " + "-" * 44)
    print(f"  project root     {ROOT}")
    print(f"  launcher python  {sys.version.split()[0]}  ({sys.executable})")

    vpy = venv_python()
    if vpy.exists():
        try:
            ver = (
                subprocess.run(
                    [str(vpy), "--version"], capture_output=True, text=True, timeout=30
                ).stdout.strip()
                or "?"
            )
        except (OSError, subprocess.SubprocessError) as exc:
            ver = f"failed to run: {exc}"
            ok = False
        print(f"  venv python      {ver}  ({vpy})")
    else:
        print(f"  venv python      MISSING  (expected {vpy})")
        ok = False

    print(f"  source tree      {SRC}{'' if SRC.is_dir() else '   MISSING'}")
    if not SRC.is_dir():
        ok = False

    if vpy.exists():
        missing = _missing_in_venv(vpy)
        if missing is None:
            print("  dependencies     could not be checked")
            ok = False
        elif missing:
            print(f"  dependencies     {len(missing)} missing: {', '.join(missing)}")
            ok = False
        else:
            print("  dependencies     all present")

        if not _package_importable(vpy):
            print(f"  app package      '{PACKAGE}' not importable")
            ok = False
        else:
            print(f"  app package      '{PACKAGE}' ok")

    print("  " + "-" * 44)
    print("  READY" if ok else "  NOT READY — see docs/08-environment.md")
    print()
    return 0 if ok else 1


def _missing_in_venv(vpy: Path) -> list[str] | None:
    """Ask the venv interpreter which requirements it is missing.

    Re-runs this file with --print-missing rather than reimplementing the
    check as an inline snippet, so both sides use identical logic.
    """
    try:
        out = subprocess.run(
            [str(vpy), str(Path(__file__).resolve()), "--print-missing"],
            env=child_env(),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return [line for line in out.stdout.splitlines() if line.strip()]


def _package_importable(vpy: Path) -> bool:
    probe = (
        "import importlib.util,sys;"
        f"sys.exit(0 if importlib.util.find_spec({PACKAGE!r}) else 1)"
    )
    try:
        return (
            subprocess.run(
                [str(vpy), "-c", probe],
                env=child_env(),
                capture_output=True,
                timeout=120,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


# --------------------------------------------------------------------------- #
# install
# --------------------------------------------------------------------------- #


def run(cmd: list[str], what: str) -> None:
    """Run a command with its output streaming straight to the terminal.

    Not captured on purpose — a pip install can take minutes and silence
    reads as a hang.
    """
    print(f"\n  -> {what}")
    print(f"     {' '.join(cmd)}\n", flush=True)
    if subprocess.run(cmd).returncode != 0:
        die(
            f"{what} failed",
            "Nothing was rolled back; fix the cause and run --install again.",
        )


def create_venv() -> None:
    if venv_python().exists():
        print(f"  = virtual environment already exists at {VENV}")
        return
    run(
        [sys.executable, "-m", "venv", str(VENV)],
        f"creating virtual environment at {VENV}",
    )
    if not venv_python().exists():
        die(
            "venv creation reported success but no interpreter appeared",
            "On Debian/Ubuntu this usually means the venv module is incomplete:",
            "",
            "    sudo apt install python3-venv",
        )


def do_install(dev: bool) -> int:
    """Create the venv and install dependencies. Returns a process exit code."""
    print()
    print("  3d immersive - install")
    print("  " + "-" * 44)

    create_venv()
    vpy = str(venv_python())
    run([vpy, "-m", "pip", "install", "--upgrade", "pip"], "upgrading pip")

    if (ROOT / "pyproject.toml").exists():
        target = ".[dev]" if dev else "."
        run(
            [vpy, "-m", "pip", "install", "-e", target],
            f"installing the project, editable: pip install -e {target}",
        )
    else:
        print("\n  ! No pyproject.toml yet, so there is nothing to install editable.")
        print("    Falling back to installing dependencies by name. Once M0 adds")
        print("    pyproject.toml this switches to 'pip install -e .' on its own.")
        run(
            [vpy, "-m", "pip", "install", *(d for _, d in REQUIRED)],
            "installing runtime dependencies",
        )
        if dev:
            run([vpy, "-m", "pip", "install", *DEV_REQUIRED], "installing dev tooling")

    # Shown for information. Every pip step above already died on failure, so
    # a remaining gap here (typically: the app package is not scaffolded yet)
    # must not be treated as an install failure.
    report()
    return 0


# --------------------------------------------------------------------------- #
# entry
# --------------------------------------------------------------------------- #


def main(argv: list[str]) -> int:
    check_bootstrap_python()

    app_args = []
    if "--" in argv:
        split = argv.index("--")
        argv, app_args = argv[:split], argv[split + 1 :]

    flags = set(argv)
    if flags & {"--help", "-h"}:
        print(__doc__)
        return 0

    if "--print-missing" in flags:  # internal, used by --check
        print("\n".join(compute_missing()))
        return 0

    known = {"--check", "--install", "--run", "-run", "--dev", "--print-missing"}
    unknown = flags - known
    if unknown:
        die(
            f"unknown option(s): {', '.join(sorted(unknown))}",
            "Run 'python3 launch.py --help' for usage.",
        )

    if "--check" in flags:
        return report()

    if "--install" in flags:
        code = do_install(dev="--dev" in flags)
        if code != 0:
            return code
        if not flags & {"--run", "-run"}:
            print("  Install complete. Start the app with:")
            print()
            print("      python3 launch.py")
            print()
            return 0
    elif flags & {"--run", "-run"}:
        # --run on its own is just the default behaviour; accept it quietly.
        pass

    check_venv_exists()

    # Already the venv interpreter: run the app in-process.
    if in_target_venv():
        sys.path.insert(0, str(SRC))
        missing = compute_missing()
        if missing:
            die(f"missing dependencies: {', '.join(missing)}", *install_hint())
        try:
            from immersive.__main__ import main as app_main
        except ModuleNotFoundError as exc:
            die(
                f"cannot import the app: {exc}",
                f"Expected a package at {SRC / PACKAGE}.",
                "If the source tree is empty the app has not been scaffolded yet",
                "— see milestone M0 in docs/06-roadmap.md.",
            )
        return int(app_main(app_args) or 0)

    # Otherwise hand off to the venv interpreter.
    cmd = [str(venv_python()), str(Path(__file__).resolve())]
    if app_args:
        cmd += ["--", *app_args]
    env = child_env()

    if os.name == "nt":
        return subprocess.run(cmd, env=env).returncode
    os.execve(cmd[0], cmd, env)  # replaces this process; keeps Ctrl+C clean


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
