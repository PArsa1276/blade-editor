"""Automatic beat-synced edits that copy the *edit language* of a reference video
(cut rhythm, flashes, shake, zoom punches, colour) onto the user's own footage."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from . import analyze, audio, ff

PRESETS = {
    # cut_every: beats per shot; punch/flash/shake: probability on an accented cut.
    "hype":      {"cut_every": 1, "punch": 0.7, "flash": 0.35, "shake": 0.35, "glitch": 0.1,  "grade": "punchy",      "transition": "cut"},
    "phonk":     {"cut_every": 1, "punch": 0.6, "flash": 0.5,  "shake": 0.6,  "glitch": 0.25, "grade": "high_contrast_bw", "transition": "cut"},
    "cinematic": {"cut_every": 4, "punch": 0.0, "flash": 0.0,  "shake": 0.0,  "glitch": 0.0,  "grade": "teal_orange", "transition": "fade", "slow_zoom": True, "letterbox": True},
    "smooth":    {"cut_every": 2, "punch": 0.2, "flash": 0.1,  "shake": 0.0,  "glitch": 0.0,  "grade": "warm",        "transition": "cut", "slow_zoom": True},
    "glitch":    {"cut_every": 1, "punch": 0.4, "flash": 0.2,  "shake": 0.3,  "glitch": 0.6,  "grade": "cyber",       "transition": "cut"},
    # velocity: shots of 1 beat (in 3 of 4 real velocity edits we measured, the median shot was
    # 0.33-0.57 s). On a downbeat (once per bar) the shot starts slow (optical-flow slow motion) with a short flash and a soft zoom punch, then runs
    # fast; other shots run fast. ramp: slow/fast speeds and the part of the shot that is slow.
    "velocity":  {"cut_every": 1, "punch": 1.0, "flash": 1.0,  "shake": 0.0,  "glitch": 0.0,  "grade": "teal_orange", "transition": "cut",
                  "ramp": {"slow": 0.35, "fast": 2.0, "hold": 0.45}},
}


def color_profile(path: str, samples: int = 12) -> dict:
    """Mean saturation, warmth (R-B), brightness and contrast over a few frames."""
    info = ff.probe(path)
    dur = info["duration"] or 1.0
    vals = []
    for i in range(samples):
        t = dur * (i + 0.5) / samples
        cmd = ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
               "-vf", "scale=64:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        raw = subprocess.run(cmd, capture_output=True).stdout
        if not raw:
            continue
        px = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.float32) / 255
        mx, mn = px.max(axis=1), px.min(axis=1)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
        lum = px @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        vals.append((sat.mean(), (px[:, 0] - px[:, 2]).mean(), lum.mean(), lum.std()))
    if not vals:
        return {}
    s, w, b, c = np.mean(vals, axis=0)
    return {"saturation": round(float(s), 3), "warmth": round(float(w), 3),
            "brightness": round(float(b), 3), "contrast": round(float(c), 3)}


def _guess_grade(cp: dict) -> str:
    if not cp:
        return "none"
    if cp["saturation"] < 0.08:
        return "high_contrast_bw" if cp["contrast"] > 0.25 else "bw"
    if cp["brightness"] < 0.28:
        return "dark_moody"
    if cp["warmth"] > 0.08:
        return "warm"
    if cp["warmth"] < -0.06:
        return "cold"
    if cp["saturation"] > 0.45:
        return "punchy"
    return "teal_orange"


def style_from_reference(ref_path: str) -> dict:
    """Turn a reference video's measured edit language into a style for auto_edit."""
    a = analyze.analyze_video(ref_path)
    s = a["summary"]
    bpm = (a.get("audio") or {}).get("bpm") or 120.0
    beat = 60.0 / bpm
    msl = s["median_shot_length"] or 1.0
    cut_every = int(max(1, min(8, round(msl / beat))))
    cuts = max(1, len(a["cuts"]))
    style = {
        "cut_every": cut_every,
        "punch": round(min(0.9, 0.2 + s["mean_activity"] / 40), 2) if msl < 1.2 else 0.15,
        "flash": round(min(0.8, len(a["flashes"]) / cuts), 2),
        "shake": round(min(0.8, s["shake_share"] * 4), 2),
        "glitch": 0.0,
        "grade": _guess_grade(color_profile(ref_path)),
        "transition": "cut" if msl < 2.5 else "fade",
        "slow_zoom": s["moving_camera_share"] > 0.3,
        "source": {"reference": ref_path, "bpm": bpm, "median_shot_length": msl,
                   "cuts_on_beat_share": s.get("cuts_on_beat_share")},
    }
    return {"style": style, "reference_analysis": a}


