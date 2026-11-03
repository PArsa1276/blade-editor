---
name: blade-motion
description: Professional motion graphics for Blade Editor edits - animated titles, lower thirds, counters, kinetic words, CTAs and custom Kinetograph graphics as transparent overlays, with motion-design rules (enter-hold-exit, springs, stagger, payoff, safe zones, sound sync, Persian RTL). Use whenever an edit needs a title, name tag, number, call to action, kinetic typography or any designed animated graphic.
---

# Blade motion graphics

Graphics are rendered with Kinetograph (Remotion-style TSX, installs itself) to a transparent
ProRes 4444 clip and placed on the edit as an `overlay`. Fast path: `motion_template`. Custom
design: write TSX and use `motion_graphic`. Ideas in this skill come from studying open motion
skills (MIT: fernandokaraka, haidrrrry, Boriwatopal, Liamrjohnston remotion-motion-graphics
skills), rewritten for Blade.

## 1. Choose the path

| Need | Use |
|---|---|
| Title / hook text, chapter title | `motion_template("title")` |
| Name + role of a speaker | `motion_template("lower_third")` |
| A number (followers, price, %) | `motion_template("counter")` - lands exactly on the value |
| Words on the beat (lyrics, slogan) | `motion_template("kinetic_words", beat=<60/BPM>)` |
| Follow / Subscribe / Buy | `motion_template("cta")` |
| Simple caption or label | EDL `texts` (faster, no Kinetograph) |
| Anything else (logo sting, 3D card, chart, map) | own TSX + `motion_graphic` (rules below) |

Match `width/height/fps` to the edit; `duration` = time on screen (2.5-4 s typical). Put the
result in `overlays`: `{src, start, end, x: 0.5, y: 0.5, width: 1.0}`. Colours: take the accent
from the edit's grade (warm grade -> warm accent); one accent only.

## 2. The rules that make it look professional

1. **Enter -> hold -> exit.** Nothing on screen at frame 0, nothing moving at the last frame.
   Exit is faster than entry (about 0.4 s) and is inside the duration. Biggest amateur tell.
2. **Never linear.** `spring()` for entrances (overshoot + settle; lower damping = more bounce),
   `Easing.out(Easing.cubic)` for moves, `Easing.in` for exits.
3. **Stagger** 3-5 frames (30 fps) between words or elements; same order out.
4. **Idle life** while holding: a slow float (4-8 px), a soft pulse, one light sweep. Felt, not
   seen.
5. **Payoff** on the key moment: a scale pop, one expanding ring, a flash. Then stillness.
   Fast move -> complete stillness -> next move reads expensive; constant motion reads cheap.
6. **One hero colour**, at most one glowing element per frame. No rainbow, no clip-art.
7. **Readability**: hero text 80-160 px at 1080 wide, weight 700+; shadow or plate over busy
   footage; 1 s per short line to read; max 5 words per line.
8. **Safe zones (9:16)**: keep text between 12% and 70% of the height and away from the right
   edge (TikTok/Reels buttons and captions cover the rest).
9. **Sound**: a whoosh/pop starting 2-3 frames BEFORE each hit (`make_sfx` + EDL `sfx`), a
   riser into the payoff. Silent graphics feel unfinished.
10. **Beat**: frames per beat = fps * 60 / BPM (`analyze_music`); land hits on beats.

## 3. Traps (code that looks right and renders wrong)

- `interpolate(frame, ...)` extends past its range by default: a counter goes past its value.
  Always clamp frame-based interpolate. Do NOT clamp an interpolate of a spring value (that
  removes the overshoot).
- A clamped range that starts at a visible value shows from frame 0 (a flash on screen all
  the time). Gate effects: `frame >= start ? ... : 0`.
- `spring()` / hooks inside `.map()`: put them in a child component.
- `transform` on an inline `<span>` does nothing: `display: inline-block`.
- Scaling a panel squashes its text: grow the panel's width or use a mask, not `scaleX`.
- Counting digits jitter: `fontVariantNumeric: "tabular-nums"`.
- Background on the root kills transparency: the Composition must use
  `background={process.env.BLADE_BG ?? "transparent"}` (Blade renders on black and white to
  compute exact alpha).
- Persian/Arabic: Kinetograph's `<Text>` has no right-to-left layout. Use HTML text:
  `<div dir="rtl" style={{fontFamily: "Vazirmatn"}}>` with the font registered from `public/`.

## 4. Check before you deliver

1. Render (`draft: true` first for a quick look), then `view_frames` on the overlay or on the
   edit at: mid-entrance, landing/payoff, mid-hold, mid-exit, last frame (must be empty).
2. Check: text inside the safe zone, nothing clipped, correct RTL word order, number exact,
   alpha clean (no black box).
3. Be the critic, not the builder: list what a viewer would see as cheap (crowded, slow, two
   accents, text under the buttons) and fix it once. At most 2 revision rounds.
