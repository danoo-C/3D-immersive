# Third-party notices

The application itself is MIT ([LICENSE](LICENSE)). It depends on, and when
bundled redistributes, the components below. This file exists because a
PyInstaller bundle (M8) ships those components inside it, at which point their
licence terms attach to the thing being handed to someone else — and an
attribution file written at release time is written under deadline, from
memory.

Keep this file current with `pyproject.toml`'s `dependencies`. It is checked by
`tests/test_docs.py`.

## Runtime dependencies

| Component | Licence | Obligation when bundled |
|---|---|---|
| [PySide6 / Qt 6](https://www.qt.io/) | LGPL-3.0 | **The one with real conditions.** See below. |
| [numpy](https://numpy.org/) | BSD-3-Clause | Reproduce the copyright notice |
| [scipy](https://scipy.org/) | BSD-3-Clause | Reproduce the copyright notice |
| [sounddevice](https://python-sounddevice.readthedocs.io/) | MIT | Reproduce the copyright notice |
| [PortAudio](http://www.portaudio.com/) (via sounddevice) | MIT-style | Reproduce the copyright notice |
| [soundfile](https://python-soundfile.readthedocs.io/) | BSD-3-Clause | Reproduce the copyright notice |
| [libsndfile](http://libsndfile.github.io/libsndfile/) (via soundfile) | LGPL-2.1 | Dynamically linked; see below |
| [soxr](https://github.com/dofuuz/python-soxr) | LGPL-2.1 | Dynamically linked; see below |
| [sofar](https://github.com/pyfar/sofar) | MIT | Reproduce the copyright notice |

### The LGPL components

PySide6 was chosen over PyQt6 precisely because it is LGPL and carries no
commercial licence question (D-2). LGPL is not, however, the same as "no
conditions". Bundling it obliges us to:

- state that Qt is used and is licensed under the LGPL-3.0 (this file),
- ship the LGPL text alongside the bundle,
- keep Qt **dynamically** linked, which PyInstaller does by default, and
- allow a user to replace the Qt libraries with their own build.

`libsndfile` and `soxr` carry the same shape of obligation under LGPL-2.1.
None of this is onerous; all of it is easy to forget, which is why it is
written down here rather than discovered at M8.

## Bundled data

| Component | Licence | Status |
|---|---|---|
| HRTF dataset (SOFA) | depends on the set chosen | **Not yet bundled.** |

The default dataset is chosen at M4 (QA-30), and the choice is constrained by
licence as much as by how it sounds. The leading candidate is **SADIE II D1**
(KEMAR), which carries *"Copyright 2018, University of York, Licensed under the
Apache License, Version 2.0"* in its own `GLOBAL_License` field — permissive
enough to bundle, which is the constraint several other candidate sets fail.
See [`docs/s0_listening_spike/phase_1_sofa_load.md`](docs/s0_listening_spike/phase_1_sofa_load.md).

Apache 2.0 requires the licence text and any `NOTICE` file to travel with the
redistributed work. When M4 settles the dataset, add its row above and its
licence text to the bundle.
