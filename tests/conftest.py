"""Shared fixtures.

Note there is no sys.path manipulation here. The package is installed
editable (D-27), and adding the source tree to sys.path would defeat the
point of the src-layout.
"""

from __future__ import annotations

import os

# Qt must not try to open a display in CI or over SSH. Set before any Qt
# import so it applies to the whole session.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
