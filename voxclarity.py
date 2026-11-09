"""VoxClarity CLI: same engine as the window app.

Usage: python voxclarity.py <input audio or video> [-o output] [--preset warm_pro|studio|natural|podcast|radio]
       [--target youtube|podcast|none] [--device cuda:0]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # works also with python -I
import engine  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=f"VoxClarity {engine.VERSION}")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--preset", choices=list(engine.PRESETS), default="warm_pro")
    ap.add_argument("--target", choices=list(engine.TARGETS), default="none")
    ap.add_argument("--device")
    a = ap.parse_args()
    out = Path(a.output) if a.output else engine.default_output(a.input, a.preset)
    t0 = time.time()
    x = engine.read_audio(a.input)
    dev = engine.pick_device(a.device)
    print(f"[VoxClarity {engine.VERSION}] {len(x) / engine.SR:.0f} s on {dev}", flush=True)
    y, _ = engine.process(x, {}, a.preset, a.target, dev)
    engine.write_output(a.input, y, out)
    print(f"[VoxClarity {engine.VERSION}] DONE in {time.time() - t0:.1f} s -> {out}", flush=True)


if __name__ == "__main__":
    main()
