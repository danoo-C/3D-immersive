import subprocess, os, shutil, sys
from pathlib import Path
S = "src/immersive/audio/spatial.py"; E = "src/immersive/audio/engine.py"; F = "src/immersive/audio/feed.py"
M = [
 ("ITD on the near ear", S, "            far = self.left[slot] if itd > 0.0 else self.right[slot]", "            far = self.right[slot] if itd > 0.0 else self.left[slot]"),
 ("ITD blended from its magnitude", S, "        Lookup.blend(bank.itd, self.vertices, self.weights, self.itds, count)", "        Lookup.blend(np.abs(bank.itd), self.vertices, self.weights, self.itds, count)"),
 ("no ITD", S, "        if itd != 0.0:\n            # Positive", "        if False:\n            # Positive"),
 ("first vertex only", S, "            for corner in (1, 2):", "            for corner in ():"),
 ("no distance gain", S, "        gain = (self.ref_distance / max(r, self.min_distance)) ** self.rolloff", "        gain = 1.0"),
 ("distance not clamped", S, "        gain = (self.ref_distance / max(r, self.min_distance)) ** self.rolloff", "        gain = (self.ref_distance / max(r, 1e-6)) ** self.rolloff"),
 ("no crossfade", S, "        if self.fresh or not self.crossfade:", "        if True:"),
 ("stale on seek", E, "                if snapshot.space is not None:\n                    snapshot.space.fresh = True", "                if False:\n                    snapshot.space.fresh = True"),
 ("tail not carried", S, "        np.add(self.tail, self.inverse, out=self.tail)", "        np.copyto(self.tail, self.inverse)"),
 ("tail replayed after stop", E, "            if space is not None:\n                space.drain(bus_l, bus_r)", "            pass"),
 ("stereo left only", E, "                np.add(lane_l, lane_r, out=row)\n                np.multiply(row, 0.5, out=row)", "                np.copyto(row, lane_l)"),
 ("bypass spatialised", "src/immersive/audio/scheduler.py", "        if bank is not None and not channel.hrtf_bypass", "        if bank is not None"),
 ("stale position applied", E, "                if command[1] == snapshot.generation and 0 <= command[2] < len(\n                    positions\n                ):", "                if 0 <= command[2] < len(\n                    positions\n                ):"),
 ("default-norm FFT", S, "        np.fft.rfft(windowed, axis=1, norm=\"ortho\", out=self.spectra)", "        np.fft.rfft(windowed, axis=1, out=self.spectra)"),
 ("meter before distance", S, "            row = src[slot]\n            level = float(self.distance[slot])", "            row = src[slot]\n            np.abs(row, out=self.scratch)\n            peaks[channel, 0] = max(float(peaks[channel, 0]), float(self.scratch.max()))\n            peaks[channel, 1] = peaks[channel, 0]\n            continue\n            level = float(self.distance[slot])"),
 ("feed never sends positions", F, "            if before != where and not engine.send_position(generation, index, *where):", "            if False and not engine.send_position(generation, index, *where):"),
 ("resolution from the constant", "src/immersive/audio/hrtf/lookup.py", "        for face in self._cells[_cell(x, y, z, self.resolution)]:", "        for face in self._cells[_cell(x, y, z, CELLS)]:"),
 ("resolution not checked", "src/immersive/audio/hrtf/lookup.py", "        if len(offsets) != 6 * resolution * resolution + 1:", "        if False:"),
 ("feed ignores bypass", F, "        tuple(channel.hrtf_bypass for channel in project.channels),\n", ""),
]
def purge():
    for d in Path(".").rglob("__pycache__"):
        if ".venv" not in d.parts: shutil.rmtree(d, ignore_errors=True)
env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1")
only = sys.argv[1:]
for name, f, old, new in M:
    if only and name not in only: continue
    path = Path(f); text = path.read_text()
    if text.count(old) != 1:
        print(f"!! {name}: {text.count(old)} matches"); continue
    path.write_text(text.replace(old, new)); purge()
    try:
        r = subprocess.run([".venv/bin/python", "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=", "-q", "-n", "8", "--dist", "worksteal", "tests/test_spatial.py", "tests/test_realtime.py", "tests/test_feed.py", "tests/test_engine.py", "tests/test_lookup.py", "tests/test_bank.py"], env=env, capture_output=True, text=True, timeout=600)
        fails = [l for l in r.stdout.splitlines() if l.startswith("FAILED")]
        print(("caught " if r.returncode else "SURVIVED ") + name, [f.split("::")[1][:60] for f in fails][:3])
    finally:
        path.write_text(text); purge()
