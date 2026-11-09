# VoceStudio installer (Windows PowerShell 5.1 or later, no administrator rights needed).
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# What it does:
#   1. finds Python 3.12 (the pinned packages are built for exactly this version)
#   2. checks for an NVIDIA GPU (nvidia-smi) and warns if there is none or the driver is old
#   3. creates .venv inside this folder, pins pip, then installs
#        a) PyTorch + torchaudio (CUDA 12.8 build) from the official PyTorch index only
#           (requirements-torch.txt), then
#        b) every other package from PyPI only (requirements.txt)
#      both with --require-hashes: pip refuses any file whose SHA-256 differs from the pinned one
#   4. gets ffmpeg: a dated LGPL build of the BtbN FFmpeg-Builds project into .\ffmpeg, after
#      checking its SHA-256 against the checksums BtbN published with that release
#      (falls back to an ffmpeg already on PATH, or prints instructions)
#   5. creates VoceStudio.lnk (a shortcut with the program icon) in this folder
#
# The AI model files (about 1 GB) are NOT downloaded here: the app downloads them from
# Hugging Face the first time it starts.
param([switch]$NoFfmpegDownload)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is much faster without the progress bar
# Keep the system default TLS choice; only make sure TLS 1.2 is also allowed (old PowerShell 5.1 defaults).
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Pinned tools (change together with the notes in THIRD_PARTY_NOTICES.md).
$PipVersion = "26.3"
$TorchIndex = "https://download.pytorch.org/whl/cu128"
$FfBase = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-11-08-12-35/"
$FfZip = "ffmpeg-n9.0.2-48-gd4070a14ce-win64-lgpl-shared-9.0.zip"
$FfSha256 = "642ac7acf4060503cfdf8dfb5791900f8fd768d5a54c27f3efef78293f5f3bbf"

function Say($m)  { Write-Host "[VoceStudio] $m" }
function Warn($m) { Write-Host "[VoceStudio] WARNING: $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[VoceStudio] ERROR: $m" -ForegroundColor Red; exit 1 }

# ---- 1. Python 3.12 ----------------------------------------------------------------------
function Test-Py($exe, $extra) {
    try {
        $v = & $exe @extra -c "import sys;print('%d.%d' % sys.version_info[:2])"
        if ($LASTEXITCODE -ne 0) { return $null }
        if ($v.Trim() -eq "3.12") { return $v.Trim() }
    } catch { }
    return $null
}
$py = $null; $pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Py "py" @("-3.12")) { $py = "py"; $pyArgs = @("-3.12") }
}
if (-not $py -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-Py "python" @()) { $py = "python" }
}
if (-not $py) {
    Fail "Python 3.12 (64-bit) was not found. Install Python 3.12 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this script again. Other Python versions are not supported: the pinned packages are built for 3.12."
}
Say ("Using Python " + (Test-Py $py $pyArgs))

# ---- 2. NVIDIA GPU -----------------------------------------------------------------------
$gpu = $null
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    try { $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | Select-Object -First 1) } catch { }
}
if ($gpu) {
    Say "NVIDIA GPU found: $gpu"
    try {
        $drv = [double](($gpu -split ",")[-1].Trim())
        if ($drv -lt 570) { Warn "NVIDIA driver $drv is older than 570: the CUDA 12.8 build of PyTorch needs driver 570 or newer. Update it from https://www.nvidia.com/drivers." }
    } catch { }
} else {
    Warn "No NVIDIA GPU found (nvidia-smi is missing or reports no card)."
    Warn "VoceStudio supports CUDA (NVIDIA) only: the app will start, but processing a file fails with 'no CUDA device found'."
    Warn "If you do have an NVIDIA card, install the current driver from https://www.nvidia.com/drivers and run this script again."
}

# ---- 3. virtual environment + packages ---------------------------------------------------
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Say "Creating .venv ..."
    & $py @pyArgs -m venv (Join-Path $root ".venv")
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment (python -m venv failed)." }
}
Say "Installing packages (PyTorch with CUDA is a large download, several GB; this can take a while) ..."
& $venvPy -m pip install --disable-pip-version-check "pip==$PipVersion"
if ($LASTEXITCODE -ne 0) { Fail "Could not install pip $PipVersion from PyPI (pip install pip==$PipVersion failed). Check your internet connection or proxy." }
& $venvPy -m pip install --disable-pip-version-check --require-hashes --no-deps --index-url $TorchIndex -r (Join-Path $root "requirements-torch.txt")
if ($LASTEXITCODE -ne 0) { Fail "Installing PyTorch/torchaudio from $TorchIndex failed (requirements-torch.txt). The message above from pip says why: network error, a hash that does not match, or a missing wheel." }
& $venvPy -m pip install --disable-pip-version-check --require-hashes -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "Installing the packages of requirements.txt from PyPI failed. The message above from pip says why: network error, a hash that does not match, or a missing package." }

