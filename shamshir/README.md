# Shamshir — free local video-editing MCP

Shamshir is an MCP server that lets an AI agent (Claude Code, Claude Desktop, Cursor and
others) edit video on your own computer. It uses ffmpeg. It is free and has no credit limits.

## What it can do

- **See the footage:** `view_frames` gives the agent a contact sheet with time stamps.
- **Read a reference edit:** `analyze_video` finds cuts, shots, camera moves, shake, flashes,
  BPM, beats and downbeats. `style_from_reference` turns this into a style.
- **Auto edit:** `auto_edit` cuts your clips on the music beats in a preset style
  (`hype`, `phonk`, `cinematic`, `smooth`, `glitch`) or in the style of a reference video.
- **Full control:** `render_edl` renders a JSON edit list: trims, speed, reverse, crop/fit
  (cover, contain, blurred background), 11 colour grades, zoom punch, slow zoom, shake, flash,
  strobe, RGB split, glitch, blur, grain, vignette, letterbox, ffmpeg transitions and flash/
  zoom/glitch/whip cuts, music with fades and ducking, generated sound effects.
- **Text:** 7 styles and 8 animations. Persian and Arabic text is shaped correctly
  (the Vazirmatn font is included).
- **Captions:** `transcribe` (faster-whisper) and `make_caption_texts` for karaoke captions.
- **Speed ramps, overlays, LUTs:** velocity edits (`ramp`), logo/PiP overlays, `.cube` LUTs,
  auto subject-following crop (`focus: "auto"`), file size cap (`max_mb`).
- **Jump cuts:** `speech_segments` finds the parts to keep in talking videos.
- **Quality check:** black frames, frozen picture, silence, loudness (−14 LUFS target), peak;
  `compare_videos` puts reference and output side by side with a style table.

Guides: [shamshir/GUIDE.md](shamshir/GUIDE.md) (English, for people; the agent offers it on
first use and translates it into the user's language), [GUIDE_FA.md](GUIDE_FA.md) (Persian) and
[skill/shamshir-edit/SKILL.md](skill/shamshir-edit/SKILL.md) (for AI agents:
`cp -r skill/shamshir-edit ~/.claude/skills/`).

- **Google Flow (optional):** `flow_generate_video` makes AI clips (Veo) with *your own* Google
  account and credits through your logged-in Chrome; the clip then goes into the edit.
  `pip install -e ".[flow]"`, then ask the agent to run `flow_setup`. Shamshir never approves
  credit dialogs and never solves CAPTCHAs. Automating the Flow website may be against
  Google's terms; use it at your own risk. Rewritten from ideas in
  [google-flow-mcp](https://github.com/vynnlee/google-flow-mcp) (MIT).

- **Motion graphics (optional):** `motion_graphic` renders a
  [Kinetograph](https://github.com/0xS4N4TG/kinetograph) TSX composition (titles, kinetic text,
  shapes, Lottie) to a transparent clip for `overlays`. Kinetograph drops alpha in video, so
  Shamshir renders on black and white and computes exact alpha. Kinetograph is a separate install
  under the PolyForm Small Business licence; it needs a GPU (or a software Vulkan driver, slower).

Rendered clip segments are cached, so a small change to the edit list renders fast.

## Install

You need Python 3.10+ and ffmpeg.

```bash
pip install -e .                 # from this folder
pip install -e ".[captions]"     # optional: speech-to-text captions
```

## Connect to an agent

Claude Code:

```bash
claude mcp add --scope user shamshir -- shamshir
```

Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "shamshir": { "command": "shamshir" } } }
```

Projects and intermediate files go to `~/shamshir_projects` (change it with `SHAMSHIR_HOME`).

## Example prompts

- "Analyze `ref.mp4`, then make a 15-second edit of `a.mp4` and `b.mp4` on `song.mp3` in the
  same style. Put the title «شمشیر» at the start."
- "Make a hype vertical edit from the clips in this folder, check it, and fix any problem."

## Tests

```bash
pip install -e ".[test]" && pytest -q
```

## Licence

Code: MIT. Font: Vazirmatn, SIL Open Font License 1.1 (see `licenses/`).

---

## راهنمای کوتاه فارسی

شمشیر یک سرور MCP رایگان برای ادیت ویدیو روی کامپیوتر خودتان است. هوش مصنوعی با آن
ویدیو را می‌بیند، ریتم و سبک یک ویدیوی مرجع را اندازه می‌گیرد، روی بیت موزیک کات می‌زند،
افکت و متن فارسی اضافه می‌کند و خروجی نهایی را بررسی می‌کند.

نصب: `pip install -e .` و بعد `claude mcp add --scope user shamshir -- shamshir`