def _score_windows(src_analysis: dict, length: float) -> list[tuple[float, float]]:
    """(start, score) for candidate windows that do not cross a cut in the source."""
    per = src_analysis["per_second"]
    dur = src_analysis["file"]["duration"]
    shots = src_analysis["shots"]
    out = []
    for sh in shots:
        if sh["duration"] < length + 0.1:
            continue
        t = sh["start"] + 0.05
        while t + length <= sh["end"] - 0.05 and t + length <= dur:
            secs = per[int(t): int(t + length) + 1] or per[-1:]
            act = float(np.mean([p["activity"] for p in secs]))
            cam = float(np.mean([p["camera_speed"] for p in secs]))
            bright = float(np.mean([p["brightness"] for p in secs]))
            penalty = 4.0 if bright < 25 or bright > 235 else 0.0
            out.append((round(t, 3), act + 0.5 * cam - penalty))
            t += max(0.25, length / 2)
    if not out and dur >= length:
        out.append((max(0.0, (dur - length) / 2), 0.0))
    return out


def _loop_music(music: str, start: float, duration: float, out_path: str) -> tuple[str, float, str]:
    have = ff.probe(music)["duration"] - start
    b = audio.analyze_beats(music, start=start)
    downs = [d - start for d in b["downbeats"] if 1.0 < d - start <= have]
    seg = downs[-1] if downs else have
    reps = int(np.ceil(duration / seg)) + 1
    out = Path(out_path).with_name(Path(out_path).stem + "_music_loop.wav")
    ff.run(["-ss", f"{start:.3f}", "-t", f"{seg:.3f}", "-i", music, "-ac", "2", "-ar", "48000",
            str(out.with_suffix(".seg.wav"))])
    ff.run(["-stream_loop", str(reps - 1), "-i", str(out.with_suffix(".seg.wav")), "-t", f"{duration + 1:.3f}",
            str(out)])
    out.with_suffix(".seg.wav").unlink(missing_ok=True)
    return str(out), 0.0, (f"The music is {have:.1f}s, shorter than {duration:.1f}s: it was repeated every "
                           f"{seg:.2f}s (from a bar end). Tell the user, or ask for a longer song.")


