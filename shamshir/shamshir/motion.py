"""Motion graphics from Kinetograph (optional, separate install: npm i -D kinetograph).

Kinetograph drops the alpha channel in every video codec, so the graphic is rendered twice,
on black and on white, and the exact alpha comes from the difference (difference matting).
The entry must take its background from the environment:
  <Composition background={process.env.SHAMSHIR_BG ?? "transparent"} ... />
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import ff


def render(entry: str, out: str | Path, comp: str | None = None, props: dict | None = None,
           draft: bool = False, timeout: float = 1800) -> dict:
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("Node.js (npx) is not installed. Kinetograph needs Node.js.")
    entry_p = Path(entry).resolve()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = {bg: out.with_name(f"{out.stem}_{bg}.mov") for bg in ("black", "white")}
    for bg, path in tmp.items():
        cmd = [npx, "kinetograph", "render", str(entry_p), "-o", str(path), "--codec", "prores",
               "--prores-profile", "4444", "--concurrency", "4"]
        if comp:
            cmd += ["--comp", comp]
        if props:
            cmd += ["--props", json.dumps(props, ensure_ascii=False)]
        if draft:
            cmd.append("--draft")
        p = subprocess.run(cmd, cwd=entry_p.parent, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "SHAMSHIR_BG": bg})
        if p.returncode != 0:
            raise RuntimeError(f"kinetograph render failed:\n{(p.stderr or p.stdout)[-2000:]}")
    # alpha = 1 - (white - black); colour = black / alpha (unpremultiply).
    ff.run(["-i", str(tmp["black"]), "-i", str(tmp["white"]), "-filter_complex",
            "[0:v]format=gbrp,split[b0][b1];[1:v]format=gbrp[w];"
            "[w][b0]blend=all_mode=difference,extractplanes=g,negate,"
            "lut=y='clip((val-2)*255/253,0,255)'[a];"
            "[b1][a]alphamerge,unpremultiply=inplace=1,format=yuva444p10le[v]",
            "-map", "[v]", "-c:v", "prores_ks", "-profile:v", "4", str(out)])
    if _identical(tmp):
        raise RuntimeError("The black and white renders are the same, so no alpha could be made. "
                           "Set <Composition background={process.env.SHAMSHIR_BG ?? 'transparent'}>.")
    for p in tmp.values():
        p.unlink(missing_ok=True)
    info = ff.probe(out)
    return {"path": str(out.resolve()), "duration": info["duration"],
            "width": info["video"]["width"], "height": info["video"]["height"],
            "pix_fmt": info["video"]["pix_fmt"]}


def _identical(tmp: dict) -> bool:
    """True when the background env var had no effect (same picture on black and white)."""
    def corner(p):
        return subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-frames:v", "1", "-vf",
                               "crop=8:8:0:0,scale=1:1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                              capture_output=True).stdout
    return corner(tmp["black"]) == corner(tmp["white"])
