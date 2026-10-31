"""Quality checks for a finished video."""

from __future__ import annotations

import re

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
    v = info["video"] or {}
    return {"file": info, "black": black, "freeze_starts": freeze, "silence_starts": silence,
            "loudness_lufs": loud, "peak_dbfs": tp, "issues": issues, "ok": not issues,
            "aspect": f"{v.get('width')}x{v.get('height')}"}
