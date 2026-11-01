---
name: shamshir-edit
description: Edit videos with the Shamshir MCP server (local, free ffmpeg editor) - beat-synced edits, remixing a reference edit's style onto the user's footage, speed ramps, effects, Persian/Arabic text, karaoke captions, jump cuts, logo/PiP overlays and platform-ready export. Use when the user gives video/music files and asks for an edit, reel, short, TikTok, montage, "edit like this reference", captions or silence removal.
---

# Shamshir video editing

Tools come from the `shamshir` MCP server. Call `capabilities` once per chat for the exact
EDL format and names; do not guess effect, grade or style names.

## Rules that make good edits

1. **Look before you plan.** `probe_media` every input, then `view_frames` on every source
   (12-16 frames) and on a reference (use `every=0.1` on its key 2-3 seconds). Never describe
   footage you have not seen.
2. **Measure the reference.** `analyze_video` + `style_from_reference`. Copy its *language*
   (cut rhythm in beats, flash and shake rate, zoom punches, colour, text timing), not its shots.
3. **Cut on the music.** Get beats with `analyze_music`. Put cuts on beats, the hardest hits
   (zoom_punch, flash, shake, sfx `hit`) on downbeats and strong onsets. Change rhythm in the
   loud part (shorter shots), slow down in quiet parts (speed ramp `[[1,1],[0.6,0.3],[1,2]]`).
4. **Pick the best moments.** Use `analyze_video` shots/activity to choose high-motion, sharp
   windows; do not reuse the same moment twice; alternate sources.
5. **Preview first.** `render_edl` with `preview=true`, `view_frames` on the preview, fix, then
   `preview=false`. Segments are cached: change one clip and only that clip re-renders.
6. **Check.** `quality_check` (no black/frozen/silence issues, about -14 LUFS, peak < -1 dBFS).
   With a reference, `compare_videos` and bring cuts/s, flashes/s and shake close to it.
7. Report the output path and what you could not match. Never claim a check you did not run.

## Recipes

- **Fast beat edit:** `auto_edit(sources, music, output_path, style="hype"|"phonk"|"cinematic"|"smooth"|"glitch"|<reference path>, duration, title)`.
  Then open the saved `edl_path`, improve it (ramps, text, sfx) and `render_edl` again.
- **Talking head:** `speech_segments` -> one clip per `keep` pair (jump cuts), `transcribe` ->
  `make_caption_texts` (karaoke) -> `texts`, `fit="blur"` for 16:9 -> 9:16, `audio.keep_clip_audio=true`.
- **Reference remix:** style_from_reference -> auto_edit with that style -> compare_videos ->
  adjust the EDL until the style table is close.
- **Branding:** `overlays` for a logo (png, width 0.12-0.18, corner x/y) or picture-in-picture.

- **New AI shots (Google Flow):** `flow_status` -> `flow_generate_video(prompt)` (dry run, no
  credits; show the screenshot and ASK the user) -> `flow_generate_video(prompt, confirm=true)`
  -> use the returned file as a clip `src`. Never approve credit dialogs for the user.

## Gotchas

- Clip effect times are relative to the clip; `texts`, `sfx`, `overlays`, `global_effects`
  use output time. A crossfade overlaps two clips by its `dur`.
- Persian/Arabic text: use the bundled styles (Vazirmatn); letter spacing is set to 0
  automatically so letters join.
- `ramp` and `speed` keep the clip audio, time-stretched with pitch kept.
- `stabilize: true` on a shaky clip (crops about 8% at the edges).
- Emoji in `texts` become colour stickers above the text; use `overlays` with `src: "emoji:🔥"`
  to place one anywhere.
- Without Google Flow, Shamshir does not generate new footage. After-Effects motion graphics
  (masks, tracked 3D text, particles) cannot be copied; get close with zoom/shake/flash/
  ramps/overlays/text animations and say what differs.
