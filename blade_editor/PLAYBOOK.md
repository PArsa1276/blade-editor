# Blade edit playbook

How good short-form edits are made, written as rules you can apply with Blade's tools. Use
what serves the user's brief, footage and music; the user's words always win. Read the sections
you need (`edit_playbook(section)`), not all of them.

## hook
- The first 1-2 s decide if people stay. Open on the strongest image, motion or line - never on
  a logo, a slow wide shot or black.
- Hit the first downbeat with something: zoom_punch (0.15-0.25), flash (0.6), a hard cut or a
  text pop.
- Text hooks: 3-6 words, top third of a 9:16 frame, on screen at least 1.2 s.
- "Result first": show the end result (the jump, the finished room, the punchline face), then
  how it happened.

## energy
- Plan an energy curve: intro (calm) -> build (faster) -> drop/peak (fastest, most effects) ->
  outro (release). Effects are spice: if every cut has a flash, none of them hits.
- Contrast makes impact: slow before fast, dark before bright, silence before the drop, B&W
  before colour, wide before close.
- Use `analyze_music`: downbeats mark bars; the loudest onsets mark the drop. Put the best
  shots on the drop.

## rhythm
- Cut on the beat; for the eye, cut 1 frame (about 0.03 s) BEFORE the beat - the new shot then
  "lands" on it.
- Vary shot lengths inside a pattern: 2-2-1-1-2 beats feels alive; 1-1-1-1 for a whole minute
  feels like a slideshow.
- Fast sections: 1/2 to 1 beat per shot. Calm sections: 2-4 beats. Hold the last shot 2+ beats.
- A shot should end when its action ends: cut on movement, not after it stops.

## motion
- Motion continuity: if the camera or subject moves left at the end of shot A, start shot B
  moving left (or use smoothleft / whip_left). Opposite directions jar - use that only on
  purpose (the drop).
- Match cuts: same shape, position or movement across the cut (a ball -> the moon, a door ->
  a door). With `view_frames`, pick in/out points where shapes line up.
- Camera moves (`camera` effect, `camera_preset`) add life to static shots: slow push 1.0 ->
  1.08 for calm, zoom_pulse on beats for energy, sway for dreamy, shake 6-12 px for impacts.
- Never stack two camera moves fighting each other on one shot.

## speed
- Speed ramps: fast (2-3x) into the moment, slow (0.25-0.4x) on the peak, fast out. The slow
  part should land on a beat or hit.
- Slow motion looks real only with new in-between frames: `slowmo: "flow"` (auto in final
  renders for speed <= 0.75). Footage shot at 60/120 fps slows best.
- Do not slow down shaky footage without `stabilize`.
- A freeze frame (ramp piece with speed 0.01 or a tpad hold) + text + boom = a "name tag" moment.

## transitions
- Most cuts should be plain cuts. Use transitions to mark a change (section, place, time).
- Flash/whip/zoom/glitch transitions belong on downbeats; crossfades belong to calm, slow
  music.
- One transition family per edit (e.g. whips + flashes for hype; fades + smooth slides for
  aesthetic). Mixing many kinds looks amateur.

## text
- Readability first: short lines (max 5 words), high contrast (outline/box), safe zone: keep
  away from the bottom 20% and the right edge on TikTok/Reels (UI covers them).
- Time on screen: about 0.3 s per word + 0.5 s, minimum 1 s.
- Animate in on a beat (pop, word_by_word), out on a beat; keep one text style per edit plus one
  accent colour for key words.
- Persian/Arabic: Blade shapes and orders RTL text; keep sentences short and check with
  `view_frames`.

## color
- One look for the whole edit (grade or LUT); mismatched clips break the spell. Fix exposure and
  colour of off clips before adding a look.
- Mood: warm/teal-orange = adventure/summer, cold/dark_moody = tension/night, faded/vintage =
  nostalgia, bw/high_contrast_bw = drama, cyber = tech/gaming, punchy = social/ads.
- Use the look change itself as an effect: B&W -> colour on the drop.

## sound
- Sound is half the edit. Layer: music + whooshes on transitions + hits/booms on impacts +
  risers into drops (`make_sfx`).
- Duck the music under speech; keep speech clear at -14 LUFS total.
- One beat of silence (or a filter-sweep) right before the drop makes the drop huge.
- Use the clip's own sound on key moments (a splash, a laugh, an engine) - it sells realism.

## ending
- End on a strong frame, a text payoff or a loop: make the last frame match the first so the
  video replays seamlessly (more watch time).
- Cut the music on a bar end (Blade loops/cuts at bar ends); fade only for calm edits.

## platform
- TikTok/Reels/Shorts: 9:16, 1080x1920, 7-30 s, hook in 1 s, captions on (most watch muted).
- YouTube: 16:9, slower pacing allowed, title card can be longer.
- Ads: product visible in the first 2 s, benefit in text, call to action at the end.

## mistakes
- Logo or slow intro first. Every cut with an effect. Text too small or under the UI. Music
  ending mid-bar. Slow motion with repeated frames. Shaky footage without stabilize. Clips with
  different colour. Jump cuts in the middle of words. Too many transition types. No sound
  effects.

## checklist
Before the final render, check: hook in 1-2 s; energy curve with a clear peak; cuts on beat
(compare_videos cuts_on_beat_share >= 0.8 for beat edits); one look; one transition family;
text readable and in safe zones; sfx on transitions and impacts; ending on a bar or loop;
quality_check clean (-14 LUFS, no black/frozen frames).
