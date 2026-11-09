r"""Headless API smoke test.

Start the server first:  .venv\Scripts\python server.py --no-window --port 8765
It prints "PAGE http://127.0.0.1:8765/?t=<token>": the token is the access secret of that run.
Then run:                .venv\Scripts\python tests\smoke_test.py 8765 path\to\clip.wav <token>
Processes the clip into the configured output folder and checks the result exists with the same duration.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

port, clip, token = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
base = f"http://127.0.0.1:{port}"


def get(path):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + path, headers={"X-VS-Token": token})))


def post(path, body):
    req = urllib.request.Request(base + path, json.dumps(body).encode(), method="POST", headers={"X-VS-Token": token})
    return json.load(urllib.request.urlopen(req))


def wait(timeout=1800):
    t = time.time()
    while time.time() - t < timeout:
        s = get("/api/status")
        if s["state"] != "running":
            return s, time.time() - t
        time.sleep(0.5)
    raise TimeoutError("job did not finish")


def duration(p):
    import soundfile as sf
    i = sf.info(str(p))
    return i.frames / i.samplerate


info = get("/api/info")
print("info:", info["version"], info["presets"])
params = {"warmth": 50, "presence": 50, "air": 50, "tightness": 50, "intensity": 50}
# The first wait covers the one-time model load (and download on a fresh machine).
while get("/api/status")["state"] == "running":
    time.sleep(1)
post("/api/full", {"path": str(clip), "params": params, "preset": "warm_pro", "target": "youtube"})
s, t = wait()
print("full:", s["state"], s["msg"], f"{t:.1f}s")
assert s["state"] == "done", s
res = Path(s["result"]["output"])
print("output:", res, f"in {duration(clip):.2f}s out {duration(res):.2f}s")
assert res.is_file() and abs(duration(res) - duration(clip)) < 0.5
print("OK")
