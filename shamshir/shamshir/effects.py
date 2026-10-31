"""Turn effect descriptions into ffmpeg filter expressions.

All times are in seconds relative to the start of the stream the filter runs on
(clip time for clip effects, output time for global effects).
"""

from __future__ import annotations

from typing import Any

# --- envelopes --------------------------------------------------------------

def _win(at: float, dur: float) -> str:
    return f"between(t,{at:.4f},{at + dur:.4f})"


def _decay(at: float, dur: float, power: float = 2.0) -> str:
    """1 at `at`, eases to 0 at `at+dur`, 0 outside."""
    dur = max(dur, 1e-3)
    return f"(if({_win(at, dur)},pow(1-(t-{at:.4f})/{dur:.4f},{power}),0))"


def _bell(at: float, dur: float) -> str:
    """0 -> 1 -> 0 over the window."""
    dur = max(dur, 1e-3)
    return f"(if({_win(at, dur)},sin(PI*(t-{at:.4f})/{dur:.4f}),0))"


def _ramp(at: float, dur: float) -> str:
    """0 before, linear 0->1 inside, 1 after."""
    dur = max(dur, 1e-3)
    return f"(clip((t-{at:.4f})/{dur:.4f},0,1))"


def _smooth(x: str) -> str:
    return f"({x})*({x})*(3-2*({x}))"


GRADES = {
    "none": "",
    "teal_orange": "colorbalance=rs=0.08:gs=-0.02:bs=-0.10:rh=-0.06:gh=0.0:bh=0.10,eq=saturation=1.15:contrast=1.08",
    "warm": "colorbalance=rm=0.08:bm=-0.08,eq=saturation=1.1",
    "cold": "colorbalance=rm=-0.06:bm=0.10,eq=saturation=0.95",
    "bw": "hue=s=0,eq=contrast=1.2",
    "high_contrast_bw": "hue=s=0,eq=contrast=1.6:brightness=-0.03",
    "vintage": "curves=preset=vintage,eq=saturation=0.85",
    "punchy": "eq=contrast=1.15:saturation=1.35,unsharp=5:5:0.6",
    "dark_moody": "eq=brightness=-0.06:contrast=1.2:saturation=0.8,colorbalance=bs=0.06",
    "faded": "curves=all='0/0.08 1/0.92',eq=saturation=0.8",
    "cyber": "colorbalance=rs=0.10:bs=0.15:gm=-0.08,eq=saturation=1.3:contrast=1.1",
}

EFFECT_DOCS = {
    "zoom_punch": "Fast zoom in, then ease back. Keys: at, dur(0.25), amount(0.15).",
    "zoom": "Slow push in or out over a window. Keys: at(0), dur(clip length), from(1.0), to(1.15).",
    "shake": "Camera shake. Keys: at, dur(0.4), amount(px at 1080p, 18), freq(28).",
    "flash": "Brightness flash. Keys: at, dur(0.15), amount(0.8), color('white'|'black').",
    "rgb_split": "Chromatic split. Keys: at, dur(0.2), amount(px, 10).",
    "glitch": "RGB split + noise + jitter burst. Keys: at, dur(0.25), amount(1.0).",
    "blur": "Blur pulse. Keys: at, dur(0.3), amount(8).",
    "grain": "Film grain on the whole span. Keys: amount(10).",
    "vignette": "Dark edges on the whole span. Keys: amount(0.4).",
    "letterbox": "Black bars. Keys: amount(0.12 of height).",
    "invert": "Invert colors inside a window. Keys: at, dur(0.1).",
    "strobe": "Brightness strobe at a rate. Keys: at, dur, rate(8 per s), amount(0.6).",
}


def _f(e: dict, key: str, default: float) -> float:
    v = e.get(key, default)
    return float(default if v is None else v)


