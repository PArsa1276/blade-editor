# ⚔️ Blade Editor

**A free video editor for AI agents.** Tell Claude (or any MCP client) what edit you want in
normal words. Blade Editor lets the agent *see* your footage, measure the music and the style
of a reference video, cut on the beat, add effects, text and captions, and check the result -
all on your own computer, with ffmpeg. No cloud, no credits, no watermark.

> Install: 🇬🇧 [INSTALL.md](INSTALL.md) · 🇮🇷 [INSTALL_FA.md](INSTALL_FA.md) — Use: 🇬🇧 [short guide](blade_editor/GUIDE.md) · 🇮🇷 [راهنمای کوتاه](GUIDE_FA.md)

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
Complete beginners: follow [INSTALL.md](INSTALL.md) (English) or [INSTALL_FA.md](INSTALL_FA.md)
(Persian), step by step.

## Everything it can do

### 👀 See and measure
| Tool | What it does |
|---|---|
| `view_frames` | Contact sheet of frames with time stamps, returned as an image, so the agent really sees the footage |
| `analyze_video` | Cuts, shots, camera moves (pan/tilt/handheld), shake, flashes, activity per second |
| `analyze_music` | BPM, beats, downbeats, strong hits, loudness per second |
| `style_from_reference` | Turns a reference edit into a style: cut rhythm in beats, zoom punch, flash and shake rate, colour grade |
| `reference_breakdown` | The recipe of a reference edit shot by shot, in few tokens: length, cut on beat, flashes, camera moves with ready keyframes, and which tool rebuilds each part |
| `extract_motion` | The camera move of one shot - movement, **rotation** and **zoom** - as keyframes you can replay on any clip (sway, whip, spin, zoom pulse) |
| `verify_cuts` | Before/after frames of each cut in one image, for a single quick check (no endless re-analysis) |
| `probe_media` | Duration, size, fps, codecs |

### ✂️ Edit
| Tool | What it does |
|---|---|
| `auto_edit` | Beat-synced edit in one call, in a preset style (`hype`, `phonk`, `cinematic`, `smooth`, `glitch`) or in the style of a reference video |
| `render_edl` | Full control with a JSON edit list; preview at half size first; unchanged clips are cached, so changes render fast |
| `speech_segments` | Finds the parts with speech for jump cuts (pause removal) |
| `find_highlights` -> `make_shorts` | **Long video -> several shorts**: scores the whole video (loudness, movement, dense speech, strong opening lines, full sentences), the AI reads the candidates and picks the best ideas, then each becomes a finished 9:16 short: pauses removed, crop that follows the action, hook title, karaoke captions |
| `subject_cutout` + `texts[].behind_subject` | **Subject separation** with a local AI model (U²-Net): **text behind the person/object** (the trendy title look), or cut the subject out - transparent, blurred background, new colour or a new background image/video |
| `edit_playbook` | **Taste guide**: the rules that make edits feel professional (hook, energy curve, rhythm, motion continuity, speed ramps, transitions, text safe zones, colour, sound design, endings, platform specs, common mistakes, final checklist), each mapped to Blade's tools |
| `edl_versions`, `restore_version` | Every render is a numbered version with a note: compare them or go back ("the earlier one was better") - re-rendered fast from cache |
| `edit_ideas`, `learn_edit` | **Ideas library**: 12 proven edit formats (beat-sync flash, velocity, aura, cinematic travel, glitch, UGC hook, before/after, 3D spin, kinetic type, POV, smooth, sport) with structure, rhythm, camera, effects and one "wow" trick each; `learn_edit` turns any edit you like (e.g. a CapCut template preview or a TikTok Creative Center ad) into your own reusable recipe |
| `transcribe` -> `fix_transcript` -> `make_caption_texts` | Captions in 3 steps: Whisper - **your choice of model** (`speech_models`: large-v3-turbo by default, large-v3, medium, small, your own OpenAI Whisper `.pt` file such as large-v3.pt, or a faster-whisper folder; the choice is saved) - writes the text with word times and marks unsure words; **the AI reads and corrects it** (misheard words, names, Persian spelling), times are re-aligned; then karaoke captions that also follow jump cuts |
| `make_sfx` | Generated sound effects: whoosh, hit, riser, click, glitch, boom, swish |
| `camera_preset` | Smooth ready-made camera moves: 360 spin with stops, sway, whip, zoom pulse, tilt swing |

