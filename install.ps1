# Blade Editor installer for Windows. In the blade-editor folder run:
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

Say "Installing Blade Editor into its own folder ($HOME\.blade-editor\venv)"
py -3 -m venv "$HOME\.blade-editor\venv"
$spy = "$HOME\.blade-editor\venv\Scripts\python.exe"
& $spy -m pip install -q --upgrade pip
& $spy -m pip install -q ".[captions]"
& $spy -c "import blade_editor.server"
if ($LASTEXITCODE -ne 0) { Write-Host "Blade Editor could not be installed. Send the text above to your assistant."; exit 1 }
Write-Host "OK: Blade Editor installed"

Say "Connecting Blade Editor to Claude (app and Claude Code)"
& $spy -m blade_editor.server --register
if ($LASTEXITCODE -ne 0) { Write-Host "Could not write the Claude settings. Quit the Claude app and run this file again."; exit 1 }
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse -Force "skill\blade-edit" "$HOME\.claude\skills\"
Say "Blade Editor is ready. Quit the Claude app (and Claude Code) completely, then open it again."
