---
name: blade-prompt
description: Prompt optimizer for Blade Editor - turns a short edit request ("make a hype edit") into a complete edit brief, and writes detailed second-by-second Google Flow (Veo) prompts with the video_prompt tool. Use before any creative Blade Editor edit, and every time a clip is made with Google Flow.
---

# Blade prompt optimizer

Short prompts give average results. Before you edit or generate, expand the user's words into
a precise brief. Do this silently and quickly; show the user the result in 3-6 lines, in their
language, and ask at most 2 questions (only what you cannot measure or guess well).

## 1. Edit brief (before planning an edit)

1. Call `edit_ideas` with the user's request (add words from the footage: "car", "night",
   "dance"...). Pick the best recipe; keep its "wow" trick.
2. Fill this brief from the request, the footage (`view_frames`) and the music (`analyze_music`):
   - Goal and platform: Reels/TikTok/Shorts (9:16) or YouTube (16:9); length in seconds.
   - Hook (first 1-2 s): the strongest shot or line, and how it hits (zoom_punch, flash, text).
   - Structure by music: intro / build / drop / outro with times on beats or downbeats.
   - Rhythm: cut every N beats per section; where the speed ramps land.
   - Camera and effects per section (only Blade names: camera, zoom_punch, shake, flash, glitch,
     rgb_split, strobe, motion_blur, grades...).
   - Text: words, style, animation, times; captions with the 3-step caption flow.
   - Grade, sound effects, loudness (-14 LUFS).
   - Missing shots -> Kinetograph (graphics, 3D turns) or Flow (new footage, section 2).
   - Checks for "done": e.g. cuts on beat >= 0.8, no black frames, length exact.
3. The user's own words always win over the recipe.

## 2. Google Flow prompts: second by second

Never send a one-line prompt. Build every clip with `video_prompt` and send its `prompt` with
`flow_generate_video(direct=false)`.

Model: the user's Flow model is **Omni 1.1 Flash** (`model="omni-1.1-flash"`, the default):
- clips of 3-10 s (8 s is a good default); aspect 16:9 or 9:16 only;
- write the prompt in **English** (translate the user's idea; spoken lines may stay in their language);
- it cuts on its own unless told not to: choose `takes="single"` (one continuous camera move,
  "Single continuous shot. No scene cuts.") or `takes="cuts"` (each beat is a shot, "Cut to:") -
  never mix them;
- each `[0-3s]` block opens with the camera; name each foley sound separately; quote dialogue
  exactly and give the voice (`["the man", "Let's go.", "in a calm deep voice"]`);
- for longer scenes, make several clips (or extend in Flow) and match the end of one to the start
  of the next.
For Veo, pass `model="veo"`.

- Plan the clip as 3-5 beats (one change per 1.5-2 s), covering the whole duration exactly.
- Every beat: **camera** (angle + movement + lens), **action** (what moves, direction, speed,
  physics: hair, cloth, smoke, water), **lighting** (source, direction, colour, time of day).
  Add subject/setting only when they change.
- Say once what must stay the same (`continuity`): face, hair, clothes, product, colours.
- `style`: film stock / camera / grade / genre, e.g. "Cinematic 35mm film, anamorphic, teal-orange
  grade, shallow depth of field, natural film grain".
- `audio`: music style and tempo, ambience, sound effects in time with the actions. Dialogue:
  `dialogue: ["the girl", "We made it."]` (short lines; say the tone in `action`).
- `negative`: things to leave out (Omni gets them as "No ..." sentences, Veo as a negative list): "text, subtitles, watermark, logo, extra fingers,
  deformed hands, blurry face, flicker".
- To fit the edit: match the edit's aspect, grade and motion direction; make the last beat end on
  a movement that the next shot can continue (match cut).

Vocabulary (from Google's Veo guide):
- Angles: eye-level, low-angle, high-angle, bird's-eye, worm's-eye, Dutch angle,
  over-the-shoulder, POV; extreme close-up, close-up, medium, full, wide/establishing.
- Movement: static, pan, tilt, dolly in/out, truck left/right, pedestal, crane up/down,
  aerial/drone, handheld, whip pan, arc/orbit, tracking.
- Lens: 14-24mm wide, 35mm, 50mm, 85mm portrait, telephoto 200mm; shallow/deep depth of field,
  rack focus, lens flare, fisheye, dolly zoom (vertigo).
- Light: golden hour, blue hour, hard noon sun, overcast soft, rim light, backlight, neon,
  practical lamps, volumetric light through haze, candlelight.
- Pacing: slow motion, real time, time-lapse, speed ramp.

Example beat: `{"t0": 0, "t1": 2, "camera": "low-angle 24mm, fast dolly in", "action": "a
skateboarder pops an ollie, wheels spinning, dust kicking up in slow motion", "lighting":
"golden hour backlight, warm rim light on the hair"}`

## 3. Show, then spend

Show the user the brief or the Flow prompt (short), then do one dry run of Flow
(`confirm=false`). Spend credits only after the user says yes.
