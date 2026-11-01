# ⚔️ Blade Editor

**A free video editor for AI agents.** Tell Claude (or any MCP client) what edit you want in
normal words. Blade Editor lets the agent *see* your footage, measure the music and the style
of a reference video, cut on the beat, add effects, text and captions, and check the result -
all on your own computer, with ffmpeg. No cloud, no credits, no watermark.

> 🇮🇷 [راهنمای فارسی قدم به قدم](GUIDE_FA.md) · 🇬🇧 [Step-by-step guide](blade_editor/GUIDE.md)

```text
You:    Make a 15-second vertical hype edit of the clips in this folder on song.mp3,
        in the style of ref.mp4. Title "My Trip". Show me a preview first.
Agent:  (looks at every clip, measures ref.mp4: 2.1 cuts/s, flashes on downbeats, teal-orange
         grade) -> renders a preview -> checks it -> final edit.mp4, -14 LUFS, no black frames.
```

## Why

Edit apps need hours of manual work, and AI video services charge credits for every try.
Blade Editor gives an AI agent the tools a human editor uses, so the agent does the work and
you only say what you want, in any language.

## Quick start

1. Install the [Claude app](https://claude.ai/download) or [Claude Code](https://claude.com/claude-code).
2. Download this repository ([ZIP](https://github.com/PArsa1276/blade-editor/archive/refs/heads/main.zip)) and run the installer in its folder:
   - Windows: `powershell -ExecutionPolicy Bypass -File install.ps1`
   - macOS / Linux: `bash install.sh`
3. Open a terminal in a folder with your clips and music, run `claude`, and ask for an edit.

The installer installs Python and ffmpeg when they are missing, puts Blade Editor in its own
environment (`~/.blade-editor/venv`), writes it into the Claude settings (`~/.claude.json` for
Claude Code and the desktop app's Code tab, `claude_desktop_config.json` for Claude Desktop
chats) and installs the editing skill. The `claude` command is not needed. Quit the Claude app
before you run it and open it again after.
Complete beginners: follow the [step-by-step guide](blade_editor/GUIDE.md) (English) or
[GUIDE_FA.md](GUIDE_FA.md) (Persian).

## Everything it can do

### 👀 See and measure
| Tool | What it does |
|---|---|
| `view_frames` | Contact sheet of frames with time stamps, returned as an image, so the agent really sees the footage |
| `analyze_video` | Cuts, shots, camera moves (pan/tilt/handheld), shake, flashes, activity per second |
| `analyze_music` | BPM, beats, downbeats, strong hits, loudness per second |
| `style_from_reference` | Turns a reference edit into a style: cut rhythm in beats, zoom punch, flash and shake rate, colour grade |
| `probe_media` | Duration, size, fps, codecs |

### ✂️ Edit
| Tool | What it does |
|---|---|
| `auto_edit` | Beat-synced edit in one call, in a preset style (`hype`, `phonk`, `cinematic`, `smooth`, `glitch`) or in the style of a reference video |
| `render_edl` | Full control with a JSON edit list; preview at half size first; unchanged clips are cached, so changes render fast |
| `speech_segments` | Finds the parts with speech for jump cuts (pause removal) |
| `transcribe` + `make_caption_texts` | Speech to text with word times, karaoke-style captions |
| `make_sfx` | Generated sound effects: whoosh, hit, riser, click, glitch, boom, swish |

Inside an edit list:
- **Clips:** trim, speed, **speed ramps (with sound)**, reverse, **stabilize**, vertical crop that
  can **follow the motion**, blurred-background fit, images and colour cards.
- **Effects:** zoom punch, slow zoom, shake, flash, strobe, RGB split, glitch, blur,
  motion blur, grain, vignette, letterbox, invert.
- **Colour:** 11 looks (teal-orange, cinematic, B&W, phonk, cyber, vintage…) and your own `.cube` LUTs.
- **Transitions:** flash, zoom, glitch and whip cuts, and every ffmpeg crossfade (fade, slide, wipe, circle, pixelize…).
- **Text:** 7 styles, 8 animations (pop, typewriter, flicker, word by word…), **correct
  Persian and Arabic** (Vazirmatn font included), **colour emoji** 🔥.
- **Overlays:** logo, picture-in-picture, emoji stickers.
- **Audio:** music with fades and ducking, clip audio, sound effects, loudness to −14 LUFS.
- **Export:** any size (9:16, 1:1, 16:9), file size limit for upload.

### ✅ Check
| Tool | What it does |
|---|---|
| `quality_check` | Black frames, frozen picture, silence, loudness (LUFS), peak |
| `compare_videos` | Reference and output side by side, with a style table (cuts/s, shot length, flashes, shake, cuts on beat) |

### ✨ Optional extras
| Tool | What it does |
|---|---|
| `flow_setup`, `flow_status`, `flow_generate_video`, `flow_collect` | New AI clips with **Google Flow (Veo)** through your own logged-in Chrome and your own credits. Dry run first (no credits); never approves credit dialogs; never solves CAPTCHAs |
| `motion_graphic` | After-Effects-style titles and graphics with [Kinetograph](https://github.com/0xS4N4TG/kinetograph), rendered to a **transparent** clip (exact alpha from a black/white double render) and placed on the edit |

### 🧭 Built for agents
- `start_here` and `guide`: on first use the agent asks if you want the guide and gives it to
  you **in your own language**.
- `capabilities`: the full edit-list format and all names, so the agent never guesses.
- Error messages reach the agent with the real reason ("clip 0: file not found: …").
- The `blade-edit` skill teaches the agent the best workflow: look first, measure the
  reference, cut on the music, preview, check.

## Example requests

- "Copy the editing style of `ref.mp4` onto my clips and compare the result with it."
- "Remove the pauses from `talk.mp4`, add word-by-word captions, make it vertical."
- "Slow motion at second 3 of `clip1.mp4`, stabilize `clip2.mp4`, put `logo.png` top right."
- "Make an animated intro title with Kinetograph and put it on the edit."
- "Make an 8-second clip of a cat on the moon with Google Flow and add it to the edit."

## Requirements

- Python 3.10+ and ffmpeg (the installers add them when they are missing).
- Optional: `faster-whisper` for captions (installed by the installers), Playwright for Google
  Flow (`pip install ".[flow]"`), Node.js + Kinetograph for motion graphics (a GPU makes it fast).

Manual install:
```bash
pip install ".[captions]"
python -m blade_editor.server --register   # writes the Claude settings files
cp -r skill/blade-edit ~/.claude/skills/
```
Claude Desktop (`claude_desktop_config.json`): `{ "mcpServers": { "blade-editor": { "command": "blade-editor" } } }`

## Limits

- Blade Editor edits your footage; it makes new scenes only through Google Flow (optional).
- Complex After Effects work (masks, tracked 3D text, particles) is not copied exactly; the edit
  gets close with rhythm, flashes, shake, zooms, colour, speed and text, plus Kinetograph graphics.
- Automating the Google Flow website may be against Google's terms; use that part at your own risk.

## Tests

```bash
pip install ".[test]" && pytest -q
```

## Credits and licence

- Code: MIT (see `LICENSE`).
- Font: Vazirmatn, SIL Open Font License 1.1 (`licenses/`).
- Emoji fallback: Twemoji (CC-BY 4.0), downloaded only when no colour-emoji font is on the computer.
- Ideas for the Google Flow part from [google-flow-mcp](https://github.com/vynnlee/google-flow-mcp) (MIT), rewritten.
- Kinetograph is a separate install under its own PolyForm Small Business licence.