Inside an edit list:
- **Clips:** trim, speed, **speed ramps (with sound)**, **real slow motion with optical-flow in-between frames** (`slowmo`), reverse, **stabilize**, vertical crop that
  can **follow the motion**, blurred-background fit, images and colour cards.
- **Camera:** keyframed moves (`camera` effect): copy a reference shot's sway, whip, rotation and
  zoom, or use a preset - with smooth easing and automatic cover zoom (no black corners).
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
| `flow_setup`, `flow_status`, `flow_generate_video`, `flow_collect` | New AI clips with **Google Flow (Veo)** in **your own Chrome**, with your own login and credits, through the bundled **Blade Bridge** extension (load it once; no settings, no prompts; Blade opens the Flow tab itself). Only that extension can connect to Blade (checked by its fixed ID); it can act only on Flow (`flow.google.com`, `labs.google`). Fallback: `chrome://inspect/#remote-debugging`. Dry run first (no credits); never approves credit dialogs; never solves CAPTCHAs. **Keyframes**: `flow_generate_image` makes still images with Flow's image model (e.g. Nano Banana 2.1), with reference images for the same character/product/place. **Start/end frames**: a clip can start and/or end exactly on an image or on a frame of your own video (`clip.mp4@12.5`), so generated shots join your footage |
| `motion_graphic` | After-Effects-style titles, graphics and **3D turns of your clips** with [Kinetograph](https://github.com/0xS4N4TG/kinetograph), rendered to a **transparent** clip (exact alpha from a black/white double render) and placed on the edit. Templates: `examples/kinetograph-title`, `examples/kinetograph-spin3d` |

### 🧭 Built for agents
- `start_here` and `guide`: on first use the agent asks if you want the guide and gives it to
  you **in your own language**.
- `capabilities`: the full edit-list format and all names, so the agent never guesses.
- Error messages reach the agent with the real reason ("clip 0: file not found: …").
- **Decide first, one complete edit:** before the first render the agent maps every reference
  part to a tool (native, Kinetograph, Flow or not possible), tells you the limits, then makes
  one finished edit - no half versions.
- **No loops:** repeated analysis of the same file is refused by the server, so a doubt costs
  one check, not your whole token budget.
- Four bundled skills, installed together:
  - `blade-edit` - which tool for what, and how to combine them;
  - `blade-spec` - spec-driven workflow (adapted from spec-kit): spec -> plan -> build -> verify;
  - `blade-ponytail` - lean mode: fewest calls, renders and tokens, hard limits;
  - `blade-prompt` - prompt optimizer: short request -> full edit brief, and second-by-second Google Flow (Veo) prompts (`video_prompt` tool).

## Example requests

- "Copy the editing style of `ref.mp4` onto my clips and compare the result with it."
- "Remove the pauses from `talk.mp4`, add word-by-word captions, make it vertical."
- "Slow motion at second 3 of `clip1.mp4`, stabilize `clip2.mp4`, put `logo.png` top right."
- "Make an animated intro title with Kinetograph and put it on the edit."
- "Make an 8-second clip of a cat on the moon with Google Flow and add it to the edit."

## Requirements

- Python 3.10+ and ffmpeg (the installers add them when they are missing).
- Optional: `faster-whisper` for captions and Node.js + Kinetograph for motion graphics - the
  installers add both, and Kinetograph also installs itself on first use (a GPU makes it fast).
  Playwright for Google Flow: `pip install ".[flow]"`.

Manual install:
```bash
pip install ".[captions]"
python -m blade_editor.server --register   # writes the Claude settings files
cp -r skill/* ~/.claude/skills/
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
- Kinetograph is downloaded from npm into `~/.blade-editor/kinetograph` (not bundled); it has its own PolyForm Small Business licence.
