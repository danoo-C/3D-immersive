"""The layering rule, enforced.

`immersive.core` must import neither Qt nor an audio device library, and must
not reach sideways into the ui or audio layers. That is requirement N-5, and
it is what keeps the model testable headless — including on WSL, where there
is no usable audio device.

See docs/02-architecture.md.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import immersive

PACKAGE_ROOT = Path(immersive.__file__).parent
CORE = PACKAGE_ROOT / "core"

FORBIDDEN_IN_CORE = ("PySide6", "sounddevice", "immersive.ui", "immersive.audio")


def imported_names(tree: ast.AST) -> Iterator[str]:
    """Every module name imported by a parsed source file."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import; banned separately by TID252
                continue
            if node.module:
                yield node.module


def offenders(directory: Path, forbidden: tuple[str, ...]) -> list[str]:
    found = []
    for path in sorted(directory.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in imported_names(tree):
            if name.startswith(forbidden):
                where = f"{directory.name}/{path.relative_to(directory)}"
                found.append(f"{where}: {name}")
    return found


def test_core_imports_no_qt_no_audio_no_ui() -> None:
    assert CORE.is_dir(), "core/ is missing"
    found = offenders(CORE, FORBIDDEN_IN_CORE)
    assert not found, "core/ must stay pure (N-5):\n" + "\n".join(found)


def test_audio_layer_does_not_import_qt() -> None:
    audio = PACKAGE_ROOT / "audio"
    assert audio.is_dir(), "audio/ is missing"
    found = offenders(audio, ("PySide6", "immersive.ui"))
    assert not found, "audio/ must not depend on Qt or the UI:\n" + "\n".join(found)


def test_the_detector_actually_detects(tmp_path: Path) -> None:
    """Guard against the checks above passing vacuously.

    While core/ is still empty the tests would pass no matter how broken this
    module was. This proves the detector sees what it claims to.
    """
    sample = tmp_path / "bad.py"
    sample.write_text(
        "import os\n"
        "import PySide6.QtWidgets\n"
        "from sounddevice import OutputStream\n"
        "from immersive.ui import theme\n"
        "from immersive.core.model import Channel\n",
        encoding="utf-8",
    )
    names = set(imported_names(ast.parse(sample.read_text(encoding="utf-8"))))
    assert names == {
        "os",
        "PySide6.QtWidgets",
        "sounddevice",
        "immersive.ui",
        "immersive.core.model",
    }

    found = offenders(tmp_path, FORBIDDEN_IN_CORE)
    assert len(found) == 3, found
    assert any(f.endswith(": PySide6.QtWidgets") for f in found)
    assert any(f.endswith(": sounddevice") for f in found)
    assert any(f.endswith(": immersive.ui") for f in found)
    # A sibling core import and a stdlib import must not be flagged.
    assert not any(f.endswith(": immersive.core.model") for f in found)
    assert not any(f.endswith(": os") for f in found)
