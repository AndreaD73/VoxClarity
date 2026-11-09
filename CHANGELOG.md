# Changelog

## 0.4.2 - fixes from the pre-publication review

Security
- The local server now requires a random access token (generated at every start, carried in the window
  URL) on every `/api`, `/file` and `/prev` request, also for HEAD; Host/Origin checks on every request;
  exclusive port binding. "Open folder" only works for listed outputs or the configured output folder.
- Uploads are limited to 4 GB (rejected with 413).
- The microphone permission prompt is no longer bypassed (removed `--use-fake-ui-for-media-stream`). The
  window uses its own browser profile and a fixed local port (47811, free port as fallback), so the
  permission you give once is remembered; the microphone is never opened just to list devices.
- Hugging Face models are downloaded at pinned revisions (Sidon `b3b02d8b...`, w2v-BERT 2.0 `da985ba0...`).
- ffmpeg: pinned dated BtbN release, SHA-256 checked against the pinned value and BtbN's published
  checksums before it is used. pip pinned (26.3); PyTorch installed from its own index only, everything
  else from PyPI only; all files verified with `--require-hashes`; TLS is no longer forced to 1.2 only.

Compatibility
- PyTorch/torchaudio 2.11.0 built for CUDA 12.8 (matching versions): works on RTX 50 (Blackwell) as well as
  Turing, Ampere, Ada. Pascal and older cards are no longer supported. Needs NVIDIA driver 570+.
- Python 3.12 only (the installer no longer accepts 3.10/3.11).
- Models load from a file object, so Windows user names with accented letters work.
- The Documents folder is read from Windows (Known Folder), so moved/OneDrive Documents work.
- If the models cannot be loaded at start (no NVIDIA card, offline first run) the reason is shown in the
  status bar, not only in the log.

Interface and documents
- Audio player: HTTP Range support (seeking while playing) and a seek bar that no longer jumps while dragged.
- Microphone list: "Default microphone" plus a hint until the browser has granted permission.
- About: FFmpeg shown as LGPL-3.0; LibriTTS-R links to OpenSLR SLR141.
- README (IT/EN): CUDA/NVIDIA only, supported GPU generations and measured video memory (about 2.0 GB
  peak on a 30 s block), log content (file names and folder paths), what is written in the install folder,
  no overclaims about the result. THIRD_PARTY_NOTICES: torch/NumPy/SciPy bundled components (OpenBLAS,
  GCC runtime with GCC-exception-3.1, Intel OpenMP, MSVC runtime), Sidon copyright line, ffmpeg source
  pointers; duplicate NumPy row removed.
- Log rotation: the last 10 daily files are kept.
- `install.ps1` creates `VoceStudio.lnk` using `icon.ico`; `docs/screenshots/.gitkeep` added.

## 0.4.1 - first public release

First version published as open source (MIT).

- File mode: drag audio or video files in, get the voice regenerated with Sidon, finished with a
  sound preset (Warm pro, Warm studio, Natural, Podcast, Radio) and five sliders, normalised to a
  loudness target (YouTube, podcast or as recorded). Several files at once (queue).
- Microphone recording inside the window; the take becomes an input.
- 10-second previews and original/processed A/B listening.
- Video files keep their picture; only the audio track is replaced.
- Italian and English interface.
- About panel: version, licences, "Check for updates" (GitHub releases) and "Report a problem"
  (pre-filled GitHub issue).
- `install.ps1` creates a local `.venv`, installs pinned packages and an LGPL ffmpeg build; no
  administrator rights. Settings and logs live in `%APPDATA%\VoceStudio`, work files in
  `%LOCALAPPDATA%\VoceStudio`. The AI models download from Hugging Face on first run.
- The window fits the content and ends just below the Process button; its height is remembered.

(0.4.0 was the last internal build before publication.)
