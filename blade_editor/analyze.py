"""Video analysis: cuts, flashes, motion, camera moves, shake and contact sheets."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import audio, ff


def _phase_shift(a: np.ndarray, b: np.ndarray, win: np.ndarray) -> tuple[float, float, float]:
    """Global translation from frame a to frame b (dx, dy in pixels) and peak confidence."""
    fa = np.fft.fft2((a - a.mean()) * win)
    fb = np.fft.fft2((b - b.mean()) * win)
    r = fa * np.conj(fb)
    r /= np.abs(r) + 1e-9
    corr = np.abs(np.fft.ifft2(r))
    peak = np.unravel_index(int(np.argmax(corr)), corr.shape)
    h, w = corr.shape
    dy = peak[0] if peak[0] <= h // 2 else peak[0] - h
    dx = peak[1] if peak[1] <= w // 2 else peak[1] - w
    conf = float(corr.max() / (corr.mean() + 1e-9))
    return -float(dx), -float(dy), conf


def output_camera_moving(path: str, width: int, height: int, fps: float = 30.0) -> tuple[np.ndarray, float]:
    """Per frame: does the camera move as analyze_video would measure it in a 'cover' crop of the
    source to width x height? (speed > 0.6 px at 160 px wide, like moving_camera_share).
    The crop magnifies the source, so a slow drift that rounds to 0 px in the full frame can be
    1 px per frame in the output: measure in the output's own crop and size."""
    sw = 160
    sh = max(2, int(round(sw * height / width / 2)) * 2)
    info = ff.probe(path)
    use = min(fps, (info.get("video") or {}).get("fps") or fps)
    vf = (f"fps={use},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
          f"scale={sw}:{sh}:flags=area,format=gray")
    proc = subprocess.run([ff._bin("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error", "-i", str(path),
                           "-vf", vf, "-f", "rawvideo", "-"], capture_output=True)
    n = len(proc.stdout) // (sw * sh)
    f = np.frombuffer(proc.stdout[: n * sw * sh], dtype=np.uint8).reshape(n, sh, sw).astype(np.float32)
    win = np.outer(np.hanning(sh), np.hanning(sw)).astype(np.float32)
    moving = np.zeros(n, dtype=bool)
    for i in range(1, n):
        dx, dy, conf = _phase_shift(f[i - 1], f[i], win)
        moving[i] = conf > 8 and float(np.hypot(dx, dy)) > 0.6
    return moving, use


def _peaks(x: np.ndarray, thr: np.ndarray | float, min_gap: int) -> list[int]:
    idx = np.where((x[1:-1] > x[:-2]) & (x[1:-1] >= x[2:]) & (x[1:-1] > thr if np.isscalar(thr) else x[1:-1] > thr[1:-1]))[0] + 1
    out: list[int] = []
    for i in idx:
        if not out or i - out[-1] >= min_gap:
            out.append(int(i))
        elif x[i] > x[out[-1]]:
            out[-1] = int(i)
    return out


SENSITIVITY = {"low": 1.5, "normal": 1.0, "high": 0.7}


def analyze_video(path: str, max_fps: float = 30.0, include_audio: bool = True,
                  sensitivity: str = "normal") -> dict:
    """Measure the edit language of a video: cut rhythm, flashes, motion, camera and shake."""
    info = ff.probe(path)
    frames, fps = ff.read_gray_frames(path, width=160, fps=max_fps)
    n = len(frames)
    if n < 2:
        raise ff.FFError("The video is too short to analyze.")
    f = frames.astype(np.float32)
    luma = f.mean(axis=(1, 2))
    diff = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    diff = np.concatenate([[0.0], diff])

    # Histogram distance helps separate real cuts from fast motion.
    hists = np.stack([np.histogram(fr, bins=32, range=(0, 255))[0] for fr in frames]).astype(np.float32)
    hists /= hists.sum(axis=1, keepdims=True) + 1e-9
    hdist = np.concatenate([[0.0], 0.5 * np.abs(np.diff(hists, axis=0)).sum(axis=1)])

    # Cut score: colour-histogram change (robust to noisy texture) plus pixel change,
    # each compared with its own neighbourhood.
    k = max(3, int(fps))

    def _local_median(x: np.ndarray, skip_frozen: bool = False) -> np.ndarray:
        pad = np.pad(x, (k, k), mode="edge")
        out = []
        for i in range(n):
            nb = np.concatenate([pad[i: i + k], pad[i + k + 1: i + 2 * k + 1]])
            if skip_frozen and (nb >= 0.5).any():
                # Frozen frames (a held frame, a freeze at the end) are not the shot's normal
                # motion: with them the median fell and normal motion next to a freeze looked
                # like a cut (r2 at 13.33: neighbours 27-33, median 7.1 with 4 frozen frames).
                nb = nb[nb >= 0.5]
            out.append(np.median(nb))
        return np.array(out)

    h_med = _local_median(hdist)
    d_med = _local_median(diff, skip_frozen=True)
    h_score = hdist - h_med
    d_ratio = diff / (d_med + 1.0)
    k_s = SENSITIVITY[sensitivity]  # "low" finds fewer cuts, "high" more
    rule1 = h_score > np.maximum(0.2, 2.5 * h_med) * k_s
    is_cut = (rule1 |
              ((h_score > 0.1 * k_s) & (d_ratio > 3.0 * k_s)) |
              ((diff - d_med > 25 * k_s) & (d_ratio > 2.5 * k_s)))
    win0 = np.outer(np.hanning(f.shape[1]), np.hanning(f.shape[2])).astype(np.float32)

    def _moved(i: int) -> bool:
        # The same picture, moved (a fast pan or whip): a strong global-shift match of 2-80 px
        # between two frames with texture. Measured: false pan cuts conf 36-146; real cuts
        # (also into moving shots) 9-15. Black/flat frames (std < 15) give random strong
        # peaks (cuts from black: std 4-6; textured frames: 14-77), and a peak at shift 0 is a
        # static logo or border, so both are not used.
        if min(f[i - 1].std(), f[i].std()) < 15:
            return False
        dx, dy, conf = _phase_shift(f[i - 1], f[i], win0)
        return conf > 25 and 2 <= np.hypot(dx, dy) <= 80

    # frames 1-2: decoder/filter start-up noise; rules 2+3 only: not when the picture just moved
    cand = [i for i in range(3, n) if is_cut[i] and (rule1[i] or not _moved(i))]
    min_gap = max(2, int(fps * 0.08))
    cut_idx: list[int] = []
    for i in cand:
        if cut_idx and i - cut_idx[-1] < min_gap:
            if hdist[i] > hdist[cut_idx[-1]]:
                cut_idx[-1] = i
            continue
        cut_idx.append(i)
    # Candidates closer than 0.2 s to each other are one event (fast POV motion, a dip to black,
    # a strobe or a glitch), not several cuts: one cut at the strongest frame.
    gap = max(min_gap, int(round(0.2 * fps)))
    groups: list[list[int]] = []
    for i in cut_idx:
        if groups and i - groups[-1][0] <= gap:  # from the event's first frame: no chains
            groups[-1].append(i)
        else:
            groups.append([i])
    cut_idx = [max(g, key=lambda j: hdist[j]) for g in groups]

    # Crossfades: no single frame changes much, so the rules above miss most of them. In the
    # middle of a crossfade the frame is the average of the frames ~0.1 s before and after
    # ("mix" = |f - (a+b)/2| / |a-b|). Measured on 24 crossfades: 16 had mix <= 0.40; frames
    # outside transitions (pans, zooms, fast motion) never went below 0.43 when |a-b| >= 15.
    kd = max(2, int(round(0.1 * fps)))
    mix = np.full(n, 9.0)
    for i in range(kd, n - kd):
        a, b = f[i - kd], f[i + kd]
        dab = float(np.abs(a - b).mean())
        if dab >= 15:
            mix[i] = float(np.abs(f[i] - (a + b) / 2).mean()) / dab
    near = max(2, int(round(0.3 * fps)))

    def _new_content(i: int) -> bool:
        # A blur or brightness pulse on one shot also mixes; a crossfade changes the content:
        # structural correlation of the frames 0.2 s before and after. Crossfades -0.27..0.68,
        # blur pulses in velocity edits 0.65..0.97 (most >= 0.76).
        a = f[max(0, i - 2 * kd)] - f[max(0, i - 2 * kd)].mean()
        b = f[min(n - 1, i + 2 * kd)] - f[min(n - 1, i + 2 * kd)].mean()
        if float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-9)) > 0.70:
            return False
        # A fast pan can also look mixed: there the middle frame is the frame before/after moved
        # far (fast pan: 54-78 px, conf 134-430; crossfades: shift <= 15 px when conf > 25).
        for x, y in ((f[i - kd], f[i]), (f[i], f[i + kd])):
            dx, dy, conf = _phase_shift(x, y, win0)
            if conf > 25 and np.hypot(dx, dy) > 20:
                return False
        return True

    dissolves: list[int] = []
    for i in range(kd, n - kd):
        if mix[i] <= 0.40 and mix[i] == mix[max(0, i - near): i + near + 1].min() and _new_content(i):
            # A cut found by the rules above (at the edge of a crossfade up to ~1 s) is the same event.
            if not any(abs(i - c) <= 0.5 * fps for c in cut_idx) and not any(abs(i - d) <= near for d in dissolves):
                dissolves.append(i)
    cut_idx = sorted(cut_idx + dissolves)

    # Flashes: brightness jumps up in 1-2 frames and the bright peak is short (<= ~0.3 s).
    # A cut to a bright shot is not a flash: it rises in one frame too, but it stays bright
    # for the whole shot (in fast edits shots are only ~0.5 s, so "falls back within 0.3 s"
    # alone was true for them, and for brightness changes inside a shot).
    flashes = []
    span = max(2, int(0.3 * fps))
    for i in range(1, n - 1):
        before = luma[max(0, i - span): i].min()
        after = luma[i + 1: i + 1 + span].min() if i + 1 < n else luma[i]
        rise = luma[i] - before
        if not (rise > 35 and luma[i] - after > 25 and luma[i] > 120):
            continue
        if luma[i] - luma[max(0, i - 2)] < 0.6 * rise:  # slow rise: light change, not a flash
            continue
        half = before + 0.5 * rise
        lo, hi = i, i
        while lo > 0 and luma[lo - 1] > half:
            lo -= 1
        while hi < n - 1 and luma[hi + 1] > half:
            hi += 1
        if hi - lo + 1 > span:  # stays bright: a bright shot
            continue
        # A flash returns to the same picture (histogram distance of frame i-2 and frame i+0.3 s
        # <= 0.30; real flashes in velocity edits: 0.05-0.26, brightness changes inside fast
        # POV shots: 0.31-0.78). Exception: an almost uniform white peak is a flash on a cut.
        pre, post = max(0, i - 2), min(n - 1, i + span)
        white = luma[i] >= 200 and f[i].std() <= 10
        if not white and 0.5 * float(np.abs(hists[pre] - hists[post]).sum()) > 0.30:
            continue
        if not flashes or i - flashes[-1] > span:
            flashes.append(i)

    # A flash changes every pixel. Keep its cut only when the picture before the flash
    # differs from the picture after it (a flash cut); otherwise drop it.
    def _hd(x: int, y: int) -> float:
        return float(0.5 * np.abs(hists[x] - hists[y]).sum())

    kept = []
    for c in cut_idx:
        near = [fl for fl in flashes if -span <= c - fl <= span]
        if not near:
            kept.append(c)
            continue
        fl = near[0]
        pre, post = max(0, fl - 2), min(n - 1, fl + span + 1)
        if _hd(pre, post) > 0.25 and not any(abs(k2 - fl) <= span for k2 in kept):
            kept.append(c)  # the cut's own frame: the flash peak can be frames later (off the beat)
    cut_idx = sorted(set(kept))

    # Camera motion between neighbour frames (skip cut frames).
    h, w = frames.shape[1:]
    win = np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)
    motion = np.zeros((n, 2), dtype=np.float32)
    cut_set = set(cut_idx)
    for i in range(1, n):
        if i in cut_set:
            continue
        dx, dy, conf = _phase_shift(f[i - 1], f[i], win)
        if conf > 8:
            motion[i] = (dx, dy)
    speed = np.hypot(motion[:, 0], motion[:, 1])

    # Shake: fast direction reversals of the camera vector.
    shake = np.zeros(n, dtype=np.float32)
    for i in range(2, n):
        a, b = motion[i - 1], motion[i]
        if np.dot(a, b) < 0 and min(np.linalg.norm(a), np.linalg.norm(b)) > 0.8:
            shake[i] = np.linalg.norm(a - b)

    shots = []
    bounds = [0, *cut_idx, n]
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b <= a:
            continue
        # motion[] is the content motion; the camera moves the other way.
        mv = motion[a:b].sum(axis=0)
        mean_speed = float(speed[a:b].mean())
        path_len = float(speed[a:b].sum())
        steady = path_len > 0 and float(np.hypot(*mv)) / path_len > 0.6
        cam = "static"
        if mean_speed > 0.6 and steady:
            cam = ("pan right" if mv[0] < 0 else "pan left") if abs(mv[0]) >= abs(mv[1]) else \
                  ("tilt down" if mv[1] < 0 else "tilt up")
        elif mean_speed > 0.6:
            cam = "handheld / mixed motion"
        shots.append({
            "start": round(a / fps, 3), "end": round(b / fps, 3),
            "duration": round((b - a) / fps, 3),
            "mean_brightness": round(float(luma[a:b].mean()), 1),
            "activity": round(float(diff[a + 1:b].mean()) if b - a > 1 else 0.0, 2),
            "camera": cam,
            "shake": round(float(shake[a:b].mean()), 2),
        })

    duration = n / fps
    per_second = []
    for s in range(int(np.ceil(duration))):
        a, b = int(s * fps), min(n, int((s + 1) * fps))
        if a >= b:
            break
        per_second.append({
            "second": s,
            "cuts": sum(1 for c in cut_idx if a <= c < b),
            "flashes": sum(1 for c in flashes if a <= c < b),
            "activity": round(float(diff[a:b].mean()), 2),
            "camera_speed": round(float(speed[a:b].mean()), 2),
            "shake": round(float(shake[a:b].mean()), 2),
            "brightness": round(float(luma[a:b].mean()), 1),
        })

    shot_durs = [s["duration"] for s in shots]
    result = {
        "file": info,
        "analysis_fps": fps,
        "frames_analyzed": n,
        "cuts": [round(i / fps, 3) for i in cut_idx],
        "dissolves": [round(i / fps, 3) for i in dissolves],  # also in cuts: the middle of a crossfade
        # 0..1: how far over the threshold each cut is. Low values are the ones worth a look.
        "cut_confidence": [round(float(min(1.0, max(hdist[i] / 0.5, diff[i] / 60))), 2) for i in cut_idx],
        "flashes": [round(i / fps, 3) for i in flashes],
        "shots": shots,
        "per_second": per_second,
        "summary": {
            "shot_count": len(shots),
            "cuts_per_second": round(len(cut_idx) / duration, 3) if duration else 0,
            "mean_shot_length": round(float(np.mean(shot_durs)), 3) if shot_durs else None,
            "median_shot_length": round(float(np.median(shot_durs)), 3) if shot_durs else None,
            "flashes_per_second": round(len(flashes) / duration, 3) if duration else 0,
            "mean_activity": round(float(diff.mean()), 2),
            "moving_camera_share": round(float((speed > 0.6).mean()), 3),
            "shake_share": round(float((shake > 1.5).mean()), 3),
        },
    }
    if include_audio and info["audio"]:
        beats = audio.analyze_beats(path)
        result["audio"] = beats
        if beats["beats"] and cut_idx:
            bt = np.array(beats["beats"])
            dists = [float(np.min(np.abs(bt - c / fps))) for c in cut_idx]
            on_beat = sum(d <= 0.07 for d in dists)
            result["summary"]["cuts_on_beat_share"] = round(on_beat / len(cut_idx), 3)
    return result


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def contact_sheet(path: str, out: str, start: float = 0.0, end: float | None = None,
                  every: float | None = None, count: int = 16, cols: int = 4,
                  thumb_width: int = 320) -> dict:
    """Build a grid of frames with time stamps. Return the image path and the sample times."""
    info = ff.probe(path)
    dur = info["duration"]
    end = min(end if end is not None else dur, dur)
    if end <= start:
        raise ff.FFError("The end time must be after the start time.")
    if every:
        times = list(np.arange(start, end, every))
    else:
        count = max(1, min(count, 64))
        step = (end - start) / count
        times = [start + step * (i + 0.5) for i in range(count)]
    times = [round(float(t), 3) for t in times][:64]
    fps = info["video"]["fps"] or 30
    thumbs = []
    tmp = Path(out).with_suffix("")
    tmp.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(times):
        fp = tmp / f"f{i:03d}.jpg"
        try:
            ff.extract_frame(path, t, fp, thumb_width)
            thumbs.append((t, Image.open(fp).convert("RGB")))
        except ff.FFError:
            continue
    if not thumbs:
        raise ff.FFError("No frames could be extracted.")
    tw, th = thumbs[0][1].size
    rows = (len(thumbs) + cols - 1) // cols
    label_h = 22
    sheet = Image.new("RGB", (cols * tw, rows * (th + label_h)), (16, 16, 16))
    draw = ImageDraw.Draw(sheet)
    font = _font(15)
    for i, (t, im) in enumerate(thumbs):
        x, y = (i % cols) * tw, (i // cols) * (th + label_h)
        sheet.paste(im.resize((tw, th)), (x, y + label_h))
        draw.text((x + 6, y + 3), f"#{i}  {t:.2f}s  f{int(round(t * fps))}", fill=(255, 220, 0), font=font)
    sheet.save(out, quality=85)
    for p in tmp.glob("*.jpg"):
        p.unlink()
    tmp.rmdir()
    return {"image": str(Path(out).resolve()), "times": [t for t, _ in thumbs], "size": sheet.size}
