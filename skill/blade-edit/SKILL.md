---
name: blade-edit
description: Edit videos with the Blade Editor MCP server (local, free ffmpeg editor) - beat-synced edits, copying a reference edit's cuts, camera moves (sway, whip, rotation, zoom) and effects onto the user's footage, speed ramps, Persian/Arabic text, captions, jump cuts, overlays, Kinetograph motion graphics and Google Flow clips. Use when the user gives video/music files and asks for an edit, reel, short, montage, "edit like this reference", captions or silence removal.
---

# Blade Editor: how to edit well

Call `start_here` first. Use `blade-spec` for the workflow and `blade-ponytail` for the budget.

## 1. Decide BEFORE the first render (the gate)

Never deliver half versions. Before any render:
1. `reference_breakdown(ref)` (if there is a reference) and `view_frames` on the reference and on
   every source (12 frames each; `every=0.1` only on the 1-2 seconds that matter).
2. Make a table: each reference part -> the tool that rebuilds it (section 2) -> `native`,
   `kinetograph`, `flow` or `not possible`.
3. Tell the user in 3-6 lines what you will rebuild exactly, what only approximately, and what
   not at all. Then do the full edit once, to the standard below. Do not ask for permission to
   try; do not ship a "first try" you already know is weak.

## 2. Which tool for what

| The edit has | Use |
|---|---|
| Cuts on the music | `analyze_music` beats -> clip in/out on beats; or `auto_edit` |
| Same rhythm/feel as a reference, fast | `auto_edit(style=<ref path>)`, then improve its EDL |
| A camera move in a reference shot (sway left-right and back, whip, pan, rotation, zoom) | `reference_breakdown` gives `camera_keys` per shot -> clip effect `{"type":"camera","keys":...}`; for one shot `extract_motion` |
| A move you design (360 spin with stops, sway, whip, zoom pulse, tilt swing) | `camera_preset` -> `camera` effect |
| A FAST SPIN noted by the breakdown | `camera_preset spin360_holds` / `tilt_swing` with the angles you see (measured angles are too low) |
| Long video (podcast, live, vlog) -> several shorts | `transcribe` + `fix_transcript` -> `find_highlights(transcript_path)` -> choose by meaning, write titles -> `make_shorts` |
| Text behind the person/object, cutout, background blur/replace | `texts[].behind_subject: true` (big bold title wider than the subject); `subject_cutout` |
| Animated title, name tag, counter, kinetic words, follow/subscribe CTA | `motion_template` (title, lower_third, counter, kinetic_words, cta) -> `overlays`; rules in the `blade-motion` skill |
| 3D turn, card flip, orbit, perspective, designed titles, shapes, Lottie, kinetic text | `motion_graphic` (Kinetograph; templates in `examples/`) |
| Impact on a beat | effects `zoom_punch` + `flash` + sfx `hit` on downbeats |
| Hand-held jitter | effect `shake` (to add) / clip `stabilize: true` (to remove) |
| Slow motion in one moment | clip `ramp` |
| Colour of the reference | `grade` (name or `.cube`) |
| Glitch / RGB look | effects `glitch`, `rgb_split` |
| Talking video | `speech_segments` -> jump cuts; captions: `transcribe` -> review + `fix_transcript` -> `make_caption_texts(keep=...)` |
| Logo, PiP, emoji sticker | `overlays` |
| A shot the user does not have | `flow_generate_video` (dry run first; ask before confirm=true) |
| Checking | preview `view_frames`, final `quality_check` + `compare_videos` |

Combine: one shot can have `camera` + `zoom_punch` + `flash`; a Kinetograph title goes on top as an
overlay; a Flow clip is just another `src`.

## 3. Trust the measurements (no loops)

- `analyze_video` cuts are measured; do not overrule them from a guess. Doubt a few? Pass the
  low-`cut_confidence` ones to `verify_cuts` ONCE and look. Only then re-run once with
  `sensitivity` 'low' or 'high'. After that the result is final.
- Tools refuse a 3rd analysis of the same file (`limit_reached`): accept the earlier result and
  tell the user any remaining doubt in one line.
- At most 2 revision rounds after the first full render (see blade-ponytail).

## 4. Standard output

9:16 1080x1920 30 fps unless asked; music to -14 LUFS (automatic); `quality_check` without
issues; with a reference, `compare_videos` cuts/s and flashes/s within about 30% of the
reference. Report the path, what matches, and the honest limits.

- Kinetograph needs no setup: `motion_graphic` installs it by itself on first use (needs Node.js).
- Google Flow: through the Blade Bridge extension (loaded once from ~/.blade-editor/chrome-extension);
  Blade opens the Flow tab itself. If `flow_status` says it is not connected, give the user
  `flow_setup` steps.

## Gotchas

- Clip effect times are from the clip start; `texts`, `sfx`, `overlays`, `global_effects` use output time.
- Persian/Arabic text: use the bundled styles; emoji become colour stickers. In Kinetograph use
  `<div dir="rtl">`, never `<Text>`.
- Big rotations zoom in to hide the corners; for 9:16 a 90-degree turn crops a lot - use
  Kinetograph for a full-frame spin if that matters.

## Captions: tool first, then your review

The recogniser (Whisper) makes mistakes, mostly in Persian/Arabic, with accents and noise. You
are the editor of its text:
0. Model: call `speech_models`. If nothing is saved, show the user the choices and the models found
   on their computer and ask which to use; pass it as `model` with `remember=true` (a `.pt` file
   needs `pip install openai-whisper` in Blade's venv - offer to run it).
1. `transcribe(path, language="fa", prompt="<names, brands, topic words>")`. Read `review`: one
   numbered line per segment, unsure words in [[ ]].
2. Correct each wrong line from the meaning and the context: misheard words, names, spelling
   (Persian: ی and ک, half-spaces in می‌شود), punctuation. Keep the spoken words and their order -
   captions must match the voice; do not summarise, translate or "improve" the style. Remove
   lines that are only noise or invented text (""). Call `fix_transcript` once with all fixes;
   word times are re-aligned to your words.
3. If a word is still unclear, ask the user once (list the line numbers) instead of guessing.
4. `make_caption_texts(transcript_path=<fixed file>, keep=<speech_segments keep pairs, when the
   video is jump-cut>)` and put its `texts_file` in the EDL `texts` list.

