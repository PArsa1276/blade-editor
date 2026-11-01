"""Camera motion: measure move / rotation / zoom in a reference shot, reduce it to keyframes,
and replay keyframes on any clip with the `camera` effect."""

from __future__ import annotations

import numpy as np

from . import ff


def _shift(a: np.ndarray, b: np.ndarray, win: np.ndarray) -> tuple[float, float, float]:
    """Sub-pixel translation of content from a to b (phase correlation + parabolic peak)."""
    fa = np.fft.fft2((a - a.mean()) * win)
    fb = np.fft.fft2((b - b.mean()) * win)
    r = fa * np.conj(fb)
    corr = np.abs(np.fft.ifft2(r / (np.abs(r) + 1e-9)))
    h, w = corr.shape
    py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)

    def refine(c_m, c_0, c_p):
        d = c_m - 2 * c_0 + c_p
        return 0.0 if d == 0 else 0.5 * (c_m - c_p) / d

    fx = px + refine(corr[py, (px - 1) % w], corr[py, px], corr[py, (px + 1) % w])
    fy = py + refine(corr[(py - 1) % h, px], corr[py, px], corr[(py + 1) % h, px])
    dx = fx if fx <= w / 2 else fx - w
    dy = fy if fy <= h / 2 else fy - h
    return -float(dx), -float(dy), float(corr.max() / (corr.mean() + 1e-9))


def _fit(s: np.ndarray, d: np.ndarray) -> np.ndarray:
    """Least squares for x' = a*x - b*y + tx, y' = b*x + a*y + ty."""
    A = np.zeros((2 * len(s), 4))
    A[0::2] = np.c_[s[:, 0], -s[:, 1], np.ones(len(s)), np.zeros(len(s))]
    A[1::2] = np.c_[s[:, 1], s[:, 0], np.zeros(len(s)), np.ones(len(s))]
    return np.linalg.lstsq(A, d.reshape(-1), rcond=None)[0]


def _similarity(a: np.ndarray, b: np.ndarray, grid: int = 4) -> tuple[float, float, float, float]:
    """Content motion a->b as (dx, dy, rotation_deg, scale) from patch shifts on a grid.
    Patches that disagree with the global fit (moving objects) are dropped and the fit is redone."""
    h, w = a.shape
    ph, pw = h // grid, w // grid
    win = np.outer(np.hanning(ph), np.hanning(pw)).astype(np.float32)
    src, dst = [], []
    for gy in range(grid):
        for gx in range(grid):
            ys, xs = gy * ph, gx * pw
            dx, dy, conf = _shift(a[ys:ys + ph, xs:xs + pw], b[ys:ys + ph, xs:xs + pw], win)
            if conf > 6:
                cx, cy = xs + pw / 2 - w / 2, ys + ph / 2 - h / 2
                src.append((cx, cy))
                dst.append((cx + dx, cy + dy))
    if len(src) < 4:
        return 0.0, 0.0, 0.0, 1.0
    s, d = np.array(src), np.array(dst)
    p = _fit(s, d)
    for _ in range(2):
        pred = np.c_[p[0] * s[:, 0] - p[1] * s[:, 1] + p[2], p[1] * s[:, 0] + p[0] * s[:, 1] + p[3]]
        res = np.hypot(*(pred - d).T)
        keep = res <= max(0.75, np.percentile(res, 70))
        if keep.sum() < 4 or keep.all():
            break
        s, d = s[keep], d[keep]
        p = _fit(s, d)
    return float(p[2]), float(p[3]), float(np.degrees(np.arctan2(p[1], p[0]))), float(np.hypot(p[0], p[1]))


def _rotate(img: np.ndarray, deg: float) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.fromarray(img).rotate(deg, resample=Image.BILINEAR,
                                                    fillcolor=float(img.mean())), dtype=np.float32)