# ---- 4. ffmpeg (pinned LGPL build, checksum verified) ------------------------------------
$ffDir = Join-Path $root "ffmpeg"
$ffExe = Join-Path $ffDir "bin\ffmpeg.exe"
function Test-Lgpl($exe) {
    $cfg = (& $exe -version) -join "`n"
    return ($cfg -match "configuration:") -and ($cfg -notmatch "--enable-gpl") -and ($cfg -notmatch "--enable-nonfree")
}
if (-not (Test-Path $ffExe) -and -not $NoFfmpegDownload) {
    $tmp = Join-Path $env:TEMP ("vocestudio-ffmpeg-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        Say "Downloading ffmpeg ($FfZip, about 75 MB) ..."
        $zip = Join-Path $tmp "ffmpeg.zip"
        Invoke-WebRequest -Uri ($FfBase + $FfZip) -OutFile $zip -UseBasicParsing
        # The checksum must match BOTH the value pinned in this script and the file BtbN published for that release.
        $actual = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLower()
        $sums = (Invoke-WebRequest -Uri ($FfBase + "checksums.sha256") -UseBasicParsing).Content
        if ($sums -is [byte[]]) { $sums = [Text.Encoding]::ASCII.GetString($sums) }
        $line = ($sums -split "`n" | Where-Object { $_ -match [regex]::Escape($FfZip) } | Select-Object -First 1)
        if (-not $line) { throw "the release checksum file does not list $FfZip" }
        $published = ($line.Trim() -split "\s+")[0].ToLower()
        if ($actual -ne $published -or $actual -ne $FfSha256) { throw "SHA-256 mismatch (downloaded $actual, published $published, pinned $FfSha256): the file was not run" }
        Say "ffmpeg SHA-256 verified: $actual"
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
        if (-not $inner -or -not (Test-Path (Join-Path $inner.FullName "bin\ffmpeg.exe"))) { throw "unexpected archive layout" }
        if (Test-Path $ffDir) { Remove-Item $ffDir -Recurse -Force }
        Move-Item $inner.FullName $ffDir
        if (-not (Test-Lgpl $ffExe)) { Remove-Item $ffDir -Recurse -Force; throw "the downloaded build is not LGPL" }
        Say "ffmpeg installed in $ffDir (LGPL build)."
    } catch {
        Warn ("ffmpeg download or verification failed (" + $_.Exception.Message + ").")
    } finally {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
if (-not (Test-Path $ffExe)) {
    $onPath = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($onPath) {
        Say ("Using the ffmpeg found on PATH: " + $onPath.Source + " (its licence depends on how that build was made).")
    } else {
        Warn "No ffmpeg available. VoceStudio needs it to read audio/video files."
        Warn "Either run this script again with an internet connection, or install ffmpeg yourself"
        Warn "(for example: winget install Gyan.FFmpeg) so that 'ffmpeg' works in a new PowerShell window."
    }
}

# ---- 5. shortcut with the program icon ---------------------------------------------------
try {
    $sh = New-Object -ComObject WScript.Shell
    $lnk = $sh.CreateShortcut((Join-Path $root "VoceStudio.lnk"))
    $lnk.TargetPath = Join-Path $env:WINDIR "System32\wscript.exe"
    $lnk.Arguments = '"' + (Join-Path $root "VoceStudio.vbs") + '"'
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = (Join-Path $root "icon.ico")
    $lnk.Description = "VoceStudio"
    $lnk.Save()
    Say "Shortcut created: VoceStudio.lnk (copy it to your desktop if you like)."
} catch {
    Warn ("Could not create the shortcut (" + $_.Exception.Message + "). Use VoceStudio.vbs directly.")
}

Say "Done. Start the program by double-clicking VoceStudio.lnk or VoceStudio.vbs."
Say "First start: the AI models (about 1 GB) are downloaded from Hugging Face; wait for the status bar to say Ready."
