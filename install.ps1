# VoxClarity installer (Windows PowerShell 5.1 or later, no administrator rights needed).
#
#   powershell -ExecutionPolicy Bypass -File install.ps1      (normal users: double-click Installa.bat)
#
# What it does:
#   1. finds Python 3.12 (the pinned packages are built for exactly this version); if it is missing,
#      installs it for the current user only (no administrator rights): first with winget, otherwise
#      the official python.org installer (pinned version, SHA-256 verified)
#   2. checks for an NVIDIA GPU (nvidia-smi) and warns if there is none or the driver is old
#   3. creates .venv inside this folder, pins pip, then installs
#        a) PyTorch + torchaudio (CUDA 12.8 build) from the official PyTorch index only
#           (requirements-torch.txt), then
#        b) every other package from PyPI only (requirements.txt)
#      both with --require-hashes: pip refuses any file whose SHA-256 differs from the pinned one
#   4. gets ffmpeg: a dated LGPL build of the BtbN FFmpeg-Builds project into .\ffmpeg, after
#      checking its SHA-256 against the checksums BtbN published with that release
#      (falls back to an ffmpeg already on PATH, or prints instructions)
#   5. creates VoxClarity.lnk (a shortcut with the program icon) in this folder and on the desktop,
#      then offers to start the app
#
# Switches: -DryRun prints what the Python step would do and exits without changing anything;
# -SimulateNoPython / -SimulateNoWinget (with -DryRun) force those branches for testing;
# -NoPrompt never asks a question (no "start now?" prompt).
#
# The AI model files (about 1 GB) are NOT downloaded here: the app downloads them from
# Hugging Face the first time it starts.
param([switch]$NoFfmpegDownload, [switch]$DryRun, [switch]$SimulateNoPython, [switch]$SimulateNoWinget, [switch]$NoPrompt)

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
# Python 3.12.10 is the last 3.12 release with a binary installer; SHA-256 as published by python.org
# (https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe.spdx.json).
$PyUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
$PySha256 = "67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb"

# Messages: English first, then Italian (the second argument is optional).
function Say($m, $it)  { Write-Host "[VoxClarity] $m"; if ($it) { Write-Host "             $it" } }
function Warn($m, $it) { Write-Host "[VoxClarity] WARNING / ATTENZIONE: $m" -ForegroundColor Yellow; if ($it) { Write-Host "             $it" -ForegroundColor Yellow } }
function Fail($m, $it) { Write-Host "[VoxClarity] ERROR / ERRORE: $m" -ForegroundColor Red; if ($it) { Write-Host "             $it" -ForegroundColor Red }; exit 1 }

