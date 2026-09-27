"""--device and --block (D-63), and what becomes of a value that cannot be
honoured: a default and a sentence, never a refusal to start (F-56)."""

from __future__ import annotations

from typing import Any

import pytest

from immersive import app
from immersive.__main__ import parse
from immersive.audio.device import DEFAULT_BLOCK, NO_DEVICE, settle


class Backend:
    """What `settle` asks of `sounddevice`, and nothing more."""

    def __init__(
        self,
        devices: tuple[str, ...] = ("Speakers", "Headphones"),
        rate_ok: bool = True,
        default: int | None = 0,
        inputs: tuple[str, ...] = (),
    ) -> None:
        self.devices = devices
        self.inputs = inputs
        self.rate_ok = rate_ok
        self.default = default
        self.checked: list[dict[str, Any]] = []

    def query_devices(
        self, device: str | int | None = None, kind: str | None = None
    ) -> Any:
        if device is None and kind is None:
            return [
                {"name": name, "max_output_channels": 2} for name in self.devices
            ] + [{"name": name, "max_output_channels": 0} for name in self.inputs]
        if device is None:
            if self.default is None:
                raise RuntimeError("Error querying device -1")
            device = self.default
        if isinstance(device, int):
            if device >= len(self.devices):
                raise ValueError(f"no device {device}")
            return {"name": self.devices[device]}
        matches = [name for name in self.devices if device.lower() in name.lower()]
        if len(matches) != 1:
            raise ValueError(f"no output device matching {device!r}")
        return {"name": matches[0]}

    def check_output_settings(self, **settings: Any) -> None:
        self.checked.append(settings)
        if not self.rate_ok:
            raise RuntimeError("Invalid sample rate")


def test_the_flags_parse_and_leave_the_rest_for_qt() -> None:
    options, rest = parse(
        ["--device", "Headphones", "--block", "1024", "-style", "fusion"]
    )

    assert (options.device, options.block) == ("Headphones", "1024")
    assert rest == ["-style", "fusion"]


def test_main_hands_the_flags_to_the_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The seam between parsing and running, which the sweep found untested:
    `parse` was tested and `app.run` was tested, and the call joining them
    could drop both flags without either noticing."""
    from immersive import __main__

    received: dict[str, Any] = {}

    def run(argv: list[str], **flags: str | None) -> int:
        received.update(flags, argv=argv)
        return 0

    # By name rather than through `app`: nothing here reaches Qt, and naming
    # the module would say it does (test_markers.py).
    monkeypatch.setattr("immersive.app.run", run)

    assert (
        __main__.main(["--device", "Headphones", "--block", "1024", "-style", "x"]) == 0
    )
    assert (received["device"], received["block"]) == ("Headphones", "1024")
    assert received["argv"][1:] == ["-style", "x"]


def test_no_flags_is_the_default_output() -> None:
    settled = settle(Backend(), None, None)

    assert settled.usable
    assert settled.output.device is None
    assert settled.output.block == DEFAULT_BLOCK
    assert settled.problems == []


def test_a_named_device_and_a_block_are_used() -> None:
    settled = settle(Backend(), "head", "1024")

    assert settled.output.device == "head"
    assert settled.output.block == 1024
    assert settled.problems == []


def test_a_device_by_number() -> None:
    assert settle(Backend(), "1", None).output.device == 1


def test_the_rate_asked_of_the_device_is_48k_and_nothing_else() -> None:
    backend = Backend()

    settle(backend, None, None)

    assert backend.checked == [
        {"device": None, "samplerate": 48_000, "channels": 2, "dtype": "float32"}
    ]


def test_an_unknown_device_is_a_notice_and_the_default() -> None:
    """D-63's whole reason: a wrong device with no way out looks broken."""
    settled = settle(Backend(), "Studio Monitors", None)

    assert settled.usable
    assert settled.output.device is None
    [problem] = settled.problems
    assert problem.startswith("--device 'Studio Monitors'")
    assert "using the default output device" in problem


@pytest.mark.parametrize("block", ["64", "4096", "fast"])
def test_a_block_that_cannot_be_honoured_is_a_notice_and_512(block: str) -> None:
    settled = settle(Backend(), None, block)

    assert settled.output.block == DEFAULT_BLOCK
    [problem] = settled.problems
    assert problem.startswith(
        f"--block {block!r}" if block == "fast" else f"--block {block}"
    )


@pytest.mark.parametrize("block", ["256", "2048"])
def test_the_ends_of_the_block_range_are_allowed(block: str) -> None:
    assert settle(Backend(), None, block).output.block == int(block)


