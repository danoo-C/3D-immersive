"""Mutation sweep, as run for M4 phase 9 (HANDOFF.md): each mutation applied,
the tests run, the files restored. Replace M and LATER with the next phase's
named mutations. Usage: python handoff_sweep.py [name-prefix ...] [tests/...]
Each run's output is kept in $TMPDIR/sweep-runs. Deleted when phase 10 closes."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = Path(tempfile.gettempdir()) / "sweep-runs"
RUNS.mkdir(exist_ok=True)
MO = "src/immersive/core/model.py"; IO = "src/immersive/core/io/project_io.py"
E = "src/immersive/audio/engine.py"; F = "src/immersive/audio/feed.py"
S = "src/immersive/audio/spatial.py"; SC = "src/immersive/audio/scheduler.py"
V = "src/immersive/ui/parameters/views.py"
M = [
 ("1 mirror on the wrong axis", MO, "            (pivot.x, pivot.y, pivot.z),\n            mirrored,\n", "            (pivot.x, pivot.y, pivot.z),\n            mirrored[::-1],\n"),
 ("2 mirror ignoring the pivot", MO, "centre - (value - centre) if flipped else value", "-value if flipped else value"),
 ("3 mono-only paired unasked", MO, "    return any(clip.media_id in stereo for clip in channel.clips)", "    return True"),
 ("4 placement not read", IO, "    if not node:\n        return Placement()\n", "    return Placement()\n"),
 ("5 new channel one point", MO, "        placement=Placement(mode=Pairing.LINKED),", "        placement=Placement(),"),
 ("6 POSITION's side ignored", E, "                    at = positions[int(command[2]), int(command[6])]", "                    at = positions[int(command[2]), 0]"),
 ("7 pivot edit as a snapshot", F, "        tuple(paired(project, channel) for channel in project.channels),", "        tuple((paired(project, channel), channel.placement.pivot.x) for channel in project.channels),"),
]
LATER = [
 ("8 pair folded as one point", E, "                if snapshot.paired[index]:", "                if False:"),
 ("9 centre flat to both ears", S, "                if own != POINT and own != ear:\n                    continue\n", ""),
 ("10 no pair gain", S, "        if self.pairs:\n            self._pair_gains()", "        if False:\n            self._pair_gains()"),
 ("11 pair gain without its shared term", S, "                    + float(np.vdot(self.pair_shared[index], cross[0]).real)\n", ""),
 ("12 the stem's spectra ignored", SC, "                tuple(sides),\n                spectra,\n", "                tuple(sides),\n                None,\n"),
 ("+ a side weighed by the other's spectrum", S, "                own, other = self.pair_left[index], self.pair_right[index]", "                own, other = self.pair_right[index], self.pair_left[index]"),
 ("13 pair gain with the switch off", S, "            if self.keep_level:\n                own, other =", "            if True:\n                own, other ="),
 ("14 a pair's meters one side", S, "            for which in (0, 1) if side == POINT else (side,):", "            for which in (0, 1):"),
 ("16 typing a linked right moves nothing", V, "                changes.append(SetAttribute(channel, \"position\", left))", "                pass"),
 ("+ right rows where there is no pair", V, "            self.show_row(right, pairs)", "            self.show_row(right, True)"),
 ("+ mirror row where there is no link", V, "        self.show_row(self._mirror_row, linked)", "        self.show_row(self._mirror_row, True)"),
 ("+ mono option hidden", V, "        self.show_row(self.mono, all(mode is not Pairing.POINT for mode in modes))", "        self.show_row(self.mono, False)"),
 ("+ placement not greyed when bypassed", V, "        ):\n            widget.setEnabled(not bypassed)", "        ):\n            widget.setEnabled(True)"),
 ("+ a mirror box on the wrong axis", V, "bool(on) if at == index else was", "bool(on) if at == 0 else was"),
 ("15 a paired stereo clip still folded", SC, "            if decoded is not None and index in spatial and not pairs[index]:", "            if decoded is not None and index in spatial:"),
]
TESTS = ["tests/test_placement_fields.py", "tests/test_stereo_placement.py", "tests/test_project_io.py", "tests/test_feed.py", "tests/test_spatial.py",
         "tests/test_level_as_mixed.py", "tests/test_model.py", "tests/test_engine.py", "tests/test_realtime.py",
         "tests/test_parameters.py", "tests/test_fields_heard.py"]
extra = [t for t in sys.argv[1:] if t.startswith("tests/")]
only = [a for a in sys.argv[1:] if not a.startswith("tests/")]
def purge():
    for d in ROOT.rglob("__pycache__"):
        if ".venv" not in d.parts: shutil.rmtree(d, ignore_errors=True)
env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1")
for entry in M + LATER:
    name = entry[0]
    edits = entry[1] if isinstance(entry[1], list) else [(entry[1], entry[2], entry[3])]
    if only and not any(name.startswith(o) for o in only): continue
    saved = {}; bad = False
    for f, old, new in edits:
        path = ROOT / f
        saved.setdefault(path, path.read_text())
        current = path.read_text()
        if current.count(old) != 1:
            print(f"!! {name}: {current.count(old)} matches in {f}"); bad = True; break
        path.write_text(current.replace(old, new))
    if bad:
        for path, text in saved.items(): path.write_text(text)
        continue
    purge()
    try:
        r = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=", "-q", "-n", "8",
                            *(extra or TESTS)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
        (RUNS / (name.split(" ")[0] + "-" + str(abs(hash(name)) % 10**6) + ".txt")).write_text(r.stdout + r.stderr)
        fails = [l.split("::", 1)[1][:70] for l in r.stdout.splitlines() if l.startswith("FAILED")]
        if r.returncode and not fails:
            print(f"!! {name}: exit {r.returncode} with no test failing - broken, not caught", flush=True); continue
        print(("caught   " if r.returncode else "SURVIVED ") + name, len(fails), fails[:3], flush=True)
    finally:
        for path, text in saved.items(): path.write_text(text)
        purge()
