#!/usr/bin/env bash
# Claude Code on the web (cloud sessions, e.g. from the phone app): install Blade Editor's Python
# packages so the project's .mcp.json server starts. Does nothing on your own computer.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}"
command -v ffmpeg >/dev/null || { (apt-get update -qq && apt-get install -y -qq ffmpeg) >/dev/null 2>&1 || echo "ffmpeg missing"; }
python3 -m pip install -q --disable-pip-version-check -e ".[captions,subject]" 2>&1 | grep -v "^WARNING" || true
mkdir -p "$HOME/.claude/skills" && cp -R skill/* "$HOME/.claude/skills/"
python3 -c "import blade_editor.server" && echo "Blade Editor ready for this cloud session"