def test_a_device_that_refuses_48k_is_said_and_not_worked_around() -> None:
    """05: no output resampler. A device that will not do 48 kHz is reported,
    never quietly opened at another rate."""
    settled = settle(Backend(rate_ok=False), None, None)

    assert not settled.usable
    assert "will not open at 48000 Hz" in settled.problems[-1]


def test_no_output_device_at_all_is_said_as_that() -> None:
    """Not as a refusal of 48 kHz: PortAudio's "Error querying device -1",
    on a WSL with nothing routing ALSA to the sound server, read as one."""
    backend = Backend(devices=(), default=None)
    settled = settle(backend, None, None)

    assert not settled.usable
    assert settled.problems == [NO_DEVICE]
    assert backend.checked == [], "nothing to ask for 48 kHz"


def test_devices_without_a_default_are_named_and_none_is_chosen() -> None:
    settled = settle(Backend(default=None, inputs=("Microphone",)), None, None)

    assert not settled.usable
    assert settled.output.device is None
    [problem] = settled.problems
    assert "no default audio output device" in problem
    assert problem.endswith("choose one with --device: Speakers, Headphones")


def test_a_machine_with_only_a_microphone_has_no_output_device() -> None:
    backend = Backend(devices=(), default=None, inputs=("Microphone",))
    assert settle(backend, None, None).problems == [NO_DEVICE]


def test_a_device_named_needs_no_default() -> None:
    settled = settle(Backend(default=None), "Headphones", None)

    assert settled.usable and settled.problems == []
    assert settled.output.device == "Headphones"


def test_a_device_named_that_is_not_there_says_so_and_then_why_nothing_plays() -> None:
    settled = settle(Backend(devices=(), default=None), "Headphones", None)

    assert not settled.usable
    assert settled.problems[0].startswith("--device 'Headphones'")
    assert settled.problems[1:] == [NO_DEVICE]


def test_a_backend_that_cannot_list_its_devices_is_no_device() -> None:
    class Silent(Backend):
        def query_devices(
            self, device: str | int | None = None, kind: str | None = None
        ) -> Any:
            raise RuntimeError("PortAudio not initialized")

    assert settle(Silent(), None, None).problems == [NO_DEVICE]


# --------------------------------------------------------------------------- #
# a real launch, through app.run
# --------------------------------------------------------------------------- #


def launched(
    monkeypatch: pytest.MonkeyPatch, backend: object, **flags: str
) -> dict[str, Any]:
    """Run `app.run` for real, look at its window once the loop is turning,
    and quit. What was seen comes back."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from immersive.ui.main_window import MainWindow

    seen: dict[str, Any] = {}

    def look() -> None:
        # Quits whatever happens: an exception here, inside the event loop,
        # would otherwise leave `run` waiting for ever.
        try:
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, MainWindow):
                    seen["notices"] = [
                        n.message for n in widget.notices().newest_first()
                    ]
                    seen["player"] = widget._player
        finally:
            instance = QApplication.instance()
            assert instance is not None
            instance.quit()

    real_build = app.build_application

    def build(argv: list[str] | None = None) -> QApplication:
        application = real_build(argv)
        QTimer.singleShot(0, look)
        return application

    monkeypatch.setattr(app, "load_backend", lambda: backend)
    monkeypatch.setattr(app, "build_application", build)
    seen["exit"] = app.run(["immersive"], **flags)
    return seen


@pytest.mark.gui
def test_a_launch_reports_every_flag_it_could_not_honour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = launched(monkeypatch, Backend(), device="Nowhere", block="64")

    assert seen["exit"] == 0
    assert seen["player"] is not None, "and can still be heard, on the default"
    assert sorted(seen["notices"]) == sorted(
        [
            "--block 64 is outside 256-2048; using 512",
            "--device 'Nowhere': no output device matching 'Nowhere'; "
            "using the default output device",
        ]
    )


@pytest.mark.gui
def test_a_launch_with_no_audio_stack_starts_and_says_what_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reason = "Audio output is unavailable (PortAudio library not found) - install it"

    seen = launched(monkeypatch, reason)

    assert seen["exit"] == 0
    assert seen["player"] is None
    assert seen["notices"] == [reason]


@pytest.mark.gui
def test_a_launch_asks_for_the_hrtf_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Here, and not in the window's constructor, which every test reaches."""
    from immersive.ui.main_window import MainWindow

    asked: list[bool] = []

    def recorded(self: MainWindow) -> bool:
        asked.append(True)
        return True

    monkeypatch.setattr(MainWindow, "prepare_hrtf", recorded)
    launched(monkeypatch, Backend())
    assert asked == [True]
