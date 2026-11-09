"""VoceStudio window app: local HTTP server + HTML UI shown as a browser app window.

Run: python server.py [--no-window] [--port N] [file to preselect]

The server only listens on 127.0.0.1. Nothing is sent anywhere, except the explicit
"Check for updates" button (one request to the GitHub API) and the first-run model download.
"""
import argparse
import hmac
import http.server
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent
UI = APP / "ui"
HOME = Path.home()
# Settings and logs live in the roaming profile, heavy work files in the local profile.
APPDATA_DIR = Path(os.environ.get("APPDATA") or HOME / "AppData" / "Roaming") / "VoceStudio"
LOGDIR = APPDATA_DIR / "logs"
WORK = Path(os.environ.get("LOCALAPPDATA") or HOME / "AppData" / "Local") / "VoceStudio" / "work"
for _d in (LOGDIR, WORK / "inbox"):
    _d.mkdir(parents=True, exist_ok=True)
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# pythonw has no stdout/stderr: send them to the log so nothing crashes silently.
LOGFILE = LOGDIR / f"vocestudio_{datetime.now():%Y-%m-%d}.log"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(LOGFILE, "a", encoding="utf-8", buffering=1)

import logging  # noqa: E402

logging.basicConfig(filename=str(LOGFILE), level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("vocestudio")


def _rotate_logs(keep=10):
    """Keep only the newest `keep` daily log files (names carry the date, so name order = age)."""
    try:
        for f in sorted(LOGDIR.glob("vocestudio_*.log"))[:-keep]:
            f.unlink(missing_ok=True)
    except OSError:
        pass


_rotate_logs()


def _choose_gpu():
    """Expose only the card with the most free memory, before torch loads.

    Sidon's TorchScript files only run on the process's cuda:0, so on multi-GPU machines the
    least busy card is made to be cuda:0. Skipped when CUDA_VISIBLE_DEVICES is already set.
    """
    if "CUDA_VISIBLE_DEVICES" in os.environ:
        return
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.free,utilization.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True,
                             timeout=10, creationflags=NOWIN).stdout
        rows = [[int(v) for v in line.split(",")] for line in out.strip().splitlines()]
        best = max(rows, key=lambda r: r[1] * (100 - r[2]) / 100)
        os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        os.environ["CUDA_VISIBLE_DEVICES"] = str(best[0])
        os.environ["VOCESTUDIO_GPU_INFO"] = out.strip().replace("\n", " | ")
    except Exception:
        pass


_choose_gpu()
sys.path.insert(0, str(APP))
import engine  # noqa: E402



