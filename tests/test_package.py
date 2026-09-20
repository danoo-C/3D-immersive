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
