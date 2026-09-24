"""The package imports, is versioned, and its metadata matches."""

from __future__ import annotations

from importlib.metadata import version

import immersive


def test_version_is_declared() -> None:
    assert immersive.__version__
    assert immersive.__version__.count(".") >= 1


def test_installed_metadata_matches_source() -> None:
    """hatchling reads the version from __init__.py — check it stayed in sync."""
    assert version("immersive") == immersive.__version__


def test_core_layers_are_importable() -> None:
    import immersive.assets
    import immersive.audio
    import immersive.core
    import immersive.ui

    for layer in (immersive.core, immersive.audio, immersive.ui, immersive.assets):
        assert layer.__doc__, f"{layer.__name__} should document its own rules"


def test_bundled_resources_are_reachable_as_resources() -> None:
    """D-30: reached through importlib.resources, so they survive a bundle.

    Both of these are non-Python files inside the package, and the failure
    they guard against is the one D-27 exists to catch: they work from a
    source tree and are missing from the wheel, so the application starts
    unstyled and iconless for everybody who installed it rather than checked
    it out. CI installs the wheel, so this test runs against what ships.
    """
    from importlib import resources

    sheet = resources.files("immersive.assets").joinpath("app.qss")
    assert sheet.is_file(), "the stylesheet is not in the package"
    assert "QWidget" in sheet.read_text(encoding="utf-8")

    play = resources.files("immersive.assets.icons").joinpath("play.svg")
    assert play.is_file(), "the icon set is not in the package"

    # M9 phase 3: the default palette is a bundled file, and D-79 says there
    # is no fallback for it. Missing from the wheel is not "unstyled", it is
    # an application that will not start.
    theme = resources.files("immersive.assets.themes").joinpath("vscode_dark.3dimtheme")
    assert theme.is_file(), "the built-in theme is not in the package"
    assert '"schema_version"' in theme.read_text(encoding="utf-8")
