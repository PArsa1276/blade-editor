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


def _beat_pattern(cuts: list[float], dur: float, beat: float) -> list[int]:
    bounds = [0.0, *cuts, dur]
    return [int(max(1, min(16, round((b - a) / beat)))) for a, b in zip(bounds[:-1], bounds[1:]) if b - a > 0.05]


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
        # How many flashes per second, and how many of them sit on a cut. Many references flash on a
        # beat INSIDE a shot; the old rule only flashed on an accented cut, so it made none at all.
        # Shot lengths of the reference in beats, in order. auto_edit repeats this pattern, so the
        # mix of short and long shots (and the number of cuts) follows the reference, not only the median.
        "pattern": _beat_pattern(a["cuts"], a["file"]["duration"], beat),
        "flash_rate": round(len(a["flashes"]) / max(1.0, a["file"]["duration"]), 3),
        "flash_on_cut": round(sum(1 for f in a["flashes"]
                                  if any(abs(f - c) < 0.1 for c in a["cuts"])) / max(1, len(a["flashes"])), 2),
        "shake": round(min(0.8, s["shake_share"] * 4), 2),
        "glitch": 0.0,
        "grade": _guess_grade(color_profile(ref_path)),
        "transition": "cut" if msl < 2.5 else "fade",
        # auto_edit picks shots so the output's moving-camera share comes close to this. A slow
        # zoom on every shot would add movement on top (measured: +0.1 to +0.36), so it is off.
        "slow_zoom": False,
        "camera_moving": s["moving_camera_share"],
        "source": {"reference": ref_path, "bpm": bpm, "median_shot_length": msl,
                   "cuts_on_beat_share": s.get("cuts_on_beat_share")},
    }
    return {"style": style, "reference_analysis": a}


def _score_windows(src_analysis: dict, length: float,
                   moving: tuple[np.ndarray, float] | None = None) -> list[tuple[float, float, float]]:
    """(start, score, moving) for candidate windows that do not cross a cut in the source.
    moving: share of the window's frames whose camera moves in the OUTPUT crop
    (analyze.output_camera_moving), or 0 when it was not measured."""
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
            mv = 0.0
            if moving is not None:
                fr, mfps = moving
                part = fr[int(t * mfps): int((t + length) * mfps)]
                mv = float(part.mean()) if len(part) else 0.0
            out.append((round(t, 3), act + 0.5 * cam - penalty, mv))
            t += max(0.25, length / 2)
    if not out and dur >= length:
        out.append((max(0.0, (dur - length) / 2), 0.0, 0.0))
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