def build_edl(sources: list[str], music: str, out_path: str, style: dict | str = "hype",
              duration: float | None = None, music_start: float = 0.0,
              width: int = 1080, height: int = 1920, fps: int = 30,
              title: str | None = None, seed: int = 7, keep_order: bool = False) -> dict:
    """Build a beat-synced EDL from source clips and a music track."""
    if isinstance(style, str):
        if style not in PRESETS:
            raise ValueError(f"Unknown style '{style}'. Use one of: {', '.join(PRESETS)}")
        style = dict(PRESETS[style])
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    warnings = []
    have = ff.probe(music)["duration"] - music_start
    if duration and duration > have + 0.05:
        # Too short for the requested length: repeat it from a bar end, so the beat grid continues.
        music, music_start, note = _loop_music(music, music_start, duration, out_path)
        warnings.append(note)
    beats_info = audio.analyze_beats(music, start=music_start, duration=duration + 2 if duration else None)
    if not beats_info["has_audio"] or len(beats_info["beats"]) < 4:
        raise ValueError("Could not find a beat in the music.")
    beats = [b - music_start for b in beats_info["beats"]]
    loud = beats_info["loudness_per_second"]
    downbeats = {round(d - music_start, 3) for d in beats_info["downbeats"]}
    strong = {round(o["t"] - music_start, 2) for o in beats_info["onsets"] if o["strength"] > 0.6}

    music_len = ff.probe(music)["duration"] - music_start
    total = min(duration or music_len, music_len)
    # Start the first shot at 0 and cut on the beat grid after that.
    k = max(1, int(style.get("cut_every", 1)))
    ramp = style.get("ramp")
    first = k - 1
    if ramp and downbeats:  # cut on the grid that contains the downbeats (the strong beats)
        first = next((j for j, b in enumerate(beats) if round(b, 3) in downbeats), k - 1) % k
    marks = [0.0] + [b for b in beats[first::k] if 0.2 < b < total - 0.2] + [total]
    # In loud sections, cut twice as often (when the grid is coarse).
    # Only when the track has a clearly louder part (3 dB over the median); else keep the grid.
    if k >= 2 and not ramp and loud and np.percentile(loud, 75) > np.median(loud) + 3:
        q = np.percentile(loud, 75)
        dense = [0.0]
        for a, b in zip(marks[:-1], marks[1:]):
            mid = [x for x in beats if a < x < b]
            sec = int(a)
            if sec < len(loud) and loud[sec] > q and mid:
                dense.append(mid[len(mid) // 2])
            dense.append(b)
        marks = sorted(set(round(m, 3) for m in dense))

    analyses = {s: analyze.analyze_video(s, max_fps=15, include_audio=False) for s in sources}
    used: dict[str, list[tuple[float, float]]] = {s: [] for s in sources}
    clips = []
    order = list(sources)
    prev_src = None
    for i, (a, b) in enumerate(zip(marks[:-1], marks[1:])):
        length = b - a
        if length < 0.08:
            continue
        accent = round(a, 3) in downbeats or (not ramp and round(a, 2) in strong) or i == 0
        pieces = None
        if ramp:  # [output seconds, speed] -> source seconds for each piece
            slow = ramp["hold"] * length if accent else 0.0
            pieces = [[o * sp, sp] for o, sp in ((slow, ramp["slow"]), (length - slow, ramp["fast"])) if o > 0.01]
        need = sum(o for o, _ in pieces) if pieces else length
        src = order[i % len(order)] if keep_order else None
        best = None
        cands = [src] if src else order
        for s in cands:
            wins = _score_windows(analyses[s], need)
            if not wins:
                continue
            # Rank windows inside each source (0..1) so sources compete fairly.
            raw = np.array([w[1] for w in wins])
            ranks = raw.argsort().argsort() / max(1, len(raw) - 1)
            for (t, _), r in zip(wins, ranks):
                overlap = any(t < ue and t + need > us for us, ue in used[s])
                score = (r - (5 if overlap else 0) - 0.35 * len(used[s])
                         - (0.5 if s == prev_src and len(order) > 1 else 0)
                         + float(rng.normal(0, 0.15)))
                if best is None or score > best[2]:
                    best = (s, t, score)
        if best is None:
            raise ValueError(f"No source is long enough for a {need:.2f}s shot.")
        s, t, _ = best
        prev_src = s
        used[s].append((t, t + need))
        fx = []
        if style.get("slow_zoom"):
            z = 1.0 + 0.08 * (1 if i % 2 == 0 else -1)
            fx.append({"type": "zoom", "from": 1.0 if z > 1 else 1.08, "to": z if z > 1 else 1.0})
        if accent and rng.random() < style.get("punch", 0):
            fx.append({"type": "zoom_punch", "at": 0, "dur": min(0.3, length * 0.8), "amount": 0.12 if ramp else 0.18})
        if accent and i > 0 and rng.random() < style.get("flash", 0):
            # velocity: a 3-frame flash; others: up to 0.15 s
            fx.append({"type": "flash", "at": 0, "dur": 3 / fps if ramp else min(0.15, length * 0.5), "amount": 0.85})
        if rng.random() < style.get("shake", 0):
            fx.append({"type": "shake", "at": 0, "dur": min(0.35, length * 0.8), "amount": 22})
        if rng.random() < style.get("glitch", 0):
            fx.append({"type": "glitch", "at": max(0.0, length - 0.15), "dur": 0.12})
        tr = style.get("transition", "cut")
        clip = {"src": s, "in": round(t, 3), "out": round(t + need, 3), "mute": True, "effects": fx}
        if pieces:
            clip["ramp"] = [[round(o, 4), sp] for o, sp in pieces]
        if i > 0 and tr != "cut":
            clip["transition"] = {"type": tr, "dur": min(0.4, length * 0.3)}
            # A crossfade overlaps shots, so lengthen this shot to keep the cut on the beat.
            ext = clip["transition"]["dur"]
            if t + length + ext <= analyses[s]["file"]["duration"]:
                clip["out"] = round(t + length + ext, 3)
        clips.append(clip)

    edl = {
        "output": {"path": out_path, "width": width, "height": height, "fps": fps, "fit": "cover",
                   "grade": style.get("grade")},
        "clips": clips,
        "texts": [],
        "global_effects": [{"type": "letterbox", "amount": 0.12}] if style.get("letterbox") else [],
        "audio": {"music": music, "music_start": music_start, "volume": 1.0, "fade_out": 1.0,
                  "keep_clip_audio": False},
        "sfx": [],
    }
    if title:
        edl["texts"].append({"text": title, "start": 0.05, "end": min(2.5, total), "style": "impact",
                             "pos": "center", "anim": "pop"})
    edl["_meta"] = {"bpm": beats_info["bpm"], "cuts": len(clips), "style": style,
                    "duration": round(total, 3), "warnings": warnings}
    return edl
