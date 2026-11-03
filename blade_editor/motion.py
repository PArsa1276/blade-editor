"""Motion graphics from Kinetograph. Blade Editor installs Kinetograph by itself on first use
into ~/.blade-editor/kinetograph (needs Node.js) and uses it for every project.

Kinetograph drops the alpha channel in every video codec, so the graphic is rendered twice,
on black and on white, and the exact alpha comes from the difference (difference matting).
The entry must take its background from the environment:
  <Composition background={process.env.BLADE_BG ?? "transparent"} ... />
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import ff


KG_HOME = Path(os.environ.get("BLADE_KG_HOME", Path.home() / ".blade-editor" / "kinetograph"))


def ensure_kinetograph(timeout: float = 900) -> list[str]:
    """Command prefix that runs the Kinetograph CLI; installs it once if it is missing."""
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node:
        raise RuntimeError("Node.js is not installed. Run the Blade Editor installer again (it installs "
                           "Node.js), or install the LTS version from https://nodejs.org")
    cli = KG_HOME / "node_modules" / "kinetograph" / "dist" / "cli.js"
    if not cli.exists():
        if not npm:
            raise RuntimeError("npm is missing; reinstall Node.js from https://nodejs.org")
        KG_HOME.mkdir(parents=True, exist_ok=True)
        if not (KG_HOME / "package.json").exists():
            (KG_HOME / "package.json").write_text('{"name": "blade-kinetograph", "private": true}')
        p = subprocess.run([npm, "install", "--no-fund", "--no-audit", "kinetograph"], cwd=KG_HOME,
                           capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0 or not cli.exists():
            raise RuntimeError(f"Could not install Kinetograph automatically:\n{(p.stderr or p.stdout)[-1500:]}")
    return [node, str(cli)]


def render(entry: str, out: str | Path, comp: str | None = None, props: dict | None = None,
           draft: bool = False, timeout: float = 1800, env: dict | None = None) -> dict:
    kg = ensure_kinetograph()
    entry_p = Path(entry).resolve()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = {bg: out.with_name(f"{out.stem}_{bg}.mov") for bg in ("black", "white")}
    for bg, path in tmp.items():
        cmd = [*kg, "render", str(entry_p), "-o", str(path), "--codec", "prores",
               "--prores-profile", "4444", "--concurrency", "4"]
        if comp:
            cmd += ["--comp", comp]
        if props:
            cmd += ["--props", json.dumps(props, ensure_ascii=False)]
        if draft:
            cmd.append("--draft")
        p = subprocess.run(cmd, cwd=entry_p.parent, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, **(env or {}), "BLADE_BG": bg})
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
                           "Set <Composition background={process.env.BLADE_BG ?? 'transparent'}>.")
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


TEMPLATES_DIR = Path(__file__).with_name("motion_templates")
TEMPLATES = {
    "title": "Big title: staggered spring words, accent bar, ring payoff, float, fast exit. props: text, subtitle, color, accent, size",
    "lower_third": "Name + role on a plate that grows from the side, light sweep, RTL-aware. props: name, role, color, accent, plate",
    "counter": "Number counting up to an exact value, tabular digits, pop + ring at landing. props: value, prefix, suffix, label, color, accent",
    "kinetic_words": "One big word per beat, key words punch in accent colour. props: text, beat (s per word), highlight, color, accent, size",
    "cta": "Call-to-action pill: spring rise, press + ring payoff, pulse. props: text, color, accent, textColor",
}


def template(name: str, out: str | Path, props: dict | None = None, width: int = 1080, height: int = 1920,
             fps: int = 30, duration: float = 3.0, draft: bool = False) -> dict:
    """Render a built-in motion template to a transparent ProRes 4444 clip."""
    import shutil
    if name not in TEMPLATES:
        raise ValueError(f"Unknown template '{name}'. Use: {', '.join(TEMPLATES)}")
    out = Path(out)
    work = out.parent / f".motion_{name}"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(TEMPLATES_DIR / name, work)
    (work / "public").mkdir(exist_ok=True)
    shutil.copy(Path(__file__).with_name("fonts") / "Vazirmatn-Black.ttf", work / "public")
    r = render(str(work / "index.tsx"), out, "Main", props, draft,
               env={"BLADE_W": str(int(width)), "BLADE_H": str(int(height)), "BLADE_FPS": str(int(fps)),
                    "BLADE_DUR": str(float(duration))})
    shutil.rmtree(work, ignore_errors=True)
    return {**r, "template": name}
