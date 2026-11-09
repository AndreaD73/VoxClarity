# Third-party notices / Componenti di terzi

VoceStudio is released under the MIT licence (see `LICENSE`). It uses the third-party components
below. Each one remains under its own licence; their authors do not endorse VoceStudio.
VoceStudio does not distribute any of them: models are downloaded by your computer from Hugging
Face on first run, packages by `pip` (from PyPI and the PyTorch index), and ffmpeg by `install.ps1`
from its publisher. Versions and file hashes are pinned in `requirements.txt`,
`requirements-torch.txt` and `install.ps1`.

VoceStudio e' distribuito con licenza MIT (vedi `LICENSE`). Usa i componenti di terzi elencati
sotto, ciascuno con la propria licenza. VoceStudio non distribuisce nessuno di essi: i modelli
vengono scaricati dal tuo computer da Hugging Face al primo avvio, i pacchetti da `pip` (PyPI e
indice PyTorch), ffmpeg da `install.ps1` presso chi lo pubblica. Versioni e hash dei file sono
fissati in `requirements.txt`, `requirements-torch.txt` e `install.ps1`.

## Speech enhancement models / Modelli

- **Sidon v0.1**, Copyright (c) 2025 sarulab-speech (Sarulab, University of Tokyo). Code and model
  weights: MIT licence. Downloaded at the pinned revision `b3b02d8bbd55fdbc410e6e46e76ef95ace4fbf52`.
  <https://github.com/sarulab-speech/Sidon> - <https://huggingface.co/sarulab-speech/sidon-v0.1>
  Paper: arXiv:2509.17052. Trained on FLEURS-R and LibriTTS-R (below).
- **w2v-BERT 2.0**, Meta (FAIR), MIT licence (as declared on the model card). Downloaded at the
  pinned revision `da985ba0987f70aaeb84a80f2851cfac8c697a7b`.
  <https://huggingface.co/facebook/w2v-bert-2.0> - used as the encoder inside Sidon and for its
  audio pre-processing configuration.

## Training data credited by the Sidon model / Dati citati

Attribution required by the Creative Commons CC BY 4.0 licence of these datasets (they are not
included in VoceStudio):

- **FLEURS-R**, Min Ma, Yuma Koizumi, Shigeki Karita, Heiga Zen, Jason Riesa, Haruko Ishikawa, Michiel Bacchiani (Google). CC BY 4.0. <https://huggingface.co/datasets/google/fleurs-r>
- **LibriTTS-R**, Yuma Koizumi, Heiga Zen, Shigeki Karita, Yifan Ding, Kohei Yatabe, Nobuyuki Morioka, Michiel Bacchiani, Yu Zhang, Wei Han, Ankur Bapna (Google), derived from LibriTTS / LibriVox recordings. CC BY 4.0. Official source: OpenSLR SLR141 <https://www.openslr.org/141/> (also <https://huggingface.co/datasets/parler-tts/libritts_r_filtered>).
  Licence text: <https://creativecommons.org/licenses/by/4.0/>

## Media / Audio e video

