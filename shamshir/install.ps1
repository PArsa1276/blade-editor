# Shamshir installer for Windows. In the shamshir folder run:
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Say($t) { Write-Host "`n==> $t" -ForegroundColor Cyan }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User") }

Say "Checking Python (3.10 or newer)"
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  Refresh-Path
}
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))"
if ($LASTEXITCODE -ne 0) { Write-Host "Please install Python 3.12 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH') and run this again."; exit 1 }
Write-Host "OK: $(py -3 --version)"

Say "Checking ffmpeg"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  Refresh-Path
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Host "ffmpeg was installed. Close this window, open a new PowerShell and run this file again."; exit 1 }
Write-Host "OK: ffmpeg found"

Say "Installing Shamshir into its own folder ($HOME\.shamshir\venv)"
py -3 -m venv "$HOME\.shamshir\venv"
$spy = "$HOME\.shamshir\venv\Scripts\python.exe"
& $spy -m pip install -q --upgrade pip
& $spy -m pip install -q ".[captions]"
& $spy -c "import shamshir.server"
if ($LASTEXITCODE -ne 0) { Write-Host "Shamshir could not be installed. Send the text above to your assistant."; exit 1 }
Write-Host "OK: Shamshir installed"

Say "Connecting Shamshir to Claude Code"
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { Write-Host "Claude Code is not installed yet. Install it (see the guide, step 2), then run this file again."; exit 1 }
claude mcp remove --scope user shamshir 2>$null | Out-Null
claude mcp add --scope user shamshir -- "$spy" -m shamshir.server
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse -Force "skill\shamshir-edit" "$HOME\.claude\skills\"
Say "Shamshir is ready. Close Claude Code if it is open, then start it again."
