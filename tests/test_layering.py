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


def test_the_notice_model_imports_no_qt() -> None:
    """D-81: `theme_io` reports a `Severity` on every problem it finds.

    So the module that defines one is upstream of the whole `.3dimtheme`
    format, and through `theme_io` it reaches `theme.py` — which keeps itself
    importable without a `QApplication` so the palette and the stylesheet
    stay testable headless. A Qt import here would cost that quietly: the
    tests would still pass, on a machine that happens to have a display.

    The widget that draws notices is `ui/widgets/notices.py` and may import
    whatever it likes. This is the model.
    """
    model = PACKAGE_ROOT / "ui" / "notices.py"
    assert model.is_file(), "ui/notices.py is missing"

    tree = ast.parse(model.read_text(encoding="utf-8"), filename=str(model))
    qt = [name for name in imported_names(tree) if name.startswith("PySide6")]

    assert not qt, f"ui/notices.py must stay Qt-free (D-81): {qt}"


def test_the_theme_modules_import_no_qt() -> None:
    """The property D-81 is protecting, asserted where it actually matters.

    `theme.py` says it in its first docstring and nothing checked it, which
    is how M9 phase 3 found D-30 asserted for one module and not its
    neighbour. Named as a set so the next theme module is one line.
    """
    found = []
    for name in ("theme.py", "theme_io.py", "notices.py"):
        path = PACKAGE_ROOT / "ui" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found += [
            f"ui/{name}: {imported}"
            for imported in imported_names(tree)
            if imported.startswith("PySide6")
        ]

    assert not found, "the theme system must stay headless:\n" + "\n".join(found)


#: `ui/` modules that are arithmetic and must stay testable with no window.
HEADLESS_UI = ("time_axis.py",)


def test_the_timeline_arithmetic_imports_no_qt() -> None:
    """D-94: the time axis is Qt-free, so its scroll and zoom are tested in
    milliseconds and in the fast lane. Named as a set, as the theme modules
    are, so the next such module is one line."""
    found = []
    for name in HEADLESS_UI:
        path = PACKAGE_ROOT / "ui" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found += [
            f"ui/{name}: {imported}"
            for imported in imported_names(tree)
            if imported.startswith("PySide6")
        ]

    assert not found, "the timeline's arithmetic must stay headless:\n" + "\n".join(
        found
    )