# ---- 1. Python 3.12 ----------------------------------------------------------------------
function Test-Py($exe, $extra) {
    try {
        $v = & $exe @extra -c "import sys;print('%d.%d' % sys.version_info[:2])"
        if ($LASTEXITCODE -ne 0) { return $null }
        if ($v.Trim() -eq "3.12") { return $v.Trim() }
    } catch { }
    return $null
}
function Find-Python {
    # Returns @{ Exe; Args } for a working Python 3.12, or $null.
    if (-not $SimulateNoPython) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            if (Test-Py "py" @("-3.12")) { return @{ Exe = "py"; Args = @("-3.12") } }
        }
        if (Get-Command python -ErrorAction SilentlyContinue) {
            if (Test-Py "python" @()) { return @{ Exe = "python"; Args = @() } }
        }
        $perUser = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
        if ((Test-Path $perUser) -and (Test-Py $perUser @())) { return @{ Exe = $perUser; Args = @() } }
    }
    return $null
}
function Install-Python {
    Say "Python 3.12 was not found: installing it for your user only (no administrator rights needed)." "Python 3.12 non trovato: lo installo solo per il tuo utente (non servono i diritti di amministratore)."
    $haveWinget = (-not $SimulateNoWinget) -and [bool](Get-Command winget -ErrorAction SilentlyContinue)
    if ($haveWinget) {
        Say "Step 1/2: installing Python 3.12 with winget ..." "Passo 1/2: installo Python 3.12 con winget ..."
        $wargs = @("install", "--id", "Python.Python.3.12", "-e", "--scope", "user", "--silent", "--accept-package-agreements", "--accept-source-agreements")
        if ($DryRun) { Say ("[dry run] would run: winget " + ($wargs -join " ")); return }
        & winget @wargs
        if ($LASTEXITCODE -eq 0) { return }
        Warn "winget did not finish correctly (code $LASTEXITCODE); trying the official python.org installer." "winget non ha finito correttamente (codice $LASTEXITCODE): provo con l'installer ufficiale di python.org."
    } else {
        Say "winget is not available on this PC: using the official python.org installer." "winget non e' disponibile su questo PC: uso l'installer ufficiale di python.org."
    }
    Say "Step 2/2: downloading Python 3.12.10 from python.org (about 26 MB) ..." "Passo 2/2: scarico Python 3.12.10 da python.org (circa 26 MB) ..."
    $inst = "/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1"
    if ($DryRun) {
        Say "[dry run] would download $PyUrl"
        Say "[dry run] would check SHA-256 = $PySha256, then run: python-3.12.10-amd64.exe $inst"
        return
    }
    $tmp = Join-Path $env:TEMP ("voxclarity-python-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $exe = Join-Path $tmp "python-3.12.10-amd64.exe"
        Invoke-WebRequest -Uri $PyUrl -OutFile $exe -UseBasicParsing
        $actual = (Get-FileHash -Path $exe -Algorithm SHA256).Hash.ToLower()
        if ($actual -ne $PySha256) { Fail "The Python installer SHA-256 does not match (got $actual): it was not run." "Lo SHA-256 dell'installer di Python non corrisponde (ottenuto $actual): non e' stato eseguito." }
        Say "Python installer SHA-256 verified. Installing ..." "SHA-256 dell'installer di Python verificato. Installo ..."
        $p = Start-Process -FilePath $exe -ArgumentList $inst -Wait -PassThru
        if ($p.ExitCode -ne 0) { Fail "The Python installer failed (code $($p.ExitCode))." "L'installazione di Python non e' riuscita (codice $($p.ExitCode))." }
    } finally {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
$found = Find-Python
if (-not $found) {
    Install-Python
    if ($DryRun) {
        Say "[dry run] after the installation it would look for Python 3.12 with 'py -3.12' or in %LOCALAPPDATA%\Programs\Python\Python312, then continue." "[dry run] dopo l'installazione cercherebbe Python 3.12 con 'py -3.12' o in %LOCALAPPDATA%\Programs\Python\Python312, poi proseguirebbe."
        exit 0
    }
    # Pick up the PATH changes the installer made, then look again.
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $found = Find-Python
    if (-not $found) {
        Fail "Python 3.12 was installed but could not be found. Close this window and double-click Installa.bat again." "Python 3.12 e' stato installato ma non lo trovo. Chiudi questa finestra e fai di nuovo doppio clic su Installa.bat."
    }
}
$py = $found.Exe; $pyArgs = $found.Args
if ($DryRun) {
    Say ("[dry run] Python 3.12 already present (" + $py + "); nothing to install. Stopping here.") "[dry run] Python 3.12 gia' presente; niente da installare. Mi fermo qui."
    exit 0
}
Say ("Using Python " + (Test-Py $py $pyArgs)) ("Uso Python " + (Test-Py $py $pyArgs))

# ---- 2. NVIDIA GPU -----------------------------------------------------------------------
$gpu = $null
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    try { $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | Select-Object -First 1) } catch { }
}
if ($gpu) {
    Say "NVIDIA GPU found: $gpu" "Scheda NVIDIA trovata: $gpu"
    try {
        $drv = [double](($gpu -split ",")[-1].Trim())
        if ($drv -lt 570) { Warn "NVIDIA driver $drv is older than 570: the CUDA 12.8 build of PyTorch needs driver 570 or newer. Update it from https://www.nvidia.com/drivers." }
    } catch { }
} else {
    Warn "No NVIDIA GPU found (nvidia-smi is missing or reports no card)."
    Warn "VoxClarity supports CUDA (NVIDIA) only: the app will start, but processing a file fails with 'no CUDA device found'."
    Warn "If you do have an NVIDIA card, install the current driver from https://www.nvidia.com/drivers and run this script again."
}

