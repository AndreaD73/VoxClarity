"""VoceStudio engine: Sidon resynthesis + sound finishing + loudness. Importable, no CLI."""
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

# No telemetry from the Hugging Face client. The model files are NOT forced offline: on first run
# they are downloaded from the Hub into the normal Hugging Face cache.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np
import soundfile as sf
import torch
import torchaudio
from scipy.signal import fftconvolve, firwin2

VERSION = "0.4.2"
REPO_URL = "https://github.com/AndreaD73/VoceStudio"
CHUNK_S = 30
SR = 48000
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
REPO = "sarulab-speech/sidon-v0.1"
W2V_REPO = "facebook/w2v-bert-2.0"
# Exact model revisions (Hugging Face commit hashes): what we tested is what gets downloaded.
REPO_REV = "b3b02d8bbd55fdbc410e6e46e76ef95ace4fbf52"
W2V_REV = "da985ba0987f70aaeb84a80f2851cfac8c697a7b"
APP_DIR = Path(__file__).resolve().parent
LOG = logging.getLogger("vocestudio")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ffmpeg_exe():
    """ffmpeg bundled by install.ps1 (<app>/ffmpeg/bin) if present, else the one on PATH."""
    local = APP_DIR / "ffmpeg" / "bin" / "ffmpeg.exe"
    if local.is_file():
        return str(local)
    return shutil.which("ffmpeg") or "ffmpeg"


# Finishing curves (Hz, dB).
STUDIO_CURVE = [(0, 0), (80, 2), (150, 3), (400, -2), (900, 0), (2500, 2), (4000, 5),
                (7000, 4), (10000, 6), (14000, 5), (SR / 2, 3)]
PODCAST_CURVE = [(0, -6), (70, -3), (100, 1), (250, 1), (400, -2), (1000, 0), (3000, 3),
                 (5000, 2), (9000, 0), (14000, -1), (SR / 2, -2)]
RADIO_CURVE = [(0, -9), (80, -4), (130, 2), (250, 3), (500, 0), (1500, 1), (3500, 4),
               (6000, 3), (10000, -1), (14000, -3), (SR / 2, -5)]
FLAT_CURVE = [(0, 0), (SR / 2, 0)]
# More body, tamed presence and sibilance, soft top end (which also hides resynthesis artefacts).
WARM_PRO_CURVE = [(0, -6), (60, 0), (120, 4), (220, 4.5), (400, 1.5), (800, 0), (2000, -0.5),
                  (3500, -2), (6000, -4.5), (9000, -6.5), (14000, -9), (SR / 2, -10)]

# key -> (label, curve, compressor ratio, compressor threshold dB)
PRESETS = {
    "warm_pro": ("Warm pro", WARM_PRO_CURVE, 3.0, -32.0),
    "studio": ("Warm studio", STUDIO_CURVE, 4.0, -34.0),
    "natural": ("Natural", FLAT_CURVE, 1.0, -34.0),
    "podcast": ("Podcast", PODCAST_CURVE, 3.0, -30.0),
    "radio": ("Radio", RADIO_CURVE, 5.0, -32.0),
}
TARGETS = {"youtube": -14.0, "podcast": -16.0, "none": None}
DEFAULTS = {"warmth": 50, "presence": 50, "air": 50, "tightness": 50, "intensity": 50}


def pick_device(requested=None):
    """Return the CUDA device to use.

    The Sidon TorchScript files are CUDA builds bound to cuda:0 (they fail on cuda:1), and
    switching card forces a full reload, so stay on the card already loaded, else cuda:0.
    There is no CPU path: without a CUDA device this raises.
    """
    if requested:
        return requested
    if not torch.cuda.is_available():
        raise RuntimeError("An NVIDIA graphics card with CUDA is required: no CUDA device found.")
    if _models:
        return next(iter(_models))
    return "cuda:0"


def gpu_name():
    """Name of the first CUDA device, or '' if none."""
    try:
        return torch.cuda.get_device_name(0) if torch.cuda.is_available() else ""
    except Exception:
        return ""


def gpu_info(dev):
    i = torch.device(dev).index or 0
    free, total = torch.cuda.mem_get_info(i)
    return f"{torch.cuda.get_device_name(i)} ({dev}) free VRAM {free / 2**20:.0f}/{total / 2**20:.0f} MiB"


def read_audio(path):
    """Decode any audio/video file to mono float32 at SR via ffmpeg."""
    cmd = [ffmpeg_exe(), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, creationflags=NOWIN).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


_models = {}
_load_lock = threading.Lock()


def _load_models(dev):
    with _load_lock:
        return _load_models_locked(dev)


