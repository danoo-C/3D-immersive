"""Bundled resources.

Read these through importlib.resources, never by walking up from __file__ —
path-walking breaks under PyInstaller and zipimport (D-30):

    from importlib.resources import files
    sofa = files("immersive.assets.hrtf") / "default.sofa"
"""
