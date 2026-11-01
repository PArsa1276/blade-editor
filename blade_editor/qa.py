"""Quality checks for a finished video."""

from __future__ import annotations

import re
import subprocess

from . import ff


def check(path: str) -> dict:
    info = ff.probe(path)
    issues: list[str] = []
    log = ff.run(["-i", path, "-vf", "blackdetect=d=0.25:pix_th=0.08,freezedetect=n=0.002:d=1.0",
                  "-af", "silencedetect=n=-45dB:d=1.0,ebur128=peak=true", "-f", "null", "-"])
    black = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)]
    freeze = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", log)]
    silence = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
    peak = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", log)
    loud = float(lufs[-1]) if lufs else None
    tp = float(peak[-1]) if peak else None
    if black:
        issues.append(f"Black frames at {', '.join(f'{a:.2f}-{b:.2f}s' for a, b in black)}.")
    if freeze:
        issues.append(f"Frozen picture starts at {', '.join(f'{t:.2f}s' for t in freeze)}.")
    if not info["audio"]:
        issues.append("The video has no audio stream.")
    elif silence:
        issues.append(f"Silence starts at {', '.join(f'{t:.2f}s' for t in silence)}.")
    if loud is not None and not (-18 <= loud <= -9):
        issues.append(f"Loudness is {loud} LUFS. Social platforms expect about -14 LUFS.")
    if tp is not None and tp > -0.5:
        issues.append(f"Audio peak is {tp} dBFS. It can clip.")
    lens = {}
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    for line in out.splitlines():
        # Rotated phone videos add side-data fields after the duration: "video,7.95,".
        kind, d = (line.split(",") + [""])[:2]
        if kind in ("video", "audio") and d not in ("", "N/A"):
            lens[kind] = float(d)
    if len(lens) == 2 and abs(lens["video"] - lens["audio"]) > 0.2:
        issues.append(f"Video ({lens['video']:.2f}s) and audio ({lens['audio']:.2f}s) lengths differ: "
                      "a clip is shorter than its EDL time (check in/out/ramp against the file).")
    v = info["video"] or {}
    return {"stream_seconds": lens,"file": info, "black": black, "freeze_starts": freeze, "silence_starts": silence,
            "loudness_lufs": loud, "peak_dbfs": tp, "issues": issues, "ok": not issues,
            "aspect": f"{v.get('width')}x{v.get('height')}"}


def speech_segments(path: str, noise_db: float = -35.0, min_silence: float = 0.35,
                    pad: float = 0.08) -> dict:
    """Parts of the file with sound, for jump-cut (silence removal) edits."""
    dur = ff.probe(path)["duration"]
    log = ff.run(["-i", path, "-vn", "-af", f"silencedetect=n={noise_db}dB:d={min_silence}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    keep, t = [], 0.0
    for s, e in zip(starts, ends + [dur] * (len(starts) - len(ends))):
        if s - t > 0.05:
            keep.append([round(max(0.0, t - pad), 3), round(min(dur, s + pad), 3)])
        t = e
    if dur - t > 0.05:
        keep.append([round(max(0.0, t - pad), 3), round(dur, 3)])
    return {"duration": dur, "keep": keep, "kept_seconds": round(sum(b - a for a, b in keep), 3)}
