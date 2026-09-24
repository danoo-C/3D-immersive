"""The output: which device, what block size, and whether it will do 48 kHz.

The stream is always opened at 48 kHz (D-11, D-63). There is no output
resampler: a device that refuses the rate is reported, never quietly opened
at another one (05, *The output stream*).

**`sounddevice` is loaded when first asked, never at import.** On a Linux
machine without PortAudio it raises `OSError` the moment it is imported, and
an application that would not start for want of a sound library is worse than
one that starts and says what to install. So `load_backend` returns the module
or the reason it could not be had, and everything that plays is handed the
backend rather than importing it - which is also what lets the tests drive a
stand-in with no audio device at all.

Qt-free, like `core/`: PortAudio calls back on its own thread, and a module
that cannot touch a widget cannot touch one from there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from immersive.core.time import SAMPLE_RATE

#: 05, *Fixed parameters*: 512 frames by default, 256 to 2048 allowed.
DEFAULT_BLOCK: Final = 512
SMALLEST_BLOCK: Final = 256
LARGEST_BLOCK: Final = 2048

#: Binaural stereo out, always.
CHANNELS: Final = 2

#: What to do about a missing PortAudio, per platform. Only Linux lacks it:
#: the Windows and macOS wheels of `sounddevice` bundle their own.
INSTALL_HINT: Final = "on Linux, install PortAudio: sudo apt install libportaudio2"


def load_backend() -> Any:
    """`sounddevice`, or a string saying why it cannot be had. Never raises."""
    try:
        import sounddevice
    except (OSError, ImportError) as missing:
        return f"Audio output is unavailable ({missing}) - {INSTALL_HINT}"
    return sounddevice


@dataclass(frozen=True)
class Output:
    """What the stream will be opened with."""

    device: str | int | None
    block: int


@dataclass(frozen=True)
class Settled:
    """The output to use, whether it can be used, and what was said about it."""

    output: Output
    usable: bool
    problems: list[str]


def settle(backend: Any, device: str | None, block: str | None) -> Settled:
    """Turn what was asked for into what will be used (D-63, F-56).

    A flag that cannot be honoured becomes a default and a sentence, never a
    refusal to start: the flags exist because a wrong default device with no
    way out would make the application look broken, and refusing to start
    over a typo in one would be the same failure by another road.
    """
    problems: list[str] = []

    chosen_block = DEFAULT_BLOCK
    if block is not None:
        try:
            asked = int(block)
        except ValueError:
            problems.append(f"--block {block!r} is not a number; using {DEFAULT_BLOCK}")
        else:
            if SMALLEST_BLOCK <= asked <= LARGEST_BLOCK:
                chosen_block = asked
            else:
                problems.append(
                    f"--block {asked} is outside {SMALLEST_BLOCK}-{LARGEST_BLOCK}; "
                    f"using {DEFAULT_BLOCK}"
                )

    chosen_device: str | int | None = None
    if device is not None:
        wanted: str | int = int(device) if device.isdigit() else device
        try:
            backend.query_devices(wanted, kind="output")
        except Exception as unknown:  # the backend's own error types
            problems.append(
                f"--device {device!r}: {unknown}; using the default output device"
            )
        else:
            chosen_device = wanted

    try:
        backend.check_output_settings(
            device=chosen_device,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
        )
    except Exception as refused:  # the backend's own error types
        problems.append(
            f"The output device will not open at {SAMPLE_RATE} Hz ({refused}); "
            "samples cannot be heard"
        )
        return Settled(Output(chosen_device, chosen_block), False, problems)

    return Settled(Output(chosen_device, chosen_block), True, problems)