def documents_dir():
    """The user's real Documents folder (it may be redirected, e.g. to OneDrive or another drive)."""
    try:
        import ctypes

        class GUID(ctypes.Structure):
            _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort), ("d3", ctypes.c_ushort),
                        ("d4", ctypes.c_ubyte * 8)]

        folder_id = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                         (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
        get = ctypes.windll.shell32.SHGetKnownFolderPath
        get.argtypes = [ctypes.POINTER(GUID), ctypes.c_ulong, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        get.restype = ctypes.c_long
        buf = ctypes.c_void_p()
        hr = get(ctypes.byref(folder_id), 0, None, ctypes.byref(buf))
        try:
            if hr == 0 and buf.value:
                return Path(ctypes.wstring_at(buf.value))
        finally:
            ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
            ctypes.windll.ole32.CoTaskMemFree(buf)
    except Exception:
        pass
    return HOME / "Documents"


DROP_OUT = documents_dir() / "VoceStudio"
# Random secret of this run: given only to the window we open (in its URL), required on every API/media request.
TOKEN = secrets.token_urlsafe(24)
DEFAULT_PORT = 47811          # fixed default so the browser origin (and its microphone permission) stays the same
MAX_UPLOAD = 4 * 2**30        # largest accepted upload (drag and drop / recording), in bytes
BROWSER_PROFILE = Path(os.environ.get("LOCALAPPDATA") or HOME / "AppData" / "Local") / "VoceStudio" / "browser"
CONFIG_FILE = APPDATA_DIR / "config.json"
CONFIG_KEYS = {"winH", "lang", "outdir", "preset", "target", "params", "mic", "setName", "input"}


def default_lang():
    """Italian if the Windows UI language is Italian, else English."""
    try:
        import ctypes
        return "it" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0xFF) == 0x10 else "en"
    except Exception:
        return "en"


def load_config():
    try:
        d = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_config(d):
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")  # no BOM
    os.replace(tmp, CONFIG_FILE)


CONFIG = load_config()
if CONFIG.get("lang") not in ("it", "en"):
    CONFIG["lang"] = default_lang()

# Messages produced by the server (status bar, dialogs); the UI has its own dictionary.
MSG = {
    "it": {"ready": "Pronto", "starting": "Avvio...", "reading": "Leggo il file...",
           "regen_full": "Rigenero la voce sulla scheda video...", "regen_prev": "Anteprima: rigenero 10 secondi...",
           "preparing": "Preparo il confronto...", "models": "Preparo i modelli (al primo avvio vengono scaricati, circa 1 GB)...",
           "warm_failed": "Modelli non caricati: {err}. Dettagli nel Log.",
           "no_cuda": "serve una scheda video NVIDIA (CUDA): nessuna trovata", "too_big": "file troppo grande (massimo 4 GB)", "writing": "Scrivo il file...",
           "prev_done": "Convertito con il suono {label} in {sec:.1f} s: e' in cima alla lista Uscite.",
           "done": "Fatto in {sec:.0f} s: {name}", "error": "Errore: {err}. Dettagli nel Log.",
           "busy": "occupato", "no_name": "manca il nome", "not_allowed": "uscita non consentita",
           "prev_name": "{stem}_{tag} (anteprima 10 s)",
           "queue_file": "File {i} di {n}: {name} -", "queue_done": "{ok} file elaborati, {err} errori",
           "queue_stopped": "Fermato: {ok} file elaborati, {err} errori",
           "dlg_filter": "Audio e video|*.wav;*.mp3;*.m4a;*.flac;*.ogg;*.aac;*.mp4;*.mov;*.mkv;*.avi;*.webm;*.m4v|Tutti i file|*.*",
           "dlg_title": "Scegli un file audio o video", "folder_title": "Scegli la cartella delle uscite"},
    "en": {"ready": "Ready", "starting": "Starting...", "reading": "Reading the file...",
           "regen_full": "Regenerating the voice on the graphics card...", "regen_prev": "Preview: regenerating 10 seconds...",
           "preparing": "Preparing the comparison...", "models": "Preparing the models (downloaded on the first run, about 1 GB)...",
           "warm_failed": "Models not loaded: {err}. See the Log for details.",
           "no_cuda": "an NVIDIA graphics card (CUDA) is required: none found", "too_big": "file too large (4 GB maximum)", "writing": "Writing the file...",
           "prev_done": "Converted with the {label} sound in {sec:.1f} s: it is at the top of the Outputs list.",
           "done": "Done in {sec:.0f} s: {name}", "error": "Error: {err}. See the Log for details.",
           "busy": "busy", "no_name": "name is missing", "not_allowed": "output not allowed",
           "prev_name": "{stem}_{tag} (10 s preview)",
           "queue_file": "File {i} of {n}: {name} -", "queue_done": "{ok} files processed, {err} errors",
           "queue_stopped": "Stopped: {ok} files processed, {err} errors",
           "dlg_filter": "Audio and video|*.wav;*.mp3;*.m4a;*.flac;*.ogg;*.aac;*.mp4;*.mov;*.mkv;*.avi;*.webm;*.m4v|All files|*.*",
           "dlg_title": "Choose an audio or video file", "folder_title": "Choose the output folder"},
}
SOUNDS = {"warm_pro": ("Caldo pro", "Warm pro"), "studio": ("Studio caldo", "Warm studio"),
          "natural": ("Naturale", "Natural"), "podcast": ("Podcast", "Podcast"), "radio": ("Radio", "Radio")}


def T(key, **kw):
    return MSG[CONFIG["lang"]][key].format(**kw)


def sound_label(key):
    return SOUNDS[key][0 if CONFIG["lang"] == "it" else 1] if key in SOUNDS else key


def out_dir():
    """Configured output folder (default Documents\\VoceStudio)."""
    p = CONFIG.get("outdir")
    return Path(p) if p else DROP_OUT


JOB = {"state": "idle", "msg": T("ready"), "progress": 0.0, "result": None, "seq": 0, "warm": "loading"}
LOCK = threading.Lock()
LAST_PING = [0.0]
PREV = WORK / "previews"          # 10 s previews, one per input and sound
INPUTS_FILE = WORK / "inputs.json"
INPUTS = []                          # [{"path", "name", "added"}], newest first


def load_inputs():
    try:
        INPUTS[:] = [i for i in json.loads(INPUTS_FILE.read_text(encoding="utf-8")) if Path(i["path"]).exists()]
    except Exception:
        INPUTS[:] = []


def add_input(path):
    """Remember an input (uploaded, recorded, picked) so it shows in the inputs list."""
    p = str(Path(path))
    INPUTS[:] = [i for i in INPUTS if i["path"] != p]
    INPUTS.insert(0, {"path": p, "name": Path(p).name, "added": datetime.now().strftime("%d/%m %H:%M")})
    del INPUTS[30:]
    INPUTS_FILE.write_text(json.dumps(INPUTS, ensure_ascii=False, indent=1), encoding="utf-8")


WRITTEN_FILE = APPDATA_DIR / "written.json"


def _written():
    try:
        return set(json.loads(WRITTEN_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def remember_written(path):
    """Remember files this app wrote, so only those can ever be sent to the Recycle Bin."""
    w = _written()
    w.add(str(path))
    WRITTEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    WRITTEN_FILE.write_text(json.dumps(sorted(w), ensure_ascii=False), encoding="utf-8")


def glob_escape(s):
    return "".join("[" + c + "]" if c in "[]*?" else c for c in s)


# Saved settings (sound + volume + sliders), kept inside the app data folder: no browser save dialog.
SETTINGS_FILE = APPDATA_DIR / "settings.json"


def load_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(d):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def outputs_of(src, extra_dir=None):
    """Every output created from one input: 10 s previews and complete files, newest first."""
    src = Path(src)
    res = []
    orig_prev = PREV / f"{src.stem}__original.wav"
    for f in PREV.glob(f"{glob_escape(src.stem)}__*.wav"):
        key = f.stem.split("__", 1)[1]
        if key in engine.PRESETS:
            lab = sound_label(key)
            res.append({"name": T("prev_name", stem=src.stem, tag=lab.replace(" ", "-")), "sound": lab,
                        "kind": "preview", "url": "/prev/" + f.name, "orig": "/prev/" + orig_prev.name,
                        "file": str(f), "mtime": f.stat().st_mtime})
    orig_full = PREV / f"{src.stem}__original_full.wav"
    dirs = {src.parent, DROP_OUT, out_dir()} | ({Path(extra_dir)} if extra_dir else set())
    exts = {".wav"} | engine.VIDEO_EXT
    for d in dirs:
        for f in d.glob(glob_escape(src.stem) + "_*"):
            if f.suffix.lower() not in exts or f == src:
                continue
            res.append({"name": f.name, "sound": f.stem[len(src.stem) + 1:].replace("-", " ").replace("_", " / "), "kind": "full",
                        "path": str(f), "file": str(f), "url": "/file?p=" + urllib.parse.quote(str(f)),
                        "orig": "/prev/" + orig_full.name, "mtime": f.stat().st_mtime})
    return sorted(res, key=lambda r: -r["mtime"])


SESSION = {}
QUEUE = {"n": 0, "i": 0, "name": "", "stop": False, "ok": 0, "err": 0, "last": None}


def set_job(**kw):
    with LOCK:
        if QUEUE["n"] > 1:  # inside a queue: prefix messages, scale progress, hold back per-file end states
            if "msg" in kw and kw.get("state") not in ("done", "error"):
                kw["msg"] = T("queue_file", i=QUEUE["i"] + 1, n=QUEUE["n"], name=QUEUE["name"]) + " " + kw["msg"]
            if "progress" in kw:
                kw["progress"] = (QUEUE["i"] + kw["progress"]) / QUEUE["n"]
            if kw.get("state") in ("done", "error"):
                QUEUE["last"] = kw["state"]
                QUEUE["ok" if kw["state"] == "done" else "err"] += 1
                kw["state"] = "running"
                kw["progress"] = (QUEUE["i"] + 1) / QUEUE["n"]
                if QUEUE["last"] == "error":
                    LOG.error("Queue: file %s failed: %s", QUEUE["name"], kw.get("msg"))
        JOB.update(kw)
        if "msg" in kw:
            LOG.info("STATUS: %s", kw["msg"])


def run_queue(kind, body, paths):
    """Process several inputs one after another with the same parameters; a failing file does not stop the rest."""
    with LOCK:
        QUEUE.update(n=len(paths), i=0, name="", stop=False, ok=0, err=0, last=None)
    done = 0
    for i, p in enumerate(paths):
        if QUEUE["stop"]:
            break
        QUEUE.update(i=i, name=Path(p).name)
        run_job(kind, dict(body, path=p))
        done += 1
    with LOCK:
        key = "queue_stopped" if QUEUE["stop"] and done < len(paths) else "queue_done"
        JOB.update(state="done" if QUEUE["err"] == 0 else "error", progress=1.0, result={"kind": "queue"},
                   msg=T(key, ok=QUEUE["ok"], err=QUEUE["err"]))
        LOG.info("STATUS: %s", JOB["msg"])
        QUEUE.update(n=0)


def vram():
    try:
        return engine.gpu_info(SESSION["dev"]) if "dev" in SESSION else "-"
    except Exception:
        return "-"


def pick_file_dialog():
    """Native Windows open-file dialog through PowerShell/WinForms."""
    ps = ("Add-Type -AssemblyName System.Windows.Forms;"
          "$f=New-Object System.Windows.Forms.OpenFileDialog;"
          "$f.Filter='" + T("dlg_filter") + "';"
          "$f.Title='" + T("dlg_title") + "';"
          "$f.Multiselect=$true;"
          "$o=New-Object System.Windows.Forms.Form;$o.TopMost=$true;"
          "if($f.ShowDialog($o) -eq 'OK'){[Console]::OutputEncoding=[Text.Encoding]::UTF8;$f.FileNames|Write-Output}")
    r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True,
                       creationflags=NOWIN)
    return [x.strip() for x in r.stdout.decode("utf-8", "replace").splitlines() if x.strip()]


def pick_folder_dialog():
    """Explorer-style folder dialog (pick_folder.ps1)."""
    r = subprocess.run(["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File", str(APP / "pick_folder.ps1"),
                        "-Start", str(out_dir()), "-Title", T("folder_title")], capture_output=True, creationflags=NOWIN)
    if r.returncode:
        LOG.error("pick_folder.ps1: %s", r.stderr.decode("utf-8", "replace")[:500])
    return r.stdout.decode("utf-8", "replace").strip()


def recycle(path):
    """Send a file to the Windows Recycle Bin (never a hard delete)."""
    ps = ("Add-Type -AssemblyName Microsoft.VisualBasic;"
          "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($env:VS_DEL,'OnlyErrorDialogs','SendToRecycleBin')")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True,
                       creationflags=NOWIN, env=dict(os.environ, VS_DEL=str(path)))
    if r.returncode:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:300])