def _coarse_rotation(a: np.ndarray, b: np.ndarray, max_deg: float = 30, step: float = 3) -> float:
    """Fast spins (> ~3 deg per frame) are too big for the patch fit: find the angle whose
    un-rotated frame best matches (phase-correlation peak, which ignores movement)."""
    h, w = a.shape
    c = slice(h // 6, h - h // 6), slice(w // 6, w - w // 6)
    ac = a[c]
    win = np.outer(np.hanning(ac.shape[0]), np.hanning(ac.shape[1])).astype(np.float32)
    base = _shift(ac, b[c], win)[2]
    best, best_conf = 0.0, base
    for deg in np.arange(-max_deg, max_deg + 0.1, step):
        if deg == 0:
            continue
        # PIL turns counter-clockwise; our angles are clockwise (as ffmpeg's rotate).
        conf = _shift(ac, _rotate(b, deg)[c], win)[2]
        if conf > best_conf:
            best, best_conf = float(deg), conf
    return best if best_conf > base * 2.0 else 0.0


def _match(a: np.ndarray, b: np.ndarray) -> float:
    h, w = a.shape
    c = slice(h // 6, h - h // 6), slice(w // 6, w - w // 6)
    win = np.outer(np.hanning(c[0].stop - c[0].start), np.hanning(c[1].stop - c[1].start)).astype(np.float32)
    return _shift(a[c], b[c], win)[2]


def measure(path: str, start: float = 0.0, end: float | None = None, fps: float = 30.0,
            stride: int = 6) -> dict:
    """Cumulative content motion of one shot: x, y (fractions of frame size), rot (deg), zoom.
    Movement and rotation are measured frame to frame; zoom `stride` frames apart (a bigger
    change, so less drift) after the later frame is shifted back by the movement."""
    dur = (end - start) if end else None
    frames, use_fps = ff.read_gray_frames(path, width=320, fps=fps, start=start, duration=dur)
    f = frames.astype(np.float32)
    n, (h, w) = len(f), f.shape[1:]
    px, py, rot, lz = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    confs: list[float] = []
    for i in range(1, n):
        conf = _match(f[i - 1], f[i])
        typical = float(np.median(confs[-15:])) if len(confs) >= 3 else conf
        confs.append(conf)
        # Only when the frames stop matching (fast spin) search the angle; else trust the fit.
        coarse = _coarse_rotation(f[i - 1], f[i]) if conf < 0.35 * typical else 0.0
        b = _rotate(f[i], coarse) if coarse else f[i]
        dx, dy, dr, _ = _similarity(f[i - 1], b)
        px[i], py[i], rot[i] = px[i - 1] + dx, py[i - 1] + dy, rot[i - 1] + coarse + dr
    mh, mw = h // 8, w // 8
    anchors = (list(range(0, n - 1, stride)) + [n - 1]) if n > 1 else [0]
    for a, b in zip(anchors[:-1], anchors[1:]):
        back = np.roll(f[b], (-int(round(py[b] - py[a])), -int(round(px[b] - px[a]))), axis=(0, 1))
        _, _, _, ds = _similarity(f[a][mh:-mh, mw:-mw], back[mh:-mh, mw:-mw])
        for k in range(1, b - a + 1):
            lz[a + k] = lz[a] + k / (b - a) * np.log(max(ds, 1e-3))
    t = np.arange(n) / use_fps
    return {"t": t, "x": px / w, "y": py / h, "rot": rot, "zoom": np.exp(lz), "fps": use_fps}


def _rdp(idx: list[int], pts: np.ndarray, eps: np.ndarray) -> list[int]:
    """Ramer-Douglas-Peucker on a multi-channel curve (normalised per channel by eps)."""
    a, b = idx[0], idx[-1]
    if b - a < 2:
        return [a, b]
    seg = pts[a:b + 1]
    line = pts[a] + np.outer(np.linspace(0, 1, b - a + 1), pts[b] - pts[a])
    err = (np.abs(seg - line) / eps).max(axis=1)
    k = int(np.argmax(err))
    if err[k] <= 1.0:
        return [a, b]
    m = a + k
    return _rdp([a, m], pts, eps)[:-1] + _rdp([m, b], pts, eps)


def keyframes(m: dict, max_keys: int = 24) -> list[list[float]]:
    """Few keyframes [t, x, y, rot, zoom] that redraw the measured motion closely."""
    pts = np.c_[m["x"], m["y"], m["rot"], m["zoom"]]
    k = max(3, int(m["fps"] * 0.25)) | 1  # smooth out measurement noise (~0.25 s)
    pad = np.pad(pts, ((k // 2, k // 2), (0, 0)), mode="edge")
    sm = np.stack([np.convolve(pad[:, j], np.ones(k) / k, mode="valid") for j in range(4)], axis=1)
    eps = np.array([0.01, 0.01, 1.0, 0.01])
    for _ in range(6):
        idx = _rdp([0, len(sm) - 1], sm, eps)
        if len(idx) <= max_keys:
            break
        eps *= 1.6
    return [[round(float(m["t"][i]), 3), *[round(float(v), 4) for v in sm[i]]] for i in idx]


def describe(m: dict) -> list[str]:
    """Plain words for the main moves, so the agent can choose the right tool."""
    out = []
    x, rot, zoom, fps = m["x"], m["rot"], m["zoom"], m["fps"]
    if len(x) < 3:
        return out
    vx = np.diff(x) * fps
    turns = int(np.sum(np.diff(np.sign(vx[np.abs(vx) > 0.05])) != 0))
    span = float(x.max() - x.min())
    if span > 0.05 and turns >= 2 and abs(x[-1] - x[0]) < span * 0.4:
        out.append(f"sway left-right (range {span:.2f} of width, {turns} turns, returns to start)")
    elif span > 0.05:
        out.append(f"pan/whip {'right' if x[-1] < x[0] else 'left'} ({span:.2f} of width)")
    if np.abs(vx).max() > 1.5:
        out.append("whip (very fast horizontal move)")
    r = float(rot.max() - rot.min())
    if r > 3:
        out.append(f"rotation {rot.min():.0f}..{rot.max():.0f} deg")
    if len(rot) > 2 and float(np.abs(np.diff(rot)).max()) > 2.5:
        # Fast spins are under-measured (about 30% low): rebuild them from a preset instead.
        out.append("FAST SPIN: measured angle is too low; use camera_preset spin360_holds/tilt_swing "
                   "with the real angles you see in view_frames")
    z = float(zoom.max() / max(zoom.min(), 1e-6))
    if z > 1.04:
        out.append(f"zoom {'in' if zoom[-1] > zoom[0] else 'out' if zoom[-1] < zoom[0] else 'pulse'} (x{z:.2f})")
    jitter = float(np.abs(np.diff(vx)).mean()) if len(vx) > 2 else 0.0
    if jitter > 0.6:
        out.append("shake (fast jitter)")
    return out


def camera_chain(keys: list[list[float]], W: int, H: int, ease: str = "smooth") -> list[str]:
    """ffmpeg filters that replay keyframes [t, x, y, rot_deg, zoom] on a W x H stream.
    x, y are content offsets in fractions of the frame; the frame is zoomed so no edge shows."""
    keys = sorted(keys, key=lambda k: k[0])
    if len(keys) == 1:
        keys = keys + [[keys[0][0] + 1, *keys[0][1:]]]

    def lerp(ch: int) -> str:
        expr = f"{keys[-1][ch]:.5f}"
        for a, b in reversed(list(zip(keys[:-1], keys[1:]))):
            d = max(b[0] - a[0], 1e-3)
            u = f"clip((t-{a[0]:.4f})/{d:.4f},0,1)"
            if ease == "smooth":
                u = f"({u})*({u})*(3-2*({u}))"
            seg = f"({a[ch]:.5f}+({b[ch] - a[ch]:.5f})*{u})"
            expr = f"if(lt(t,{b[0]:.4f}),{seg},{expr})"
        return f"if(lt(t,{keys[0][0]:.4f}),{keys[0][ch]:.5f},{expr})"

    X, Y, R, Z = lerp(1), lerp(2), lerp(3), lerp(4)
    mx = max(abs(k[1]) for k in keys)
    my = max(abs(k[2]) for k in keys)
    margin = 1 + 2 * max(mx, my)
    ratio = max(W, H) / min(W, H)
    # Zoom so that a rotated, shifted frame still covers the output.
    zexpr = f"({Z})*{margin:.4f}*(abs(cos(({R})*PI/180))+abs(sin(({R})*PI/180))*{ratio:.4f})"
    return [
        f"scale=w='trunc({W}*{zexpr}/2)*2+2':h='trunc({H}*{zexpr}/2)*2+2':eval=frame:flags=bicubic",
        f"rotate=a='({R})*PI/180':ow=iw:oh=ih:c=black",
        f"crop=w={W}:h={H}:x='(iw-{W})/2-({X})*{W}':y='(ih-{H})/2-({Y})*{H}'",
        "setsar=1",
    ]


def preset(name: str, duration: float, amount: float | None = None, count: int | None = None) -> list[list[float]]:
    """Ready keyframes [t, x, y, rot, zoom] for common moves (use with ease 'smooth')."""
    d = float(duration)
    if name == "spin360_holds":
        # Turn 90 degrees, stop, turn again ... until 360; each stop holds half of its slot.
        n = count or 4
        slot, keys = d / n, [[0.0, 0, 0, 0, 1]]
        for i in range(n):
            keys.append([round(i * slot + slot * 0.5, 4), 0, 0, 360 / n * (i + 1), 1])
            keys.append([round((i + 1) * slot, 4), 0, 0, 360 / n * (i + 1), 1])
        return keys
    if name == "sway":
        a, n = amount or 0.12, count or 2
        pts = [[round(d * k / (2 * n), 4), (a if k % 2 else 0) * (1 if (k // 2) % 2 == 0 else -1), 0, 0, 1]
               for k in range(2 * n + 1)]
        return pts
    if name in ("whip_left", "whip_right"):
        a = (amount or 0.6) * (-1 if name == "whip_left" else 1)
        return [[0.0, 0, 0, 0, 1], [round(d * 0.35, 4), a, 0, 0, 1.08], [d, a, 0, 0, 1.0]]
    if name == "zoom_pulse":
        a, n = amount or 0.15, count or 2
        return [[round(d * k / (2 * n), 4), 0, 0, 0, 1 + (a if k % 2 else 0)] for k in range(2 * n + 1)]
    if name == "tilt_swing":
        a, n = amount or 8.0, count or 2
        return [[round(d * k / (2 * n), 4), 0, 0, (a if k % 2 else 0) * (1 if (k // 2) % 2 == 0 else -1), 1]
                for k in range(2 * n + 1)]
    raise ValueError("Presets: spin360_holds, sway, whip_left, whip_right, zoom_pulse, tilt_swing")