def _load_models_locked(dev):
    if dev in _models:
        return _models[dev]
    t = time.time()
    import transformers
    from huggingface_hub import hf_hub_download
    _models.clear()
    torch.cuda.empty_cache()

    def get(name):
        # Local copy first (the online check alone costs seconds at every start); download if missing.
        try:
            return hf_hub_download(REPO, name, revision=REPO_REV, local_files_only=True)
        except Exception:
            return hf_hub_download(REPO, name, revision=REPO_REV)

    def load_ts(name):
        # Open the file ourselves: torch.jit.load(path) fails on paths with accented characters
        # (for example a Windows user name with accented letters); a file object does not.
        with open(get(name), "rb") as f:
            return torch.jit.load(f, map_location=dev).to(dev)

    fe = load_ts("feature_extractor_cuda.pt")
    dec = load_ts("decoder_cuda.pt")
    try:
        pre = transformers.SeamlessM4TFeatureExtractor.from_pretrained(W2V_REPO, revision=W2V_REV,
                                                                       local_files_only=True)
    except Exception:
        pre = transformers.SeamlessM4TFeatureExtractor.from_pretrained(W2V_REPO, revision=W2V_REV)
    _models[dev] = (fe, dec, pre)
    LOG.info("Sidon models loaded on %s in %.1f s", dev, time.time() - t)
    return _models[dev]


_gpu_lock = threading.Lock()


def regenerate(x, dev, progress=None):
    """One GPU inference at a time (the start-up warm-up and a user job must not overlap)."""
    with _gpu_lock:
        return _regenerate(x, dev, progress)


def _regenerate(x, dev, progress=None):
    """Sidon resynthesis in CHUNK_S chunks (long single blocks run out of memory on 10 GB cards)."""
    fe, dec, pre = _load_models(dev)
    peak = np.abs(x).max() or 1.0
    w = torch.from_numpy(0.9 * x / peak).view(1, -1)
    w = torchaudio.functional.highpass_biquad(w, SR, 50)
    w16 = torchaudio.functional.resample(w, SR, 16000)
    w16 = torch.nn.functional.pad(w16, (0, 24000))
    chunks = list(w16.view(-1).split(16000 * CHUNK_S))
    outs, cache = [], None
    torch.cuda.reset_peak_memory_stats(torch.device(dev))
    with torch.inference_mode():
        for k, chunk in enumerate(chunks):
            feats = pre(torch.nn.functional.pad(chunk, (160, 160)), return_tensors="pt")
            feat = fe(feats["input_features"].to(dev))["last_hidden_state"]
            if cache is not None:
                feat = torch.cat([cache, feat], dim=1)
            outs.append(dec(feat.transpose(1, 2)).view(-1)[:-960].cpu())  # keep results off the GPU
            cache = feat[:, -1:]
            del feats, feat
            if progress:
                progress((k + 1) / len(chunks))
    peak_mb = torch.cuda.max_memory_allocated(torch.device(dev)) / 2**20
    LOG.info("Sidon: %d blocks, peak VRAM %.0f MiB", len(chunks), peak_mb)
    return torch.cat(outs).float().cpu().numpy()[: len(x)]


def _bell(f, fc, width_oct, gain_db):
    lf = np.log2(np.maximum(f, 1.0) / fc)
    return gain_db * np.exp(-0.5 * (lf / (width_oct / 2)) ** 2)


def build_curve(preset, p):
    """Preset curve plus slider bells, scaled by intensity above 50. Returns (f, dB) arrays."""
    f = np.linspace(0, SR / 2, 2048)
    hz, db = zip(*PRESETS[preset][1])
    curve = np.interp(f, hz, db)
    curve = (curve + _bell(f, 200, 1.4, (p["warmth"] - 50) / 50 * 5)
             + _bell(f, 3500, 1.2, (p["presence"] - 50) / 50 * 5)
             + _bell(f, 12000, 1.6, (p["air"] - 50) / 50 * 6))
    boost = 1 + max(0, p["intensity"] - 50) / 50 * 0.6
    return f, curve * boost


def shape(x, f, db):
    taps = firwin2(2047, f / (SR / 2), 10 ** (db / 20))
    return fftconvolve(x, taps, mode="same")


def compress(x, threshold_db=-34.0, ratio=4.0, attack=0.005, release=0.12):
    """Block-wise compressor (1 ms blocks): fast enough for hour-long files."""
    n = SR // 1000
    pad = (-len(x)) % n
    blocks = np.abs(np.pad(x, (0, pad))).reshape(-1, n).max(axis=1)
    a, r = np.exp(-1 / (attack * 1000)), np.exp(-1 / (release * 1000))
    env = np.empty_like(blocks)
    e = 0.0
    for i, s in enumerate(blocks):
        e = a * e + (1 - a) * s if s > e else r * e + (1 - r) * s
        env[i] = e
    over = np.maximum(0.0, 20 * np.log10(env + 1e-9) - threshold_db)
    gain = 10 ** (-(over - over / ratio) / 20)
    g = np.interp(np.arange(len(x)), np.arange(len(gain)) * n + n / 2, gain)
    return x * g


