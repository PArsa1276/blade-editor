#!/usr/bin/env bash
# Blade Editor installer for macOS and Linux. Run it from the blade-editor folder: bash install.sh
set -e
cd "$(dirname "$0")"
say() { printf '\n==> %s\n' "$1"; }

say "Checking Python (3.10 or newer)"
PY=$(command -v python3 || true)
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  if command -v brew >/dev/null; then brew install python; PY=$(command -v python3)
  elif command -v apt-get >/dev/null; then sudo apt-get install -y python3 python3-pip python3-venv; PY=$(command -v python3)
  else echo "Please install Python 3.10+ from https://www.python.org/downloads/ and run this again."; exit 1; fi
fi
echo "OK: $("$PY" --version)"

say "Checking ffmpeg"
if ! command -v ffmpeg >/dev/null; then
  if command -v brew >/dev/null; then brew install ffmpeg
  elif command -v apt-get >/dev/null; then sudo apt-get install -y ffmpeg
  else echo "Please install ffmpeg (https://ffmpeg.org/download.html) and run this again."; exit 1; fi
fi
echo "OK: ffmpeg found"

say "Installing Blade Editor into its own folder (~/.blade-editor/venv)"
"$PY" -m venv "$HOME/.blade-editor/venv"
"$HOME/.blade-editor/venv/bin/python" -m pip install -q --upgrade pip
"$HOME/.blade-editor/venv/bin/python" -m pip install -q ".[captions]"
SPY="$HOME/.blade-editor/venv/bin/python"
"$SPY" -c "import blade_editor.server" && echo "OK: Blade Editor installed"

say "Connecting Blade Editor to Claude Code"
if command -v claude >/dev/null; then
  claude mcp remove --scope user blade-editor >/dev/null 2>&1 || true
  claude mcp add --scope user blade-editor -- "$SPY" -m blade_editor.server
  mkdir -p "$HOME/.claude/skills" && cp -R skill/blade-edit "$HOME/.claude/skills/"
  echo "OK: connected"
else
  echo "Claude Code is not installed yet. Install it (see the guide, step 2), then run this file again."
  exit 1
fi

say "Blade Editor is ready. Close Claude Code if it is open, then start it again."
