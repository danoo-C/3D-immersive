"""How the audio thread's work is compiled (D-138, D-139).

`kernel` is numba's `njit` with the three options every kernel needs:

- **`nogil=True`**: the kernel runs without the GIL. That is the point of
  compiling it: the numpy it replaces waited for the GIL again at every
  call, and with a busy UI thread that cost a block its deadline (D-137).
- **`cache=True`**: the compiled code is kept beside the module, as Python
  keeps `.pyc` files, and a later launch loads it in a fraction of a second
  rather than compiling for seconds (D-139).
- **no runtime** (`_nrt=False`): numba's runtime counts references to the
  arrays it makes and, when it is on, to every array a kernel is given. A
  kernel makes no array (D-106), so it needs none. Without it, a call makes
  no record for each array argument, which was 48 bytes each, freed at the
  end, and 2.8 KiB for the spatial path's block, over D-106's line. It also
  holds D-106 at compile time: a kernel that tried to make an array would
  not compile.

**The cache is cleared when any audio module changes.** numba checks a
cached kernel against its own module's file only, but a kernel's compiled
code holds the kernels it calls, which may live in other files: the
spatial kernel calls the lookup's walk. Edit only `lookup.py`, and the
spatial kernel's cache would go on playing the old walk. A caller cached
before its callee's edit was seen to return the old result. So on import
this module hashes every source file of the audio package, and when the
hash has changed it deletes numba's cached kernels beside them before any
is loaded. An installed release is replaced whole, so this matters while
the code is being worked on, which is when stale code does harm.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, TypeVar

from numba import njit

Function = TypeVar("Function", bound=Callable[..., object])

#: The audio package: every kernel is in it, and every kernel it calls.
PACKAGE = Path(__file__).resolve().parent

#: Where the hash of the package's sources is kept, beside numba's cache.
STAMP = "kernels.sha256"

#: `njit`'s options for every kernel. `_nrt` is numba's own option for its
#: runtime, which its type stubs leave out, hence a mapping.
OPTIONS: Final[dict[str, Any]] = {"cache": True, "nogil": True, "_nrt": False}


def kernel(function: Function) -> Function:
    """Compile `function` for the audio thread: without the GIL, cached,
    and without numba's runtime."""
    compiled: Function = njit(**OPTIONS)(function)
    return compiled


def fresh_cache(package: Path = PACKAGE) -> bool:
    """Delete numba's cached kernels under `package` if any of its source
    files changed since the cache was last known fresh; whether it did.
    Never raises: a directory that cannot be written is numba's to manage."""
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(path.read_bytes())
    stamp = package / "__pycache__" / STAMP
    try:
        if stamp.read_text(encoding="ascii") == digest.hexdigest():
            return False
    except OSError:
        pass
    try:
        for cached in (*package.rglob("*.nbi"), *package.rglob("*.nbc")):
            cached.unlink(missing_ok=True)
        stamp.parent.mkdir(exist_ok=True)
        # Through a temporary file and a rename, as the other caches are,
        # so a worker starting beside this one never reads half a hash.
        handle, name = tempfile.mkstemp(dir=stamp.parent, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="ascii") as written:
            written.write(digest.hexdigest())
        Path(name).replace(stamp)
    except OSError:
        pass
    return True


fresh_cache()