def finish(y, preset, params):
    """EQ + compression per preset/sliders, then blend with plain Sidon output (intensity)."""
    p = {**DEFAULTS, **{k: float(v) for k, v in params.items() if k in DEFAULTS}}
    _, _, ratio0, thr = PRESETS[preset]
    k = 2 ** ((p["tightness"] - 50) / 50 * 1.3)
    ratio = ratio0 * k if ratio0 > 1 else 1 + max(0, (p["tightness"] - 50) / 50) * 2
    f, db = build_curve(preset, p)
    z = y
    if np.abs(db).max() > 0.05:
        z = shape(z, f, db)
    if ratio > 1.05:
        z = compress(z, thr, ratio)
    mix = min(1.0, p["intensity"] / 50)
    # Match level to the plain signal before blending so the mix does not jump in loudness.
    z = z * (np.sqrt(np.mean(y ** 2)) / (np.sqrt(np.mean(z ** 2)) + 1e-12))
    return mix * z + (1 - mix) * y


def set_loudness(x, target_key):
    """Integrated loudness (pyloudnorm, EBU R128) to the target; RMS -20 dB when target is None."""
    target = TARGETS[target_key]
    if target is None:
        y = x * 10 ** (-20 / 20) / (np.sqrt(np.mean(x ** 2)) + 1e-12)
    else:
        import pyloudnorm as pyln
        cur = pyln.Meter(SR).integrated_loudness(x.astype(np.float64))
        y = x * 10 ** ((target - cur) / 20) if np.isfinite(cur) else x
    return limit(y).astype(np.float32)


def limit(y, ceiling_db=-1.0, lookahead_ms=5.0):
    """Look-ahead peak limiter: smooth gain reduction instead of shaping each sample.

    A per-sample soft clipper distorts loud peaks; this keeps the waveform intact.
    """
    from scipy.ndimage import minimum_filter1d, uniform_filter1d
    ceiling = 10 ** (ceiling_db / 20)
    n = max(1, int(SR * lookahead_ms / 1000))
    need = np.minimum(1.0, ceiling / (np.abs(y) + 1e-12))
    g = minimum_filter1d(need, size=4 * n + 1)        # hold the reduction around each peak
    g = uniform_filter1d(g, size=2 * n + 1)           # smooth attack/release, no clicks
    g = np.minimum(g, minimum_filter1d(need, size=2 * n + 1))  # guarantee the ceiling
    return y * g


def pick_preview_window(x, seconds=10):
    """Sample range of the most energetic `seconds` window (1 s frames)."""
    n = len(x)
    w = seconds * SR
    if n <= w:
        return 0, n
    frames = np.sqrt(np.add.reduceat(x ** 2, np.arange(0, n, SR)))[: n // SR]
    win = np.convolve(frames, np.ones(seconds), mode="valid")
    s = int(np.argmax(win)) * SR
    return s, min(n, s + w)


_cache = {}


def process(x, params, preset, target, dev, progress=None, cache_key=None):
    """Chain on a mono signal: Sidon -> finishing -> loudness. Returns (audio, timings)."""
    t = {}
    t0 = time.time()
    if cache_key is not None and _cache.get("key") == cache_key:
        y = _cache["y"]
        LOG.info("Sidon: reusing the in-memory result (only the finishing parameters changed)")
    else:
        y = regenerate(x, dev, progress)
        if cache_key is not None:
            _cache.update(key=cache_key, y=y)
    t["sidon"] = time.time() - t0
    t1 = time.time()
    z = set_loudness(finish(y, preset, params), target)
    t["finishing"] = time.time() - t1
    return z, t


def write_output(src, y, out):
    """Audio file: write WAV. Video: copy the picture, replace the audio track."""
    if Path(src).suffix.lower() in VIDEO_EXT:
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "voice.wav"
            sf.write(wav, y, SR)
            subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-i", str(src), "-i", str(wav), "-map", "0:v",
                            "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
                            str(out)], check=True, creationflags=NOWIN)
    else:
        sf.write(out, y, SR)


def sound_tag(preset):
    """File-name tag of a sound preset: 'Warm pro' -> 'Warm-pro'."""
    return PRESETS.get(preset, (preset,))[0].replace(" ", "-")


def safe_tag(name):
    """Any user text -> safe file-name piece: 'Warm voice 2!' -> 'Warm-voice-2'."""
    return re.sub(r"[^\w\-]+", "-", name.strip(), flags=re.UNICODE).strip("-")[:90] or "setting"


def default_output(src, preset="warm_pro", tag=None):
    """Output name carries the sound or saved setting used: clip.wav -> clip_Warm-pro.wav."""
    src = Path(src)
    t = safe_tag(tag) if tag else sound_tag(preset)
    return src.with_name(src.stem + "_" + t + (src.suffix if src.suffix.lower() in VIDEO_EXT else ".wav"))
