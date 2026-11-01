"""Edit idea library: proven short-form edit formats as recipes that Blade's tools can build.

The built-in recipes describe well-known formats (beat-sync, velocity, aura edit, travel, ...)
in Blade's own terms. The user's own references can be added with `save_from_reference`; they
live in ~/.blade-editor/recipes and are searched together with the built-in ones.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

USER_DIR = Path(os.environ.get("BLADE_RECIPES", Path.home() / ".blade-editor" / "recipes"))

# Times in beats unless written in seconds. "build" lists the Blade calls in order.
RECIPES: list[dict] = [
    {
        "name": "beat_sync_flash",
        "tags": "beat sync flash hype music montage reel tiktok energy party sport gym car",
        "idea": "Every cut on a beat, a white flash and zoom punch on each downbeat; the drop gets a strobe.",
        "structure": "hook 0-2 beats (best shot + zoom_punch) | build 1-beat cuts | drop: 1/2-beat cuts + strobe | outro: hold 2 beats, fade",
        "cuts": "1 beat; 1/2 beat in the drop", "camera": "zoom_pulse on downbeats",
        "transitions": "flash on downbeats, plain cuts elsewhere", "effects": "zoom_punch, flash, strobe (drop), motion_blur",
        "text": "impact + pop, 2-3 words, on the first downbeat", "grade": "punchy", "sfx": "hit on the drop, whoosh before it",
        "build": ["analyze_music", "auto_edit(style='hype')", "add strobe at the drop in global_effects", "quality_check"],
        "wow": "Cut 1 frame BEFORE the beat - the eye then lands on the new shot exactly on the beat.",
        "avoid": "flashes on every beat (tiring); max 1 per bar",
    },
    {
        "name": "velocity_edit",
        "tags": "velocity speed ramp slow motion fast smooth dance car sport fashion aesthetic",
        "idea": "Each shot runs fast, slows down hard on the beat hit, then speeds up again.",
        "structure": "every shot: fast (2-3x) -> slow (0.3x) on the hit -> fast; 1-2 shots per bar",
        "cuts": "2-4 beats", "camera": "zoom in during the slow part (camera keys)",
        "transitions": "zoom transition or whip between ramps", "effects": "motion_blur on fast parts, zoom_punch on the hit",
        "text": "minimal, small, lower third", "grade": "teal_orange or warm", "sfx": "swish on each speed-up",
        "build": ["analyze_music (hits)", "render_edl with clip ramp [[src_s, speed], ...] so the slow part lands on a hit",
                  "motion_blur on fast parts", "quality_check"],
        "wow": "The slowest frame should be the most beautiful pose/moment - pick it with view_frames.",
        "avoid": "ramps on shaky footage (stabilize first)",
    },
    {
        "name": "aura_edit",
        "tags": "aura farm character anime hero edit phonk slowed dark cool sigma",
        "idea": "Slow, confident shots of one subject with dark grade, glow-like flashes and hard bass hits.",
        "structure": "hook: close-up + text | slow 2-4 beat shots | bass drop: shake + flash + rgb_split | ending: freeze + title",
        "cuts": "2-4 beats; 1 beat at the drop", "camera": "sway or slow zoom, tilt_swing on the drop",
        "transitions": "black flash, glitch on the drop", "effects": "shake, rgb_split, flash(black), grain, vignette",
        "text": "neon or impact, flicker anim", "grade": "dark_moody or high_contrast_bw", "sfx": "boom on the drop",
        "build": ["auto_edit(style='phonk') or render_edl", "camera_preset sway on calm shots", "quality_check"],
        "wow": "One shot in B&W just before the drop, back to colour on the drop.",
        "avoid": "bright happy music",
    },
    {
        "name": "cinematic_travel",
        "tags": "travel trip vacation cinematic vlog nature city wedding story calm emotional",
        "idea": "Wide establishing shots, slow pushes, letterbox and soft crossfades, story order.",
        "structure": "intro: wide shot + title | journey 4-8 beat shots | emotional peak | outro: sunset/last look + fade to black",
        "cuts": "4-8 beats", "camera": "slow zoom 1.0->1.08 on every shot", "transitions": "fade, dissolve, smoothleft",
        "effects": "letterbox, grain(6), vignette", "text": "minimal + fade; place name lower third",
        "grade": "cinematic look or teal_orange", "sfx": "riser into the peak, ambience",
        "build": ["auto_edit(style='cinematic')", "letterbox in global_effects", "texts with place names", "quality_check"],
        "wow": "Match cut: end one shot and start the next with the same shape/motion direction.",
        "avoid": "fast flashes and glitches",
    },
    {
        "name": "glitch_tech",
        "tags": "glitch tech gaming cyber product launch futuristic digital electronic",
        "idea": "Glitch bursts and RGB split on the beats, cyber grade, typed text.",
        "structure": "hook: glitch-in logo | 1-2 beat cuts | glitch transition every bar | outro: logo glitch-out",
        "cuts": "1-2 beats", "camera": "whip_left / whip_right on transitions", "transitions": "glitch, pixelize",
        "effects": "glitch, rgb_split, strobe, invert (1 frame)", "text": "neon + typewriter", "grade": "cyber",
        "sfx": "glitch, click", "build": ["auto_edit(style='glitch')", "make_sfx glitch at transitions", "quality_check"],
        "wow": "A 1-frame invert exactly on the loudest hit.", "avoid": "glitch on every cut",
    },
    {
        "name": "hook_first_ugc",
        "tags": "ugc ad product review talking head hook sales marketing reel business",
        "idea": "Best line or result in the first second, then problem -> product -> proof -> call to action.",
        "structure": "0-1.5s hook (result/bold claim) | problem | product in use | proof/before-after | CTA text",
        "cuts": "jump cuts on speech (speech_segments), 1.5-3 s", "camera": "zoom_punch on key words",
        "transitions": "plain cuts", "effects": "zoom_punch on emphasis, subtle zoom on calm parts",
        "text": "captions (3-step flow) + yellow keywords; CTA in boxed style", "grade": "punchy",
        "sfx": "pop/click on each text", "build": ["speech_segments", "transcribe -> fix_transcript -> make_caption_texts(keep)",
                                                  "render_edl", "quality_check"],
        "wow": "Put the result shot first and the 'how' after - viewers stay to see how.",
        "avoid": "logo intro at the start",
    },
    {
        "name": "before_after_reveal",
        "tags": "before after transformation reveal makeover renovation fitness edit glow up",
        "idea": "Slow 'before', a hard hit, then the 'after' with flash and zoom punch.",
        "structure": "before (calm, desaturated) 4 beats | riser | hit: flash + zoom_punch | after (full colour) | text result",
        "cuts": "on the hit", "camera": "zoom_pulse on the reveal", "transitions": "flash or whip on the reveal",
        "effects": "grade 'bw' or 'faded' on before, punchy on after, flash, zoom_punch",
        "text": "'BEFORE' / 'AFTER' impact + pop", "grade": "faded -> punchy", "sfx": "riser + hit",
        "build": ["analyze_music (strongest hit)", "render_edl", "quality_check"],
        "wow": "Freeze the last 'before' frame for 2 beats while the riser builds.", "avoid": "weak music without a hit",
    },
    {
        "name": "spin_3d_showcase",
        "tags": "3d spin rotate product showcase card turn logo intro shoe phone",
        "idea": "The clip turns like a card (Kinetograph 3D) or spins 360 with holds on the beats.",
        "structure": "hold | spin 90 on beat | hold | spin | ... | final hold + title",
        "cuts": "spin per bar", "camera": "camera_preset spin360_holds (2D) or examples/kinetograph-spin3d (3D)",
        "transitions": "the spin is the transition", "effects": "motion_blur during the spin",
        "text": "Kinetograph title", "grade": "punchy", "sfx": "swish on each turn",
        "build": ["camera_preset('spin360_holds') or motion_graphic(examples/kinetograph-spin3d)", "render_edl"],
        "wow": "Swap to the next clip at 90 degrees, when the card is edge-on - an invisible cut.",
        "avoid": "spins faster than 1 per beat",
    },
    {
        "name": "kinetic_typography",
        "tags": "typography text quote lyrics motivational podcast words kinetic title lyric",
        "idea": "Words appear on the beat, word by word, with zoom and position changes.",
        "structure": "one phrase per bar; key word big; background clips dimmed",
        "cuts": "background every 2-4 beats", "camera": "slow zoom on background",
        "transitions": "fade", "effects": "blur(4) + darker grade on background so text reads",
        "text": "word_by_word / pop; key words yellow; Persian works (RTL)", "grade": "dark_moody",
        "sfx": "click per word (quiet)", "build": ["transcribe or lyrics -> texts on beats", "motion_graphic for designed titles"],
        "wow": "Make the key word 2x bigger and hit it with zoom_punch.", "avoid": "more than 5 words on screen",
    },
    {
        "name": "pov_storytime",
        "tags": "pov story storytime day in life vlog relatable funny",
        "idea": "POV text hook on top, quick clips that follow the story, captions.",
        "structure": "POV text 0-2s | story beats in order | twist/punchline with zoom_punch | loop back to first shot",
        "cuts": "1-2 s", "camera": "handheld feel (light shake 4px)", "transitions": "plain cuts, whip on the twist",
        "effects": "zoom_punch on the twist", "text": "boxed POV text at top + captions",
        "grade": "warm", "sfx": "whoosh on the twist",
        "build": ["render_edl", "texts", "quality_check"],
        "wow": "End on a frame that matches the first frame so the video loops seamlessly.", "avoid": "long intros",
    },
    {
        "name": "smooth_aesthetic",
        "tags": "smooth aesthetic soft lofi chill fashion food coffee calm minimal",
        "idea": "Smooth zoom and slide transitions on the beat, soft colours, slow motion.",
        "structure": "2-beat shots, transition exactly on each beat, slow-mo on the best moments",
        "cuts": "2 beats", "camera": "slow zoom, gentle sway", "transitions": "smoothleft, smoothup, zoom, fade",
        "effects": "grain(5), slight blur pulses", "text": "minimal + fade", "grade": "faded or warm",
        "sfx": "none or soft swish", "build": ["auto_edit(style='smooth')", "quality_check"],
        "wow": "Direction continuity: if a shot moves left, use smoothleft into the next one.", "avoid": "hard flashes",
    },
    {
        "name": "sport_highlight",
        "tags": "sport highlight football goal basketball gym match action skate bike",
        "idea": "Build-up, slow-mo on the key action, freeze frame with name, crowd/hit sound.",
        "structure": "build-up fast cuts | key action in slow-mo (ramp) | freeze + player name | celebration fast cuts",
        "cuts": "1 beat; ramp on the key action", "camera": "zoom_punch on contact, shake on impact",
        "transitions": "flash, whip", "effects": "ramp, freeze (ramp speed 0.01 for a hold), shake, zoom_punch",
        "text": "impact name tag on the freeze", "grade": "punchy or high contrast", "sfx": "boom on impact",
        "build": ["analyze_video (find action)", "render_edl with ramp", "quality_check"],
        "wow": "Drop the music for 1 beat right before the key moment (silence = tension).", "avoid": "slow-mo on every shot",
    },
]


def _words(s: str) -> set[str]:
    return set(re.findall(r"\w+", s.lower()))


def user_recipes() -> list[dict]:
    out = []
    for f in sorted(USER_DIR.glob("*.json")) if USER_DIR.is_dir() else []:
        try:
            out.append(dict(json.loads(f.read_text(encoding="utf-8")), source="user"))
        except (OSError, ValueError):
            pass
    return out


def ideas(request: str, count: int = 3) -> list[dict]:
    """The recipes that fit a request best (user recipes first when they match equally)."""
    want = _words(request)
    pool = user_recipes() + [dict(r, source="built-in") for r in RECIPES]
    scored = []
    for i, r in enumerate(pool):
        hay = _words(" ".join(str(r.get(k, "")) for k in ("name", "tags", "idea", "notes")))
        scored.append((len(want & hay), -i, r))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best = [r for s, _, r in scored if s > 0][:count]
    return best or [dict(r, source="built-in") for r in RECIPES[:count]]


def save(name: str, recipe: dict) -> Path:
    slug = re.sub(r"[^\w-]+", "_", name.strip().lower()).strip("_") or "recipe"
    USER_DIR.mkdir(parents=True, exist_ok=True)
    path = USER_DIR / f"{slug}.json"
    path.write_text(json.dumps(dict(recipe, name=slug), ensure_ascii=False, indent=1), encoding="utf-8")
    return path