def motion_chain(effects: list[dict], width: int, height: int, span: float) -> list[str]:
    """Zoom and shake effects become one scale + crop pair (keeps a fixed output size)."""
    zoom_terms: list[str] = []
    sx_terms: list[str] = []
    sy_terms: list[str] = []
    scale_ref = height / 1080.0 if height <= width else width / 1080.0
    for i, e in enumerate(effects):
        typ = e.get("type")
        at = _f(e, "at", 0.0)
        if typ == "zoom_punch":
            dur, amt = _f(e, "dur", 0.25), _f(e, "amount", 0.15)
            zoom_terms.append(f"{amt:.4f}*{_decay(at, dur, 2.0)}")
        elif typ == "zoom":
            dur = _f(e, "dur", max(span - at, 0.01))
            z0, z1 = _f(e, "from", 1.0), _f(e, "to", 1.15)
            zoom_terms.append(f"({z0 - 1:.4f}+({z1 - z0:.4f})*{_smooth(_ramp(at, dur))})")
        elif typ == "shake":
            dur, amt = _f(e, "dur", 0.4), _f(e, "amount", 18.0) * scale_ref
            fq = _f(e, "freq", 28.0)
            env = _decay(at, dur, 1.0)
            ph = 1.7 * (i + 1)
            sx_terms.append(f"{amt:.2f}*{env}*sin(t*{fq:.2f}*6.2832+{ph:.2f})")
            sy_terms.append(f"{amt * 0.8:.2f}*{env}*sin(t*{fq * 1.37:.2f}*6.2832+{ph * 2.1:.2f})")
    if not (zoom_terms or sx_terms):
        return []
    shake_max = 0.0
    for e in effects:
        if e.get("type") == "shake":
            shake_max = max(shake_max, _f(e, "amount", 18.0) * scale_ref)
    margin = 1.0 + (2.2 * shake_max / min(width, height) if shake_max else 0.0)
    z = "(1+" + ("+".join(zoom_terms) if zoom_terms else "0") + f")*{margin:.4f}"
    sx = "+".join(sx_terms) or "0"
    sy = "+".join(sy_terms) or "0"
    return [
        f"scale=w='trunc({width}*{z}/2)*2+2':h='trunc({height}*{z}/2)*2+2':eval=frame:flags=bicubic",
        f"crop=w={width}:h={height}:x='(iw-{width})/2+{sx}':y='(ih-{height})/2+{sy}'",
        "setsar=1",
    ]


def look_chain(effects: list[dict], width: int, height: int, span: float) -> list[str]:
    """Color, flash, split, blur and texture effects."""
    out: list[str] = []
    bright_terms: list[str] = []
    for e in effects:
        typ = e.get("type")
        at = _f(e, "at", 0.0)
        if typ == "flash":
            dur, amt = _f(e, "dur", 0.15), _f(e, "amount", 0.8)
            sign = -1.0 if e.get("color") == "black" else 1.0
            bright_terms.append(f"{sign * amt:.3f}*{_decay(at, dur, 1.5)}")
        elif typ == "strobe":
            dur, amt, rate = _f(e, "dur", 0.5), _f(e, "amount", 0.6), _f(e, "rate", 8.0)
            bright_terms.append(f"{amt:.3f}*if({_win(at, dur)},gt(sin(t*{rate:.2f}*6.2832),0),0)")
        elif typ == "rgb_split":
            dur, amt = _f(e, "dur", 0.2), int(_f(e, "amount", 10.0) * width / 1080)
            out.append(f"rgbashift=rh={amt}:bh=-{amt}:enable='{_win(at, dur)}'")
        elif typ == "glitch":
            dur, amt = _f(e, "dur", 0.25), _f(e, "amount", 1.0)
            px = max(2, int(14 * amt * width / 1080))
            out.append(f"rgbashift=rh={px}:bv={px // 2}:gh=-{px // 2}:enable='{_win(at, dur)}'")
            out.append(f"noise=alls={int(40 * amt)}:allf=t:enable='{_win(at, dur)}'")
            out.append(f"hue=H='{2.5 * amt:.2f}*sin(t*90)':enable='{_win(at, dur)}'")
        elif typ == "blur":
            dur, amt = _f(e, "dur", 0.3), max(1, int(_f(e, "amount", 8.0)))
            out.append(f"gblur=sigma={amt}:enable='{_win(at, dur)}'")
        elif typ == "invert":
            out.append(f"negate=enable='{_win(at, _f(e, 'dur', 0.1))}'")
        elif typ == "grain":
            out.append(f"noise=alls={int(_f(e, 'amount', 10))}:allf=t")
        elif typ == "vignette":
            out.append(f"vignette=angle={0.3 + _f(e, 'amount', 0.4):.3f}")
        elif typ == "letterbox":
            bar = int(height * _f(e, "amount", 0.12) / 2)
            out.append(f"drawbox=x=0:y=0:w=iw:h={bar}:color=black:t=fill,"
                       f"drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black:t=fill")
    if bright_terms:
        out.insert(0, f"eq=brightness='{'+'.join(bright_terms)}':eval=frame")
    return out


def grade(name: str | None) -> list[str]:
    if not name:
        return []
    if name not in GRADES:
        raise ValueError(f"Unknown grade '{name}'. Use one of: {', '.join(GRADES)}")
    g = GRADES[name]
    return [g] if g else []


def validate(effects: list[Any]) -> None:
    for e in effects:
        if not isinstance(e, dict) or e.get("type") not in EFFECT_DOCS:
            raise ValueError(f"Bad effect {e!r}. Known types: {', '.join(EFFECT_DOCS)}")