# ---- 3. virtual environment + packages ---------------------------------------------------
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Say "Creating .venv ..." "Creo l'ambiente .venv ..."
    & $py @pyArgs -m venv (Join-Path $root ".venv")
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment (python -m venv failed)." }
}
Say "Installing packages (PyTorch with CUDA is a large download, several GB; this can take a while) ..." "Installo i pacchetti (PyTorch con CUDA e' un download di diversi GB: puo' richiedere parecchio tempo) ..."
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
    $tmp = Join-Path $env:TEMP ("voxclarity-ffmpeg-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        Say "Downloading ffmpeg (about 75 MB) ..." "Scarico ffmpeg (circa 75 MB) ..."
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
        Warn "No ffmpeg available. VoxClarity needs it to read audio/video files."
        Warn "Either run this script again with an internet connection, or install ffmpeg yourself"
        Warn "(for example: winget install Gyan.FFmpeg) so that 'ffmpeg' works in a new PowerShell window."
    }
}

# ---- 5. shortcuts with the program icon (folder + desktop) ------------------------------
function New-VoxShortcut($path) {
    $sh = New-Object -ComObject WScript.Shell
    $lnk = $sh.CreateShortcut($path)
    $lnk.TargetPath = Join-Path $env:WINDIR "System32\wscript.exe"
    $lnk.Arguments = '"' + (Join-Path $root "VoxClarity.vbs") + '"'
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = (Join-Path $root "icon.ico")
    $lnk.Description = "VoxClarity"
    $lnk.Save()
}
try {
    New-VoxShortcut (Join-Path $root "VoxClarity.lnk")
    Say "Shortcut created in the program folder: VoxClarity.lnk" "Collegamento creato nella cartella del programma: VoxClarity.lnk"
} catch {
    Warn ("Could not create the folder shortcut (" + $_.Exception.Message + "). Use VoxClarity.vbs directly.") "Impossibile creare il collegamento nella cartella: usa direttamente VoxClarity.vbs."
}
try {
    $desk = [Environment]::GetFolderPath("Desktop")
    New-VoxShortcut (Join-Path $desk "VoxClarity.lnk")
    Say "Shortcut created on the desktop: VoxClarity" "Collegamento creato sul desktop: VoxClarity"
} catch {
    Warn ("Could not create the desktop shortcut (" + $_.Exception.Message + ").") "Impossibile creare il collegamento sul desktop."
}

Say "Done. Start the program with the VoxClarity icon on your desktop." "Fatto. Avvia il programma con l'icona VoxClarity sul desktop."
Say "First start: the AI models (about 1 GB) are downloaded from Hugging Face; wait for the status bar to say Ready." "Primo avvio: i modelli AI (circa 1 GB) vengono scaricati da Hugging Face; attendi che la barra di stato dica Pronto."
if (-not $NoPrompt) {
    try {
        $ans = Read-Host "Start VoxClarity now? / Avviare VoxClarity adesso? [Y/S = yes/si, N = no]"
        if ($ans -match '^\s*(y|s)') { Start-Process -FilePath (Join-Path $env:WINDIR "System32\wscript.exe") -ArgumentList ('"' + (Join-Path $root "VoxClarity.vbs") + '"') -WorkingDirectory $root }
    } catch { }
}