- **FFmpeg**, (c) the FFmpeg developers. The build used is configured with `--enable-version3` and
  without `--enable-gpl` / `--enable-nonfree`, so it is licensed under **LGPL-3.0-or-later**
  (full text: <https://www.gnu.org/licenses/lgpl-3.0.txt>). `install.ps1` downloads, from the
  BtbN FFmpeg-Builds project (<https://github.com/BtbN/FFmpeg-Builds>), the pinned release
  `autobuild-2026-11-08-12-35`, file `ffmpeg-n9.0.2-48-gd4070a14ce-win64-lgpl-shared-9.0.zip`
  (ffmpeg.exe + DLLs, FFmpeg n9.0.2 plus 48 commits, commit `d4070a14ce`), checks its SHA-256
  (`642ac7acf4060503cfdf8dfb5791900f8fd768d5a54c27f3efef78293f5f3bbf`) against both the value pinned
  in the script and the `checksums.sha256` file BtbN published with that release, and refuses a build
  configured with `--enable-gpl` or `--enable-nonfree`. The `ffmpeg` folder is created on your
  computer; **VoceStudio does not distribute the ffmpeg binary.** FFmpeg source code (git tag
  `n9.0.2` and the commit above): <https://ffmpeg.org/download.html>,
  <https://git.ffmpeg.org/ffmpeg.git>; build scripts and releases: the BtbN repository. You may
  replace the DLLs in `ffmpeg\bin` with your own build. VoceStudio runs ffmpeg as a separate program
  and does not link to it.
- **libsndfile**, LGPL 2.1 or later, shipped as a DLL inside the `soundfile` Python wheel
  (python-soundfile, BSD-3-Clause). <https://github.com/libsndfile/libsndfile>

## Python libraries / Librerie Python

Installed by `install.ps1`; exact versions and hashes in `requirements.txt` and
`requirements-torch.txt`. Licences below are the ones the packages declare in their `METADATA`.

| Package | Licence |
|---|---|
| PyTorch 2.11.0+cu128 (<https://pytorch.org>) | `License: BSD-3-Clause` as declared by the package. Its `LICENSE` and `NOTICE` files also carry the notices of bundled third-party code (for example Apache-2.0 with LLVM exception for NVTX, and Intel's terms for the OpenMP runtime). The wheel bundles the **Intel OpenMP runtime** (`libiomp5md.dll`, Intel Corporation, redistributed under Intel's licence terms) and Microsoft Visual C++ runtime DLLs. The CUDA/cuDNN libraries inside the official wheel are covered by NVIDIA's own licence terms (CUDA EULA: <https://docs.nvidia.com/cuda/eula/>; cuDNN: <https://docs.nvidia.com/deeplearning/cudnn/backend/latest/reference/eula.html>); they are downloaded by pip, not redistributed here. |
| torchaudio 2.11.0+cu128 | BSD-style licence, declared as `License :: OSI Approved :: BSD License` (same project as PyTorch; see the `LICENSE` file in the package) |
| NumPy 2.5.4 | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` as declared. The Windows wheel bundles **OpenBLAS** (BSD-3-Clause), the Microsoft Visual C++ runtime (`msvcp140`) and the **GCC runtime library / libgfortran, licensed GPL-3.0-or-later WITH GCC-exception-3.1** (the GCC Runtime Library Exception permits this use in a combined work, with no copyleft effect on VoceStudio). |
| SciPy 1.18.1 | BSD-3-Clause. The Windows wheel bundles OpenBLAS (BSD-3-Clause) and the same GCC runtime library (**GPL-3.0-or-later WITH GCC-exception-3.1**), plus Microsoft Visual C++ runtime DLLs. |
| transformers, huggingface_hub (<https://github.com/huggingface>) | Apache-2.0 |
| pyloudnorm | MIT |
| python-soundfile | BSD-3-Clause |
| Pillow (only to regenerate the icon, optional, not installed) | HPND |
| anyio, h11, filelock, pip | MIT |
| MarkupSafe, idna, click, colorama, Jinja2, networkx, pycparser, fsspec, httpcore2, httpx2, Pygments, mpmath, sympy | BSD-2-Clause or BSD-3-Clause |
| mdurl, markdown-it-py, rich, annotated-doc, PyYAML, truststore, typer, setuptools | MIT |
| cffi | MIT-0 |
| shellingham | ISC |
| packaging | Apache-2.0 or BSD-2-Clause |
| hf-xet, tokenizers, safetensors | Apache-2.0 |
| regex | Apache-2.0 and CNRI-Python |
| tqdm | MPL-2.0 and MIT (MPL-2.0 file-level copyleft; used unmodified, source at <https://github.com/tqdm/tqdm>) |
| typing_extensions | PSF-2.0 |

Every package pinned in `requirements.txt` and `requirements-torch.txt` is covered by the rows
above; the authoritative licence of each is in the `*.dist-info/METADATA` and `LICENSE*` files
inside `.venv\Lib\site-packages` after installation. This file lists licences and links; the full
licence texts are available at the linked project pages and inside each installed package.

## Not affiliated

VoceStudio is an independent project. It is not affiliated with or endorsed by the authors of
Sidon, Meta, Google, NVIDIA, the PyTorch Foundation, Hugging Face, BtbN or the FFmpeg project.
