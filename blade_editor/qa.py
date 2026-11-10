"""Quality checks for a finished video."""

from __future__ import annotations

import re
from pathlib import Path
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
                          "-of", "csv=p=0", path], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
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


def snap_cuts(path: str, keep: list, window: float = 0.35, min_silence: float = 0.06, pad: float = 0.04) -> dict:
    """Move every in/out of `keep` [[in, out], ...] to the real silence next to it.

    Whisper's word times are loose (a word runs on to the start of the next one), so a cut on a
    word time can keep the first sound of the next sentence. The boundary comes from the sound
    itself: energy in 10 ms steps; a pause is `min_silence` s below the threshold (between the room
    noise and the speech level). An "in" goes to just before the speech starts, an "out" to just
    after it ends. A boundary with no pause inside `window` s goes to the quietest moment and is
    marked in_silence=false (the cut is inside speech: look for another place)."""
    import numpy as np

    sr, hop = 16000, 160
    y = ff.read_audio_mono(path, sr=sr)
    if len(y) < hop * 4:
        raise ValueError("The file has no audio to find pauses in.")
    n = len(y) // hop
    db = 10 * np.log10(np.maximum((y[: n * hop].reshape(n, hop) ** 2).mean(axis=1), 1e-10))
    floor, speech = float(np.percentile(db, 10)), float(np.percentile(db, 90))
    thr = floor + max(6.0, 0.3 * (speech - floor))
    quiet = db < thr
    step, need = hop / sr, max(1, int(round(min_silence * sr / hop)))
    dur = n * step

    def snap(t: float, side: str) -> dict:
        a, b = max(0, int((t - window) / step)), min(n, int((t + window) / step) + 1)
        runs, k = [], a
        while k < b:
            if quiet[k]:
                j = k
                while j < n and quiet[j]:
                    j += 1
                i = k
                while i > 0 and quiet[i - 1]:
                    i -= 1
                if j - i >= need:
                    runs.append((i * step, j * step))
                k = j
            else:
                k += 1
        if (t <= window and side == "in") or (t >= dur - window and side == "out"):
            runs.append((0.0, 0.0) if side == "in" else (dur, dur))  # the file's own start / end
        if runs:
            r0, r1 = min(runs, key=lambda r: 0.0 if r[0] <= t <= r[1] else min(abs(t - r[0]), abs(t - r[1])))
            new = max(r0, r1 - pad) if side == "in" else min(r1, r0 + pad)
            return {"t": round(float(new), 3), "moved": round(float(new - t), 3), "in_silence": True}
        k = a + int(np.argmin(db[a:b]))
        return {"t": round(k * step, 3), "moved": round(k * step - t, 3), "in_silence": False,
                "level_db": round(float(db[k]), 1)}

    out, notes = [], []
    for i, (a, b) in enumerate(keep):
        sa, sb = snap(float(a), "in"), snap(float(b), "out")
        if sb["t"] - sa["t"] < 0.05:
            sa, sb = {"t": float(a), "moved": 0.0, "in_silence": False}, {"t": float(b), "moved": 0.0, "in_silence": False}
        out.append([sa["t"], sb["t"]])
        for side, r in (("in", sa), ("out", sb)):
            if not r["in_silence"]:
                notes.append(f"keep[{i}] {side} at {r['t']}s is inside speech (no pause within {window}s).")
    return {"keep": out, "moved": [[round(o[0] - float(k[0]), 3), round(o[1] - float(k[1]), 3)] for o, k in zip(out, keep)],
            "threshold_db": round(thr, 1), "noise_db": round(floor, 1), "speech_db": round(speech, 1),
            "inside_speech": notes, "ok": not notes}


def clean_voice(path: str, out: str, denoise: float = 12.0, target_lufs: float = -14.0) -> dict:
    """Clean and master a voice recording: remove rumble (high-pass 80 Hz), reduce steady room noise
    (afftdn, `denoise` dB; 0 = off), a little presence, gentle compression, then loudness to
    `target_lufs` with a -1.5 dB peak limit. The picture is copied without re-encoding."""
    def measure(p: str) -> dict:
        import numpy as np
        log = ff.run(["-i", p, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
        i = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
        y = ff.read_audio_mono(p, sr=16000)
        n = len(y) // 160
        db = 10 * np.log10(np.maximum((y[: n * 160].reshape(n, 160) ** 2).mean(axis=1), 1e-10)) if n else np.zeros(1)
        # How far the speech is above the room noise: loud 10 ms steps against the quietest ones.
        return {"lufs": float(i[-1]) if i else None,
                "speech_over_noise_db": round(float(np.percentile(db, 90) - np.percentile(db, 5)), 1)}

    info = ff.probe(path)
    if not info["audio"]:
        raise ValueError("The file has no audio.")
    before = measure(path)
    chain = ["highpass=f=80"]
    if denoise > 0:
        chain.append(f"afftdn=nr={min(40.0, float(denoise)):.1f}:nf=-40:tn=1")
    chain += ["equalizer=f=3500:t=q:w=1.0:g=2", "acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2",
              f"loudnorm=I={float(target_lufs):.1f}:TP=-1.5:LRA=9", "aresample=48000"]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    video = ["-c:v", "copy"] if info["video"] else ["-vn"]
    ext = Path(out).suffix.lower()
    if ext in (".wav", ".flac"):
        video, acodec = ["-vn"], ([] if ext == ".flac" else ["-c:a", "pcm_s16le"])
    else:
        acodec = ["-c:a", "aac", "-b:a", "192k"]
    ff.run(["-i", path, "-af", ",".join(chain), *video, *acodec, out])
    return {"output": str(Path(out).resolve()), "before": before, "after": measure(out), "filters": chain}
