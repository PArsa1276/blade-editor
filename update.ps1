# Blade Editor update for Windows (small and quick). In the blade-editor folder, after you
# downloaded the new version, run:   powershell -ExecutionPolicy Bypass -File update.ps1
# It only: installs the new Blade code into Blade's own Python, copies the skills and the Chrome
# extension, and writes the Claude settings again. Nothing else is downloaded or installed.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$spy = "$HOME\.blade-editor\venv\Scripts\python.exe"
if (-not (Test-Path $spy)) { Write-Host "Blade Editor is not installed yet. Run install.ps1 first."; exit 1 }
$pv = (& $spy -c "import sys; print('%d.%d' % sys.version_info[:2])")
& $spy -m pip install -q --upgrade ".[captions,subject]"
if ($LASTEXITCODE -ne 0) { Write-Host "The update failed. Send the text above to your assistant."; exit 1 }
& $spy -m blade_editor.server --register | Out-Null
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse -Force "skill\*" "$HOME\.claude\skills\"
Remove-Item -Recurse -Force "$HOME\.blade-editor\chrome-extension" -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force "extension" "$HOME\.blade-editor\chrome-extension"
Write-Host "OK: Blade Editor $(& $spy -m blade_editor.server --version)"
Write-Host "Now: 1) close and open Claude again; 2) in Chrome open chrome://extensions and press the reload arrow on Blade Bridge."
if ($pv -ne "3.12" -and $pv -ne "3.11") {
  Write-Host "Note: Blade's environment uses Python ${pv}. GPU packages need Python 3.12 or 3.11: run install.ps1 once to build it again."
}
