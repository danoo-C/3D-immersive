"""The menu a snap setting is chosen from - the toolbar's chip for the
project, and a channel header's indicator for its override (F-16, F-18).

Off, the six divisions and a *Triplet* check, and for a channel *Follow
Project* at the top. Every choice hands back a new setting and never edits
the one it was shown, so the caller can push it as one command:

- **a division** turns snapping on at it, keeping the triplet check;
- **Off** keeps the division and the check, so turning snapping on again
  returns to them;
- **Triplet** flips the check and keeps the rest;
- **Follow Project** hands back `None`: the override cleared.

For a channel following the project, the checks show the project's setting,
since that is what the channel snaps to, and any choice but Follow Project
makes it the channel's own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu

from immersive.core.model import SnapSetting
from immersive.core.time import Division
from immersive.ui.timeline.grid import snap_text

OFF = "Off"
TRIPLET = "Triplet"
FOLLOW = "Follow Project"


def fill_snap_menu(
    menu: QMenu,
    shown: SnapSetting,
    choose: Callable[[SnapSetting | None], None],
    *,
    following: bool | None = None,
) -> QMenu:
    """Fill `menu` - emptied first - with the choices for `shown`.

    `following` is `None` for the project's own setting, and for a channel
    whether it follows the project, in which case `shown` is the project's.
    """
    menu.clear()
    group = QActionGroup(menu)

    def choice(text: str, checked: bool, setting: SnapSetting | None) -> QAction:
        action = QAction(text, menu)
        action.setCheckable(True)
        action.setChecked(checked)
        action.triggered.connect(lambda _checked=False: choose(setting))
        menu.addAction(action)
        return action

    own = following is not True
    if following is not None:
        group.addAction(choice(f"{FOLLOW}  ({snap_text(shown)})", following, None))
        menu.addSeparator()
    group.addAction(
        choice(OFF, own and not shown.enabled, replace(shown, enabled=False))
    )
    for division in Division:
        group.addAction(
            choice(
                division.value,
                own and shown.enabled and shown.division is division,
                replace(shown, enabled=True, division=division),
            )
        )
    menu.addSeparator()
    choice(TRIPLET, shown.triplet, replace(shown, triplet=not shown.triplet))
    return menu
