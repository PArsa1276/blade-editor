#!/usr/bin/env bash
# Blade Editor update for macOS and Linux (small and quick). From the blade-editor folder, after
# you downloaded the new version: bash update.sh
set -e
cd "$(dirname "$0")"
SPY="$HOME/.blade-editor/venv/bin/python"
[ -x "$SPY" ] || { echo "Blade Editor is not installed yet. Run install.sh first."; exit 1; }
"$SPY" -m pip install -q --upgrade ".[captions,subject]"
"$SPY" -m blade_editor.server --register >/dev/null
mkdir -p "$HOME/.claude/skills" && cp -R skill/* "$HOME/.claude/skills/"
rm -rf "$HOME/.blade-editor/chrome-extension" && cp -R extension "$HOME/.blade-editor/chrome-extension"
echo "OK: Blade Editor $("$SPY" -m blade_editor.server --version)"
echo "Now: 1) close and open Claude again; 2) in Chrome open chrome://extensions and press the reload arrow on Blade Bridge."