def run_job(kind, body):
    """Worker thread: preview (10 s) or full processing."""
    t_all = time.time()
    try:
        src = Path(body["path"])
        params = body.get("params", {})
        preset = body.get("preset", "warm_pro")
        target = body.get("target", "none")
        if preset not in engine.PRESETS or target not in engine.TARGETS:
            raise ValueError("unknown preset or target")
        LOG.info("ACTION %s file=%s preset=%s target=%s params=%s", kind, src.name, preset, target,
                 json.dumps(params))
        set_job(state="running", msg=T("reading"), progress=0.02, result=None)
        t = time.time()
        x = engine.read_audio(src)
        LOG.info("Read %.1f s of audio in %.1f s", len(x) / engine.SR, time.time() - t)
        if "dev" not in SESSION:
            SESSION["dev"] = engine.pick_device(body.get("device"))
        dev = SESSION["dev"]
        LOG.info("GPU: %s", vram())
        key = (str(src), src.stat().st_mtime, kind)
        if kind == "preview":
            a, b = engine.pick_preview_window(x, 10)
            x = x[a:b]
            key = key + (a,)
            LOG.info("Preview: window %.1f-%.1f s", a / engine.SR, b / engine.SR)
        else:
            # Keep the heavy result for files up to 10 min, so a new sound/volume on the same input is quick.
            key = key if len(x) <= 600 * engine.SR else None
        set_job(msg=T("regen_full") if kind == "full" else T("regen_prev"), progress=0.1)
        y, t = engine.process(x, params, preset, target, dev,
                              progress=lambda f: set_job(progress=0.1 + 0.75 * f), cache_key=key)
        LOG.info("Timings: %s | VRAM after: %s", {k: round(v, 2) for k, v in t.items()}, vram())
        import soundfile as sf
        if kind == "preview":
            set_job(msg=T("preparing"), progress=0.9)
            PREV.mkdir(parents=True, exist_ok=True)
            sf.write(PREV / f"{src.stem}__original.wav", engine.set_loudness(x, target), engine.SR)
            f = PREV / f"{src.stem}__{preset}.wav"
            sf.write(f, y, engine.SR)
            set_job(state="done", progress=1.0,
                    msg=T("prev_done", label=sound_label(preset), sec=time.time() - t_all),
                    result={"kind": "preview", "url": "/prev/" + f.name})
        else:
            set_job(msg=T("writing"), progress=0.92)
            dst_dir = out_dir()  # every output goes to the configured output folder
            dst_dir.mkdir(parents=True, exist_ok=True)
            out = engine.default_output(dst_dir / src.name, preset, body.get("tag"))
            engine.write_output(src, y, out)
            remember_written(out)
            PREV.mkdir(parents=True, exist_ok=True)
            sf.write(PREV / f"{src.stem}__original_full.wav", engine.set_loudness(x, target), engine.SR)
            LOG.info("Written %s (%.1f MB)", out.name, out.stat().st_size / 2**20)
            set_job(state="done", progress=1.0, msg=T("done", sec=time.time() - t_all, name=out.name),
                    result={"kind": "full", "output": str(out), "url": "/file?p=" + urllib.parse.quote(str(out))})
    except Exception as e:
        LOG.error("ERROR %s: %s\n%s", kind, e, traceback.format_exc())
        set_job(state="error", msg=T("error", err=e), progress=0.0)
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass


def open_app_window(url):
    """Open the UI as a Chrome/Edge app window (no tabs); fall back to the default browser.

    The window uses its own browser profile (%LOCALAPPDATA%\\VoceStudio\\browser) and a fixed local port, so
    the browser remembers the microphone permission you grant once. No permission prompt is bypassed.
    """
    rels = (Path("Google") / "Chrome" / "Application" / "chrome.exe",
            Path("Microsoft") / "Edge" / "Application" / "msedge.exe")
    for rel in rels:
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
                     os.environ.get("LOCALAPPDATA", "")):
            exe = Path(base) / rel
            if base and exe.is_file():
                h = int(load_config().get("winH") or 720)  # height measured by the page last time
                BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
                subprocess.Popen([str(exe), f"--app={url}", f"--window-size=1040,{max(400, min(h, 1400))}",
                                  f"--user-data-dir={BROWSER_PROFILE}", "--no-first-run",
                                  "--no-default-browser-check"])
                return
    import webbrowser
    webbrowser.open(url)


# ---- About / updates / problem report -------------------------------------------------------

def _version_tuple(s):
    parts = []
    for p in str(s).lstrip("vV").split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_update():
    """Ask the GitHub releases API of REPO_URL for the latest release. Never raises.

    Returns {"state": "newer"|"current"|"none"|"offline"|"error", "latest": tag, "url": page}.
    """
    api = engine.REPO_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/releases/latest"
    req = urllib.request.Request(api, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"VoceStudio/{engine.VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:  # no release published yet (or repository not public)
            return {"state": "none", "url": engine.REPO_URL + "/releases"}
        return {"state": "error", "detail": f"HTTP {e.code}", "url": engine.REPO_URL + "/releases"}
    except (urllib.error.URLError, OSError, TimeoutError):
        return {"state": "offline"}
    except Exception as e:
        return {"state": "error", "detail": str(e)[:100]}
    tag = str(d.get("tag_name") or "")
    url = d.get("html_url") or engine.REPO_URL + "/releases"
    if not tag:
        return {"state": "none", "url": engine.REPO_URL + "/releases"}
    newer = _version_tuple(tag) > _version_tuple(engine.VERSION)
    return {"state": "newer" if newer else "current", "latest": tag, "url": url}


def system_info():
    """Version, Windows version and GPU name for the problem report (no paths, no user name)."""
    return {"version": engine.VERSION, "windows": f"{platform.system()} {platform.release()} ({platform.version()})",
            "gpu": engine.gpu_name() or "none detected", "python": platform.python_version()}


def report_url():
    """Pre-filled GitHub new-issue URL; contains only version, Windows version and GPU name."""
    s = system_info()
    body = (f"**VoceStudio version:** {s['version']}\n**Windows:** {s['windows']}\n**GPU:** {s['gpu']}\n"
            f"**Python:** {s['python']}\n\n**What happened?**\n\n\n**What did you expect?**\n\n\n"
            "**Log file:** please attach the newest file from `%APPDATA%\\VoceStudio\\logs`. "
            "Check it first: it contains the names of the files you processed and folder paths, "
            "which may include your Windows user name.\n")
    q = urllib.parse.urlencode({"title": "Problem report", "body": body}, quote_via=urllib.parse.quote)
    return engine.REPO_URL + "/issues/new?" + q


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _local_only(self):
        """Refuse requests whose Host/Origin is not this local server (DNS rebinding, other web pages)."""
        port = self.server.server_address[1]
        ok_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "") not in ok_hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.split("://", 1)[-1] in ok_hosts

    def _guard(self):
        """Host/Origin check on every request, plus the access token on everything but the static UI files.

        The token comes in the X-VS-Token header (fetch) or the `t` query parameter (audio elements).
        Returns False after answering 403.
        """
        ok = self._local_only()
        if ok:
            u = urllib.parse.urlparse(self.path)
            if u.path.startswith(("/api/", "/prev/")) or u.path == "/file":
                tok = self.headers.get("X-VS-Token") or urllib.parse.parse_qs(u.query).get("t", [""])[0]
                ok = hmac.compare_digest(tok.encode("utf-8"), TOKEN.encode("utf-8"))
        if not ok:
            self._json({"error": "forbidden"}, 403)
        return ok

    def translate_path(self, path):
        p = urllib.parse.urlparse(path).path
        if p.startswith("/prev/"):
            return str(PREV / Path(urllib.parse.unquote(p[6:])).name)
        if p == "/file":  # complete outputs: only files this app lists as outputs
            f = urllib.parse.parse_qs(urllib.parse.urlparse(path).query).get("p", [""])[0]
            ok = any(o.get("path") == f for i in INPUTS for o in outputs_of(i["path"]))
            return f if ok else str(UI / "nonexistent")
        f = (UI / urllib.parse.unquote(p).lstrip("/\\") if p.strip("/") else UI / "index.html").resolve()
        return str(f) if UI.resolve() in f.parents else str(UI / "nonexistent")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_HEAD(self):
        if not self._guard():
            return
        p = urllib.parse.urlparse(self.path).path
        if p.startswith("/prev/") or p == "/file":
            return self._send_ranged(Path(self.translate_path(self.path)))
        if p.startswith("/api/"):
            return self._json({"error": "method not allowed"}, 405)
        return super().do_HEAD()

    def do_GET(self):
        if not self._guard():
            return
        p = urllib.parse.urlparse(self.path).path
        if p == "/api/info":
            return self._json({
                "version": engine.VERSION, "repo": engine.REPO_URL,
                "presets": list(engine.PRESETS), "targets": list(engine.TARGETS),
                "defaults": engine.DEFAULTS, "preselect": SESSION.get("preselect", "")})
        if p == "/api/config":
            return self._json({"config": CONFIG, "outdir": str(out_dir()), "default_outdir": str(DROP_OUT)})
        if p == "/api/settings":
            return self._json({"settings": load_settings()})
        if p == "/api/inputs":
            return self._json({"inputs": INPUTS})
        if p == "/api/outputs":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self._json({"outputs": outputs_of(q.get("path", [""])[0])})
        if p == "/api/status":
            with LOCK:
                return self._json(dict(JOB, queue={"i": QUEUE["i"] + 1, "n": QUEUE["n"], "name": QUEUE["name"],
                                                   "ok": QUEUE["ok"], "err": QUEUE["err"]}))
        if p == "/api/update-check":
            return self._json(check_update())
        if p.startswith("/prev/") or p == "/file":
            return self._send_ranged(Path(self.translate_path(self.path)))
        return super().do_GET()

    def _send_ranged(self, f):
        """Serve audio with HTTP Range support (GET and HEAD), so the player can seek while playing."""
        if not f.is_file():
            return self.send_error(404)
        size = f.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        partial = False
        if rng.startswith("bytes="):
            try:
                a, _, b = rng[6:].split(",")[0].partition("-")
                if a.strip():
                    start = int(a)
                    if b.strip():
                        end = min(int(b), size - 1)
                elif b.strip():
                    start = max(0, size - int(b))
                else:
                    raise ValueError("empty range")
                partial = True
            except ValueError:
                start, end = 0, size - 1
            if partial and (start > end or start >= size):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                return self.end_headers()
        if partial:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(f)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(f, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = fh.read(min(1 << 16, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass  # the player cancelled this request to seek elsewhere

    def do_POST(self):
        if not self._guard():
            return
        url = urllib.parse.urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0:
            return self._json({"error": "bad request"}, 400)
        try:
            if url.path == "/api/upload":  # drag & drop: browser gives no path, so stream the bytes
                if n > MAX_UPLOAD:  # refuse before reading anything and drop the connection
                    self.close_connection = True
                    return self._json({"error": T("too_big")}, 413)
                name = Path(urllib.parse.parse_qs(url.query).get("name", ["file"])[0]).name or "file"
                inbox = WORK / "inbox"
                inbox.mkdir(parents=True, exist_ok=True)
                dst = inbox / name
                k = 1
                while dst.exists():  # never overwrite an earlier upload with the same name
                    dst = inbox / f"{Path(name).stem}-{k}{Path(name).suffix}"
                    k += 1
                left = n
                with open(dst, "wb") as f:
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                if left > 0:  # connection dropped: do not keep a truncated recording
                    dst.unlink(missing_ok=True)
                    return self._json({"error": "incomplete upload"}, 400)
                out_dir().mkdir(parents=True, exist_ok=True)
                LOG.info("ACTION upload: %s (%.1f MB)", dst.name, dst.stat().st_size / 2**20)
                add_input(dst)
                return self._json({"path": str(dst), "output": str(out_dir() / engine.default_output(dst).name)})
            body = json.loads(self.rfile.read(n) or b"{}")
            if url.path == "/api/ping":
                LAST_PING[0] = time.time()
                return self._json({"ok": True})
            if url.path == "/api/pick":
                LOG.info("ACTION pick files")
                paths = pick_file_dialog()
                LOG.info("Files picked: %d", len(paths))
                for p in reversed(paths):
                    add_input(p)
                return self._json({"paths": paths, "path": paths[0] if paths else ""})
            if url.path == "/api/config":
                for k, v in body.items():
                    if k in CONFIG_KEYS and (k != "lang" or v in ("it", "en")):
                        CONFIG[k] = v
                save_config(CONFIG)
                return self._json({"ok": True, "config": CONFIG, "outdir": str(out_dir())})
            if url.path == "/api/pickfolder":
                LOG.info("ACTION pick output folder")
                path = pick_folder_dialog()
                LOG.info("Output folder %s", "changed" if path else "unchanged (cancelled)")
                if path:
                    CONFIG["outdir"] = path
                    save_config(CONFIG)
                return self._json({"path": path, "outdir": str(out_dir())})
            if url.path == "/api/outputs/delete":
                f = str(body.get("path", ""))
                if f not in _written() or not any(o.get("file") == f for i in INPUTS for o in outputs_of(i["path"])):
                    return self._json({"error": T("not_allowed")}, 403)
                LOG.info("ACTION delete output (recycle bin) %s", Path(f).name)
                recycle(f)
                return self._json({"ok": True})
            if url.path in ("/api/preview", "/api/full"):
                with LOCK:
                    if JOB["state"] == "running":
                        return self._json({"error": T("busy")}, 409)
                    JOB.update(state="running", msg=T("starting"), progress=0.0, result=None)
                kind = url.path.split("/")[-1]
                paths = [p for p in (body.get("paths") or []) if p]
                if kind == "full" and len(paths) > 1:
                    threading.Thread(target=run_queue, args=(kind, body, paths), daemon=True).start()
                else:
                    if paths:
                        body = dict(body, path=paths[0])
                    QUEUE["n"] = 0
                    threading.Thread(target=run_job, args=(kind, body), daemon=True).start()
                return self._json({"ok": True})
            if url.path == "/api/stop":
                QUEUE["stop"] = True
                LOG.info("ACTION stop queue after the current file")
                return self._json({"ok": True})
            if url.path == "/api/openlog":
                LOG.info("ACTION open log")
                os.startfile(str(LOGFILE))
                return self._json({"ok": True})
            if url.path == "/api/openfolder":
                p = Path(str(body.get("path", "")))
                listed = any(o.get("file") == str(p) for i in INPUTS for o in outputs_of(i["path"]))
                if listed and p.is_file():  # a listed output: show it selected
                    LOG.info("ACTION open folder (select output)")
                    subprocess.Popen(["explorer", f"/select,{p}"])
                elif p.is_dir() and p.resolve() == out_dir().resolve():  # the configured output folder
                    LOG.info("ACTION open folder (output folder)")
                    subprocess.Popen(["explorer", str(p)])
                else:
                    return self._json({"error": T("not_allowed")}, 403)
                return self._json({"ok": True})
            if url.path == "/api/report":
                # Open the pre-filled issue page and show the log in Explorer for manual attaching.
                LOG.info("ACTION report a problem")
                import webbrowser
                webbrowser.open(report_url())
                subprocess.Popen(["explorer", f"/select,{LOGFILE}"])
                return self._json({"ok": True, "info": system_info(), "logdir": "%APPDATA%\\VoceStudio\\logs"})
            if url.path == "/api/settings/save":
                name = (body.get("name") or "").strip()[:40]
                if not name:
                    return self._json({"error": T("no_name")}, 400)
                d = load_settings()
                d[name] = body["data"]
                save_settings(d)
                LOG.info("ACTION save setting: %s", json.dumps(body["data"]))
                return self._json({"ok": True, "settings": d})
            if url.path == "/api/settings/delete":
                d = load_settings()
                d.pop(body.get("name", ""), None)
                save_settings(d)
                LOG.info("ACTION delete setting")
                return self._json({"ok": True, "settings": d})
            if url.path == "/api/clientlog":
                LOG.info("UI: %s", body.get("msg"))
                return self._json({"ok": True})
        except Exception as e:
            LOG.error("ERROR endpoint %s: %s\n%s", url.path, e, traceback.format_exc())
            return self._json({"error": str(e)}, 500)
        self._json({"error": "not found"}, 404)


class Server(http.server.ThreadingHTTPServer):
    allow_reuse_address = False   # on Windows SO_REUSEADDR would let a second program share our port

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("file", nargs="?")
    a = ap.parse_args()
    if a.file:
        SESSION["preselect"] = str(Path(a.file).resolve())
    load_inputs()
    if a.file:
        add_input(SESSION["preselect"])
    # Fixed default port (saved in the config), so the browser origin and its microphone permission are stable;
    # if it is busy, any free port is used for this run.
    preferred = a.port or int(CONFIG.get("port") or DEFAULT_PORT)
    server = None
    for pp in ((preferred,) if a.port else (preferred, 0)):
        try:
            server = Server(("127.0.0.1", pp), Handler)
            break
        except OSError as e:
            LOG.warning("Port %s not available (%s)", pp, e)
    if server is None:
        raise SystemExit("could not open a local port")
    port = server.server_address[1]
    if not a.port and "port" not in CONFIG:
        CONFIG["port"] = port
        save_config(CONFIG)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/?t={TOKEN}"
    LOG.info("=== VoceStudio %s started on port %s (no_window=%s) ===", engine.VERSION, port, a.no_window)
    LOG.info("GPUs (index, free MiB, %% load): %s -> chosen %s",
             os.environ.get("VOCESTUDIO_GPU_INFO", "?"), os.environ.get("CUDA_VISIBLE_DEVICES", "?"))

    def warm_up():
        # Load the AI models while the user picks a file, so the first preview starts fast.
        # On the very first run this also downloads them from Hugging Face.
        try:
            with LOCK:
                if JOB["state"] == "idle":
                    JOB.update(msg=T("models"))
            dev = engine.pick_device()
            engine._load_models(dev)
            engine.regenerate(engine.np.zeros(engine.SR * 2, dtype=engine.np.float32), dev, None)
            with LOCK:
                JOB["warm"] = "done"
                if JOB["state"] == "idle":
                    JOB.update(msg=T("ready"))
            LOG.info("Model warm-up finished")
        except Exception as e:
            LOG.exception("Model warm-up failed (models will be loaded at the first preview)")
            with LOCK:
                JOB["warm"] = "failed"
                if JOB["state"] == "idle":  # show the reason in the status bar, not only in the log
                    why = T("no_cuda") if "no CUDA device" in str(e) else str(e)
                    JOB.update(state="error", msg=T("warm_failed", err=why), progress=0.0)
    threading.Thread(target=warm_up, daemon=True).start()
    if a.no_window:
        print("PAGE " + url, flush=True)  # only for tests/diagnostics; the token is never written to the log
    if not a.no_window:
        open_app_window(url)
        LAST_PING[0] = time.time()
    while True:
        time.sleep(2)
        # Window closed (no heartbeat for 150 s: hidden pages are throttled) and nothing running: quit.
        if not a.no_window and time.time() - LAST_PING[0] > 150 and JOB["state"] != "running":
            LOG.info("Window closed: exiting")
            break


if __name__ == "__main__":
    main()
