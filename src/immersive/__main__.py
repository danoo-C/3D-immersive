"""Entry point.

python -m immersive
python3 launch.py          (preferred — handles the venv for you)
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Run the application. Returns a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)

    if "--version" in args:
        from immersive import __version__

        print(__version__)
        return 0

    from immersive.app import run

    return run()


def cli() -> None:
    """Console-script wrapper for the `immersive` entry point."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
