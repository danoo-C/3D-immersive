"""Block time for 32 stereo channels as points and as linked pairs, SADIE at
512 frames, level as mixed on and off (M4 phase 9; the start of phase 10's
benchmark). Usage: python handoff_blocktime.py. Deleted when phase 10 closes."""
import math, tempfile, time
from pathlib import Path
import numpy as np
from immersive.audio.engine import Engine
from immersive.audio.hrtf.bank import prepare
from immersive.audio.hrtf.sofa import builtin
from immersive.audio.scheduler import build
from immersive.core.io.media import Decoded
from immersive.core.io.loudness import measure
from immersive.core.model import Channel, Clip, Master, MediaFile, Pairing, Placement, Position, Project
BLOCK = 512
with tempfile.TemporaryDirectory() as c:
    bank = prepare(builtin("sadie-d1"), BLOCK, Path(c))
rng = np.random.default_rng(0)
audio = (0.05 * rng.standard_normal((48000 * 8, 2))).astype(np.float32); audio.flags.writeable = False
decoded = Decoded(audio, 48000, measure(audio).fold, measure(audio))
m = MediaFile("m-00000001", "/n.wav", "n.wav", 48000, 2, len(audio))
for mode in (Pairing.POINT, Pairing.LINKED):
  for keep in (False, True):
    p = Project(media_pool=[m], master=Master(), channels=[Channel(f"c-{n:08x}", f"S{n}", "#A855F7", position=Position(1.0, 1.0, 0.0), placement=Placement(mode=mode), clips=[Clip(f"k-{n:08x}", m.id, 0, 0, len(audio))]) for n in range(32)])
    p.distance.keep_level = keep
    e = Engine(BLOCK); s = build(p, {m.id: decoded}.get, None, bank); e.install(s); e.set_playing(True)
    out = np.zeros((BLOCK, 2), dtype=np.float32); times = []
    for n in range(3000):
        for ch in range(32):
            a = ch * 0.2 + n * 0.02
            r = 0.1 if ch < 4 else 1.5  # four inside the centre
            e.send_position(s.generation, ch, r * math.sin(a), r * math.cos(a), 0.2)
            if mode is Pairing.LINKED:
                e.send_position(s.generation, ch, -r * math.sin(a), r * math.cos(a), 0.2, side=1)
        t0 = time.perf_counter(); e.process(out); times.append(time.perf_counter() - t0)
    t = np.array(times[100:]) * 1000
    print(f"over 8 ms: {(t > 8).sum()} of {len(t)}; {mode.value:7} keep_level={keep!s:5}: mean {t.mean():.2f} ms, p99 {np.percentile(t, 99):.2f} ms, worst {t.max():.2f} ms (budget 10.67)")
