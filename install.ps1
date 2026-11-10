# Blade Editor installer for Windows. In the blade-editor folder run:
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Say($t) { Write-Host "`n==> $t" -ForegroundColor Cyan }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User") }

Say "Checking Python (3.12 or 3.11)"
# Python 3.12 (or 3.11) on purpose: `py -3` picks the newest one (3.14), and the GPU packages
# (onnxruntime-gpu, torch, CTranslate2) have no builds for it yet.
function Find-Python {
  $keep = $ErrorActionPreference
  $ErrorActionPreference = "Continue"  # `py` prints to stderr when a version is missing: not an error here
  $found = $null
  foreach ($v in "3.12", "3.11") {
    & py "-$v" -c "import sys" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $found = $v; break }
  }
  $ErrorActionPreference = $keep
  return $found
}
$pv = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $pv = Find-Python }
if (-not $pv) {
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  Refresh-Path
  if (Get-Command py -ErrorAction SilentlyContinue) { $pv = Find-Python }
}
if (-not $pv) { Write-Host "Please install Python 3.12 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH') and run this again."; exit 1 }
Write-Host "OK: $(py "-$pv" --version)"

Say "Checking ffmpeg"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  Refresh-Path
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Host "ffmpeg was installed. Close this window, open a new PowerShell and run this file again."; exit 1 }
Write-Host "OK: ffmpeg found"

Say "Installing Blade Editor into its own folder ($HOME\.blade-editor\venv)"
$spy = "$HOME\.blade-editor\venv\Scripts\python.exe"
$old = ""
if (Test-Path $spy) { $old = (& $spy -c "import sys; print('%d.%d' % sys.version_info[:2])") }
if ($old -and $old -ne $pv) {
  Write-Host "The old environment uses Python ${old}: building it again with Python ${pv}"
  py "-$pv" -m venv --clear "$HOME\.blade-editor\venv"
} else {
  py "-$pv" -m venv "$HOME\.blade-editor\venv"
}
& $spy -m pip install -q --upgrade pip
& $spy -m pip install -q ".[captions,subject]"
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
  # NVIDIA GPU: captions need the CUDA 12 cuBLAS + cuDNN 9 files. Use the ones other programs already
  # have (PyTorch, CUDA Toolkit, cuDNN, conda); download them (about 1 GB) only when none are found.
  & $spy -c "from blade_editor import captions; raise SystemExit(0 if captions.cuda_ready() else 1)"
  if ($LASTEXITCODE -eq 0) {
    Write-Host "NVIDIA GPU found: using the CUDA 12 libraries already on this computer (no download)"
  } else {
    Write-Host "NVIDIA GPU found: installing its CUDA 12 libraries for captions (about 1 GB)"
    & $spy -m pip install -q ".[gpu]"
  }
}
& $spy -c "import blade_editor.server"
if ($LASTEXITCODE -ne 0) { Write-Host "Blade Editor could not be installed. Send the text above to your assistant."; exit 1 }
Write-Host "OK: Blade Editor installed"

Say "Connecting Blade Editor to Claude (app and Claude Code)"
& $spy -m blade_editor.server --register
if ($LASTEXITCODE -ne 0) { Write-Host "Could not write the Claude settings. Quit the Claude app and run this file again."; exit 1 }
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse -Force "skill\*" "$HOME\.claude\skills\"
Remove-Item -Recurse -Force "$HOME\.blade-editor\chrome-extension" -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force "extension" "$HOME\.blade-editor\chrome-extension"
Write-Host "OK: Chrome extension (Blade Bridge) in $HOME\.blade-editor\chrome-extension"
Say "Optional: Node.js + Kinetograph (animated titles and 3D graphics)"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
  Refresh-Path
}
if (Get-Command node -ErrorAction SilentlyContinue) {
  & $spy -c "from blade_editor import motion; motion.ensure_kinetograph()"
  if ($LASTEXITCODE -eq 0) { Write-Host "OK: Kinetograph ready" } else { Write-Host "Kinetograph skipped (it installs itself on first use)" }
  # cmd /c: npm writes notices to stderr, which Windows PowerShell with "Stop" treats as a fatal error.
  cmd /c "npx -y skills add 0xS4N4TG/kinetograph -g -a claude-code -y >nul 2>&1"
  if ($LASTEXITCODE -eq 0) { Write-Host "OK: Kinetograph skill" } else { Write-Host "Kinetograph skill skipped" }
} else { Write-Host "Node.js not installed: Kinetograph is skipped (everything else works)." }

Say "Blade Editor is ready. Quit the Claude app (and Claude Code) completely, then open it again."
