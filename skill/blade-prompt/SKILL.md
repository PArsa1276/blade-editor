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

Model: the user's Flow model is **Omni 1.2 Flash** (`model="omni-1.2-flash"`, the default; Omni 1.1
Flash is `model="omni-1.1-flash"`, 3-10 s):
- clips of 3-15 s in **whole seconds** (8-10 s is a good default for one shot); a clip made from a
  first AND a last frame is at most 10 s; aspect 16:9 or 9:16 only;
- 1.2 makes fewer unwanted cuts than 1.1; for several planned cuts in one clip, stay at about 12 s
  or less (not measured yet beyond that);
- Flow sets the aspect and the number of takes in its Agent settings ("Video generation default":
  16:9 or 9:16, x1-x4), not in the prompt: use the same `aspect` as that setting (ask the user
  if unknown; 9:16 for Reels/TikTok/Shorts) and recommend x1 (x2-x4 make more takes and spend
  more credits; flow_collect downloads all of them);
- with "Confirm before generating: Always", Flow asks before it spends credits: the USER clicks
  that confirmation in Chrome, Blade never does;
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

## Keyframes first (best quality and the same character in every shot)

For any new footage from Flow, make images first, then video:
1. **Reference** (once per character/product/place): `flow_generate_image` with a clear
   description - e.g. "character sheet: the same young man, front and 3/4 view, plain grey
   background" or a clean product shot. Pass the user's own photo/footage as `references` when
   the person or product is real.
2. **Keyframes** per shot: `flow_generate_image(references=[the reference image])` for the first
   frame (and the last frame when the shot must end somewhere exact). Same aspect as the video
   (9:16 or 16:9). Prompt in English: subject + pose/action, framing and lens, setting, light,
   style, aspect. Look at each image (Read it) before going on; remake only what is wrong.
3. **Video**: `flow_generate_video(first_frame=<keyframe>, last_frame=<keyframe>)` with a
   `video_prompt` that describes the MOTION and camera between them.
Flow's image model is the project's "Image generation default" (Nano Banana 2.1 for this user,
who says it costs no credits); the video model spends credits, so the dry-run rule still applies
to videos.

## Start and end frames (clips that join the user's footage)

`flow_generate_video(first_frame=..., last_frame=...)` attaches pictures in Flow and tells the
model to start/end exactly on them. A frame can be an image or `"clip.mp4@12.5"` (the frame at
12.5 s). Use it to:
- continue a shot: first_frame = the LAST frame of the user's shot (`clip.mp4@<its end>`);
- bridge two shots: first_frame = end of shot A, last_frame = start of shot B (a generated
  transition that matches both);
- animate a photo: first_frame = the photo.
With frames, write the prompt about the MOTION and camera between the frames (they already fix
the look). In the dry run check `frames_visible` and the screenshot before asking to spend.

## Remake a reference without footage

The user has a reference video and no footage ("I want one like this"). Ideas from rea-video
(Apache-2.0), built on Blade's measurements:
1. `remake_plan(reference, aspect)`. It measures cuts, crossfades and the camera move of every
   shot, and groups the shots into the fewest Flow clips ("units"): same-scene shots, and short
   montage shots (< 2 s, "Cut to:"), share one clip; each shot is made >= 1.5 s (the middle is
   used); frozen shots are one still image (no credits). Tell the user: N shots -> M Flow clips.
2. For each unit: call its `look_at` and SEE the reference shots. Decide what each shot is
   (filmed / AI video / 3D / graphic or text / screen / still):
   - graphic, text, UI, charts -> `motion_template` / `motion_graphic`, not Flow (exact text);
   - filmed, AI, 3D -> Flow. Write each beat's subject, action, setting, lighting with the
     USER'S topic, keep the measured `camera` words. Never copy the reference's people, faces,
     logos, brands or characters - copy the rhythm, framing and camera, not the content.
3. Recurring person/product: one reference image first (`flow_generate_image`), the same
   `references` in every unit. `continuity` in a unit: its first_frame is the previous clip's
   last frame (`"<clip>@<its length>"`).
4. `video_prompt(beats, style, duration=generate_s, aspect, takes=<unit takes>)` ->
   `flow_generate_video` (dry run, then ask before spending; one unit = one call).
5. `remake_assemble(saved_plan, {"G1": clip, ...}, output, music)`: it finds the real cuts in each
   clip and cuts every shot from its own segment at the reference's exact length. Units in
   `check` did not cut as planned: look at them; regenerate only those.
Music: the user's own (or ask); the reference's music is usually not theirs to reuse.

## 3. Show, then spend

Show the user the brief or the Flow prompt (short), then do one dry run of Flow
(`confirm=false`). Spend credits only after the user says yes.
