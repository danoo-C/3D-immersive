"""Entry point.

python -m immersive [--device NAME|NUMBER] [--block FRAMES]
python3 launch.py -- --device "Speakers" --block 1024   (preferred)

`--device` and `--block` are D-63's: the output device and block size, until
M8's Preferences promotes them. A value that cannot be honoured is reported
in the window and a default used, never a refusal to start (F-56) - which is
why `--block` is taken as text and judged later rather than typed here, where
argparse would print to stderr and exit.
"""

from __future__ import annotations

import argparse
import sys


def parse(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """The application's own flags, and whatever is left for Qt."""
    parser = argparse.ArgumentParser(prog="immersive")
    parser.add_argument("--version", action="store_true", help="print the version")
    parser.add_argument(
        "--device", help="output device, by name or number (default: the system's)"
    )
    parser.add_argument(
        "--block", help="frames per audio block, 256-2048 (default: 512)"
    )
    return parser.parse_known_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the application. Returns a process exit code."""
    options, rest = parse(list(sys.argv[1:] if argv is None else argv))

    if options.version:
        from immersive import __version__

        print(__version__)
        return 0

    from immersive.app import run

    return run([sys.argv[0], *rest], device=options.device, block=options.block)


def cli() -> None:
    """Console-script wrapper for the `immersive` entry point."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
