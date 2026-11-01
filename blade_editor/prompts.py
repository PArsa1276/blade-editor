"""Detailed, timed prompts for Google Flow video models, built from a shot list.

model="omni-1.1-flash" (Gemini Omni Flash 1.1, default): 3-10 s, 16:9 or 9:16, timecode blocks
"[0-3s]", every block opens with the camera, either one continuous shot ("Single continuous shot.
No scene cuts.") or cuts ("Cut to:") - never both, negatives written as "No ..." sentences (Omni has
no negative field), English text. Sources: Gemini API Omni docs, Runware Omni 1.1 prompting guide.
model="veo": Google's Veo prompt guide: subject, action, scene, visual style, camera
(angle, movement, lens), lighting, temporal pacing, audio in separate sentences, dialogue as
"<who> says: ...", and negative terms as plain nouns (no "no"/"don't").
"""

from __future__ import annotations

import re

FIELDS = ("camera", "subject", "action", "setting", "lighting", "audio")
_NEG_WORDS = re.compile(r"\b(no|not|don't|dont|without|never|avoid)\b", re.I)


MODELS = ("omni-1.1-flash", "veo")


def build(beats: list[dict], style: str, duration: float = 8.0, aspect: str = "16:9",
          subject: str = "", setting: str = "", audio: str = "", negative: str = "",
          continuity: str = "", model: str = "omni-1.1-flash", takes: str = "single") -> dict:
    """beats: [{t0, t1, camera, subject?, action, setting?, lighting?, audio?, dialogue?: [who, line]}]
    in time order. Returns the final prompt and the problems found."""
    if not beats:
        raise ValueError("Give at least one beat: {t0, t1, camera, action, ...}.")
    issues = []
    beats = sorted(beats, key=lambda b: float(b["t0"]))
    if abs(float(beats[0]["t0"])) > 0.01:
        issues.append("The first beat should start at 0s.")
    if abs(float(beats[-1]["t1"]) - duration) > 0.05:
        issues.append(f"The last beat should end at {duration:g}s (the clip length).")
    for a, b in zip(beats, beats[1:]):
        if abs(float(a["t1"]) - float(b["t0"])) > 0.05:
            issues.append(f"Gap or overlap between {a['t1']}s and {b['t0']}s.")
    if len(beats) > max(1, int(duration // 1.5)):
        issues.append("Too many beats for the clip: Veo follows about one change per 1.5-2 s.")

    omni = model.startswith("omni")
    if model not in MODELS:
        raise ValueError(f"Unknown model '{model}'. Use: {', '.join(MODELS)}")
    if takes not in ("single", "cuts"):
        raise ValueError("takes must be 'single' (one continuous shot) or 'cuts' (each beat is a shot).")
    if omni:
        if not 3 <= duration <= 10:
            issues.append("Omni Flash makes 3-10 s clips: set duration in 3..10 (use more clips or "
                          "Flow's extend for longer).")
        if aspect not in ("16:9", "9:16"):
            issues.append("Omni Flash supports only 16:9 and 9:16.")
        if re.search(r"[\u0600-\u06FF]", " ".join(str(v) for b in beats for v in b.values())):
            issues.append("Write the prompt in English (Omni follows English best); keep only dialogue "
                          "in another language if it must be spoken.")
    head = []
    if omni:
        head.append("Single continuous shot. No scene cuts." if takes == "single"
                    else f"A sequence of {len(beats)} shots with hard cuts.")
    head.append(f"{style.strip().rstrip('.')}." if style else "")
    head.append(f"{duration:g} seconds, {aspect}.")
    if subject:
        head.append(f"Subject: {subject.strip().rstrip('.')}.")
    if setting:
        head.append(f"Setting: {setting.strip().rstrip('.')}.")
    if continuity:
        head.append(f"Keep consistent through the whole clip: {continuity.strip().rstrip('.')}.")
    lines = [" ".join(x for x in head if x)]
    for k, b in enumerate(beats):
        missing = [f for f in ("camera", "action") if not b.get(f)]
        if missing:
            issues.append(f"Beat {b['t0']}-{b['t1']}s has no {', '.join(missing)}.")
        if omni:
            stamp = f"[{float(b['t0']):g}-{float(b['t1']):g}s]"
            if takes == "cuts" and k:
                stamp += " Cut to:"
        else:
            stamp = f"[{float(b['t0']):05.2f}-{float(b['t1']):05.2f}s]"
        parts = [stamp]
        for key, label in (("camera", None if omni else "Camera"), ("subject", None), ("action", None),
                           ("setting", None), ("lighting", "Lighting"), ("audio", "Sound")):
            v = str(b.get(key, "")).strip().rstrip(".")
            if v:
                parts.append(f"{label}: {v}." if label else f"{v[0].upper()}{v[1:]}.")
        if b.get("dialogue"):
            d = b["dialogue"]
            who, line = d[0], d[1]
            how = f", {d[2]}" if len(d) > 2 else ""
            parts.append(f'{who} says{how}: "{line}"')
        lines.append(" ".join(parts))
    if audio:
        lines.append(f"Audio: {audio.strip().rstrip('.')}.")
    else:
        issues.append("No overall audio: the model then picks random sound/music. Describe music, "
                      "ambience and each sound effect.")
    if negative:
        items = [x.strip() for x in re.split(r"[,;]", negative) if x.strip()]
        if omni:
            lines.append(" ".join(f"No {re.sub(_NEG_WORDS, '', x).strip()}." for x in items))
        else:
            if _NEG_WORDS.search(negative):
                issues.append("Write the negative prompt as plain things to leave out (e.g. 'text, "
                              "watermark, extra fingers'), without 'no'/'don't'.")
            lines.append(f"Negative prompt: {', '.join(items)}.")
    prompt = "\n".join(lines)
    words = len(prompt.split())
    if words < 80:
        issues.append(f"Only {words} words: add detail (lens, light direction, textures, motion speed).")
    return {"prompt": prompt, "words": words, "issues": issues, "ok": not issues}