def _place_flashes(clips: list[dict], starts: list[tuple[float, float]], beats: list[float],
                   style: dict, total: float) -> None:
    """Put the reference's number of flashes on the beat: some on cuts, the rest inside shots."""
    n = int(round(style["flash_rate"] * total))
    if n <= 0:
        return
    on_cut = [(k, 0.0) for k in range(1, len(clips))]
    inside = []
    for b in beats:
        for k, (st, ln) in enumerate(starts):
            if st + 0.12 <= b <= st + ln - 0.12:
                inside.append((k, round(b - st, 3)))
                break
    n_cut = min(len(on_cut), int(round(n * style.get("flash_on_cut", 0.0))))
    n_in = min(len(inside), n - n_cut)
    n_cut = min(len(on_cut), n - n_in)  # too few beats inside shots: use more cuts

    def spread(c: list, m: int) -> list:
        return [c[j] for j in sorted({int(x) for x in np.linspace(0, len(c) - 1, m).round()})] if m > 0 else []

    for k, at in spread(on_cut, n_cut) + spread(inside, n_in):
        clips[k]["effects"].append({"type": "flash", "at": at, "dur": 0.1, "amount": 0.85})


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
    pattern = [int(x) for x in style.get("pattern") or [] if int(x) >= 1]
    if pattern and not ramp:  # a reference's own shot lengths in beats, repeated
        # The first shot starts at 0: count 0 s as a beat when the first beat comes later.
        step = float(np.median(np.diff(beats))) if len(beats) > 1 else 0.5
        marks, j, n = [0.0], (0 if beats[0] < step / 2 else -1), 0
        while True:
            j += pattern[n % len(pattern)]
            n += 1
            if j >= len(beats) or beats[j] >= total - 0.2:
                break
            if beats[j] > 0.2:
                marks.append(beats[j])
        marks.append(total)
    # In loud sections, cut twice as often (when the grid is coarse).
    # Only when the track has a clearly louder part (3 dB over the median); else keep the grid.
    if k >= 2 and not ramp and not pattern and loud and np.percentile(loud, 75) > np.median(loud) + 3:
        q = np.percentile(loud, 75)
        dense = [0.0]
        for a, b in zip(marks[:-1], marks[1:]):
            mid = [x for x in beats if a < x < b]
            sec = int(a)
            if sec < len(loud) and loud[sec] > q and mid:
                dense.append(mid[len(mid) // 2])
            dense.append(b)
        marks = sorted(set(round(m, 3) for m in dense))

    # 30 fps: the cut rules are measured at 30 fps. At 15 fps fast footage moves twice as far
    # per frame and real source cuts were missed, so shots crossed a cut inside the source.
    analyses = {s: analyze.analyze_video(s, max_fps=30, include_audio=False) for s in sources}
    used: dict[str, list[tuple[float, float]]] = {s: [] for s in sources}
    # A reference's share of moving-camera time. The crop to the output frame magnifies the
    # source (a 640x480 source in a 9:16 frame: 2.4x), so a slow drift reads as a moving camera:
    # measure each source in the output's own crop.
    cam_target = style.get("camera_moving")
    motion = ({s: analyze.output_camera_moving(s, width, height) for s in sources}
              if cam_target is not None else {})
    moved = filled = 0.0
    clips = []
    order = list(sources)
    prev_src = None
    starts: list[tuple[float, float]] = []  # output start and length of each clip
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
            wins = _score_windows(analyses[s], need, motion.get(s))
            if not wins:
                continue
            # Rank windows inside each source (0..1) so sources compete fairly.
            raw = np.array([w[1] for w in wins])
            ranks = raw.argsort().argsort() / max(1, len(raw) - 1)
            want = None
            if cam_target is not None:  # the moving share this shot should have to reach the target
                want = float(np.clip((cam_target * (filled + need) - moved) / need, 0.0, 1.0))
            for (t, _, mv), r in zip(wins, ranks):
                overlap = any(t < ue and t + need > us for us, ue in used[s])
                score = (r - (5 if overlap else 0) - 0.35 * len(used[s])
                         - (0.5 if s == prev_src and len(order) > 1 else 0)
                         + float(rng.normal(0, 0.15))
                         - (1.5 * abs(mv - want) if want is not None else 0.0))
                if best is None or score > best[2]:
                    best = (s, t, score, mv)
        if best is None:
            raise ValueError(f"No source is long enough for a {need:.2f}s shot.")
        s, t, _, mv = best
        moved += mv * need
        filled += need
        prev_src = s
        used[s].append((t, t + need))
        fx = []
        if style.get("slow_zoom"):
            z = 1.0 + 0.08 * (1 if i % 2 == 0 else -1)
            fx.append({"type": "zoom", "from": 1.0 if z > 1 else 1.08, "to": z if z > 1 else 1.0})
        if accent and rng.random() < style.get("punch", 0):
            fx.append({"type": "zoom_punch", "at": 0, "dur": min(0.3, length * 0.8), "amount": 0.12 if ramp else 0.18})
        if "flash_rate" not in style and accent and i > 0 and rng.random() < style.get("flash", 0):
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
        starts.append((a, length))

    if cam_target is not None and filled and moved / filled > cam_target + 0.15:
        warnings.append(f"The footage moves more than the reference: about {moved / filled:.0%} of the time the "
                        f"camera moves in this crop, the reference {cam_target:.0%}. Shots were picked as still "
                        f"as possible. For handheld shots, 'stabilize': true on a clip can help; or ask for "
                        f"steadier footage.")
    if style.get("flash_rate") and not ramp:
        _place_flashes(clips, starts, beats, style, total)

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
    if ramp:
        # The numbers cannot tell a still subject (a face the camera follows) from real movement,
        # so the agent checks the slow shots by eye after the render.
        slow, t = [], 0.0
        for k, c in enumerate(clips):
            d = sum(o / sp for o, sp in c["ramp"])
            if len(c["ramp"]) > 1:
                slow.append({"clip": k, "start": round(t, 3), "end": round(t + d, 3), "src": c["src"],
                             "in": c["in"], "source_seconds": round(sum(o for o, _ in c["ramp"]), 3)})
            t += d
        edl["_meta"]["slow_shots"] = slow
        edl["_meta"]["check"] = (
            "Look at each slow shot: view_frames(output, start, end, every=0.1). The slow part must "
            "show something that moves (a jump, a turn, a splash). If the subject is still (a face, "
            "a person standing), change only that clip's 'in' in the saved EDL to a moving moment "
            "(same source or another; in + source_seconds must stay inside one shot of the source). "
            "The slow part is only the first ~0.1 s of source: put 'in' ON the peak of the action, "
            "with the subject inside the crop. Then call render_edl once. One round only.")
    return edl
