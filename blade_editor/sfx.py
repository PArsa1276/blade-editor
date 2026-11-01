"""Generate simple sound effects with ffmpeg (free, no sample library needed)."""

from __future__ import annotations

import re
from pathlib import Path

from . import ff

# kind: (lavfi audio source, duration)
_RECIPES = {
    "whoosh": ("anoisesrc=color=pink:amplitude=0.9:d={d},highpass=f=300,lowpass=f=6000,"
               "volume=6dB,afade=t=in:d={d}*0.6:curve=exp,afade=t=out:st={d}*0.6:d={d}*0.4", 0.45),
    "hit": ("aevalsrc='0.9*sin(2*PI*t*(55+90*exp(-t*25)))*exp(-t*9)+0.35*random(0)*exp(-t*40)':d={d}", 0.6),
    "riser": ("aevalsrc='0.5*sin(2*PI*t*(200+1400*t*t/({d}*{d})))*(t/{d})':d={d},"
              "aecho=0.6:0.5:60:0.3,volume=8dB", 1.5),
    "click": ("aevalsrc='0.8*sin(2*PI*2400*t)*exp(-t*120)':d={d}", 0.08),
    "glitch": ("anoisesrc=color=white:amplitude=0.6:d={d},acrusher=bits=4:samples=30,"
               "volume='if(lt(mod(t,0.05),0.025),1,0.1)':eval=frame", 0.3),
    "boom": ("aevalsrc='0.95*sin(2*PI*t*(40+40*exp(-t*8)))*exp(-t*3.5)':d={d},lowpass=f=300", 1.4),
    "swish": ("anoisesrc=color=white:amplitude=0.7:d={d},bandpass=f=2500:w=1800,"
              "volume=28dB,afade=t=in:d={d}*0.3,afade=t=out:st={d}*0.3:d={d}*0.7", 0.25),
}


def kinds() -> list[str]:
    return list(_RECIPES)


def make(kind: str, out_dir: str | Path, duration: float | None = None) -> Path:
    if kind not in _RECIPES:
        raise ValueError(f"Unknown sfx '{kind}'. Use one of: {', '.join(_RECIPES)}")
    recipe, d0 = _RECIPES[kind]
    d = float(duration or d0)
    out = Path(out_dir) / f"sfx_{kind}_{int(d * 1000)}.wav"
    if not out.exists():
        src = re.sub(r"\{d\}\*([0-9.]+)", lambda m: f"{d * float(m.group(1)):.3f}", recipe)
        src = src.replace("{d}", f"{d:.3f}")
        ff.run(["-f", "lavfi", "-i", src, "-t", f"{d:.3f}", "-ac", "2", "-ar", "48000", str(out)])
    return out
