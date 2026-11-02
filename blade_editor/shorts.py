"""Long video -> several shorts: score candidate moments, then build finished vertical edits.

find(): measures loudness and movement per second and (with a transcript) speech density, hooks
(questions, exclamations, numbers) and complete sentences, and returns the best non-overlapping
windows with their text, so the agent can read them and choose. build_edl(): one short as an EDL
(jump cuts, crop that follows the action, hook title, karaoke captions moved onto the cut
timeline).
"""

from __future__ import annotations

import re

import numpy as np

from . import captions, ff, qa, text


def _per_second(path: str, dur: float) -> tuple[np.ndarray, np.ndarray]:
    n = max(1, int(np.ceil(dur)))
    y = ff.read_audio_mono(path, sr=8000)
    loud = np.full(n, -60.0)
    for s in range(min(n, int(np.ceil(len(y) / 8000)))):
        seg = y[s * 8000:(s + 1) * 8000]
        if len(seg):
            loud[s] = 20 * np.log10(max(float(np.sqrt(np.mean(seg ** 2))), 1e-6))
    frames, _ = ff.read_gray_frames(path, width=64, fps=1)
    motion = np.zeros(n)
    if len(frames) > 1:
        d = np.abs(np.diff(frames.astype(np.float32), axis=0)).mean(axis=(1, 2))
        motion[1:1 + min(len(d), n - 1)] = d[:n - 1]
    return loud, motion


def _z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / (x.std() + 1e-6)


def find(path: str, transcript: dict | None = None, count: int = 5, min_len: float = 20,
         max_len: float = 60) -> dict:
    dur = ff.probe(path)["duration"]
    loud, motion = _per_second(path, dur)
    lz, mz = _z(loud), _z(motion)
    if transcript and transcript.get("segments"):
        units = [(s["start"], s["end"], s["text"], len(s.get("words") or s["text"].split()))
                 for s in transcript["segments"]]
    else:  # no transcript: speech/sound blocks, cut into pieces of at most 8 s
        units = []
        for a, b in qa.speech_segments(path)["keep"]:
            t = a
            while t < b - 0.5:
                units.append((t, min(b, t + 8), "", 0))
                t += 8
    rate_all = sum(u[3] for u in units) / max(1e-6, sum(u[1] - u[0] for u in units))
    cands = []
    for i, (a, _, first, _) in enumerate(units):
        words = 0
        for j in range(i, len(units)):
            b, last = units[j][1], units[j][2]
            words += units[j][3]
            length = b - a
            if length > max_len:
                break
            if length < min_len:
                continue
            sl = slice(int(a), max(int(a) + 1, int(np.ceil(b))))
            score = 0.4 * float(lz[sl].mean()) + 0.25 * float(mz[sl].mean())
            why = []
            if rate_all > 0:
                dens = words / length / rate_all - 1
                score += 0.25 * dens
                if dens > 0.15:
                    why.append("fast, dense speech")
            if first and re.search(r"[?!؟]|\d", first):
                score += 0.3
                why.append("strong opening line")
            if last and re.search(r"[.!?؟]\s*$", last.strip()):
                score += 0.1
                why.append("ends on a full sentence")
            if lz[sl].mean() > 0.5:
                why.append("loud/energetic")
            if mz[sl].mean() > 0.5:
                why.append("lots of movement")
            txt = " ".join(u[2] for u in units[i:j + 1]).strip()
            cands.append({"start": round(a, 2), "end": round(b, 2), "seconds": round(length, 1),
                          "score": round(score, 3), "why": why, "text": txt[:400] + ("..." if len(txt) > 400 else "")})
    cands.sort(key=lambda c: c["score"], reverse=True)
    picked: list[dict] = []
    for c in cands:  # best first, no overlaps; offer extra ones so the agent can choose
        if all(c["end"] <= p["start"] or c["start"] >= p["end"] for p in picked):
            picked.append(c)
        if len(picked) >= count * 2:
            break
    return {"duration": round(dur, 2), "with_transcript": bool(transcript), "candidates": picked}


def build_edl(path: str, start: float, end: float, out_path: str, title: str | None = None,
              transcript: dict | None = None, jump_cut: bool = True, captions_on: bool = True,
              width: int = 1080, height: int = 1920, fps: int = 30, caption_style: str = "subtitle") -> dict:
    if end <= start:
        raise ValueError(f"Short {start}-{end}: end must be after start.")
    keep = [[start, end]]
    if jump_cut:
        keep = [[max(a, start), min(b, end)] for a, b in qa.speech_segments(path)["keep"] if b > start and a < end]
        merged: list[list[float]] = []
        for a, b in keep:  # tiny pauses are kept: very short pieces look nervous
            if merged and a - merged[-1][1] < 0.15:
                merged[-1][1] = b
            else:
                merged.append([a, b])
        keep = [[round(a, 3), round(b, 3)] for a, b in merged if b - a > 0.12] or [[start, end]]
    clips = [{"src": path, "in": a, "out": b, "focus": "auto"} for a, b in keep]
    texts: list = []
    if captions_on and transcript and transcript.get("segments"):
        segs = [s for s in transcript["segments"] if s["end"] > start and s["start"] < end]
        texts += text.captions_to_items(captions.remap(segs, keep), caption_style, "lower", True, 4)
    if title:
        texts.append({"text": title, "start": 0, "end": 3.0, "style": "impact", "pos": "upper", "anim": "pop"})
    return {"output": {"path": out_path, "width": width, "height": height, "fps": fps, "fit": "cover"},
            "clips": clips, "texts": texts,
            "audio": {"keep_clip_audio": True, "clip_audio_volume": 1.0}}
