"""How far work on a worker has got (F-59): headless, like all of `core/`."""

from __future__ import annotations

from immersive.core.progress import Progress


def test_progress_only_rises_and_stops_at_1() -> None:
    progress = Progress()
    progress.reach(0.5)
    progress.reach(0.25)
    assert progress.done == 0.5
    progress.reach(3.0)
    assert progress.done == 1.0


def test_a_part_maps_its_own_0_to_1_onto_its_stretch() -> None:
    progress = Progress()
    part = progress.part(0.2, 0.6)
    part.at(0.5)
    assert progress.done == 0.4
    inner = part.part(0.5, 1.0)
    inner.at(0.5)
    assert abs(progress.done - 0.5) < 1e-12, "three quarters of 0.2-0.6"


def test_a_part_reads_its_progress_cancel() -> None:
    progress = Progress()
    part = progress.part(0.0, 0.5).part(0.0, 0.5)
    assert not part.cancelled
    progress.cancelled = True
    assert part.cancelled
