"""Blade Editor benchmark: build an auto_edit, render it, and measure it against its own EDL.

The EDL is the ground truth: every clip start is a real cut and every flash effect is a real
flash. The script measures what analyze_video finds in the rendered file, and checks the
render itself (frozen frames, clips that run across a cut inside the source).

Usage (from the repo root):
    python benchmarks/bench.py --sources a.mp4 b.mp4 --music m.wav --style velocity \
        --duration 13.5 --name dance_104_velocity --out runs/ [--set flash=0 cut_every=2]
One JSON line per run is appended to runs/results.jsonl.
"""
from __future__ import annotations

import argparse
import copy
import json
import time
from pathlib import Path

import numpy as np

from blade_editor import analyze, audio, autoedit, ff, render

TOL_CUT = 0.07    # s: a detected cut within this of an EDL cut is a hit (same as cuts_on_beat_share)
TOL_FLASH = 0.10  # s


def _match(truth: list[float], found: list[float], tol: float) -> tuple[int, list[float], list[float]]:
    """One-to-one matching, nearest first. Returns hits, extra (found only), missed (truth only)."""
    pairs = sorted((abs(t - f), i, j) for i, t in enumerate(truth) for j, f in enumerate(found) if abs(t - f) <= tol)
    used_t, used_f = set(), set()
    for _, i, j in pairs:
        if i not in used_t and j not in used_f:
            used_t.add(i); used_f.add(j)
    extra = [round(found[j], 3) for j in range(len(found)) if j not in used_f]
    missed = [round(truth[i], 3) for i in range(len(truth)) if i not in used_t]
    return len(used_t), extra, missed


def _prf(hits: int, n_truth: int, n_found: int) -> dict:
    p = hits / n_found if n_found else 1.0
    r = hits / n_truth if n_truth else 1.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}


def frozen_runs(path: str) -> dict:
    frames, _ = ff.read_gray_frames(path, width=160, fps=30)
    d = np.abs(np.diff(frames.astype(np.float32), axis=0)).mean(axis=(1, 2)) < 0.3
    runs, k = [], 0
    for x in list(d) + [False]:
        if x:
            k += 1
        elif k:
            runs.append(k); k = 0
    return {"frozen_frames": int(sum(runs)), "frozen_runs_2plus": sum(1 for r in runs if r >= 2)}


def run(sources: list[str], music: str, style: str, duration: float, name: str, out: Path,
        overrides: dict | None = None, width: int = 540, height: int = 960) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    st = copy.deepcopy(autoedit.PRESETS[style])
    for k, v in (overrides or {}).items():
        if k in ("slow", "fast", "hold"):
            st["ramp"][k] = v
        else:
            st[k] = v
    t0 = time.time()
    edl = autoedit.build_edl(sources, music, str(out / f"{name}.mp4"), st, duration=duration,
                             width=width, height=height)
    meta = edl.pop("_meta")
    t_build = time.time() - t0
    (out / f"{name}_edl.json").write_text(json.dumps(edl, indent=1))
    t0 = time.time()
    res = render.render(edl, out / "work")
    t_render = time.time() - t0
    video = res["output"]

    # Ground truth from the EDL, in output time (the same timeline the renderer uses). A hard
    # cut is one time; a crossfade is a span (start of the overlap .. its end) and is measured
    # separately: a detected cut anywhere in the span (+- tolerance) counts as found.
    norm = render.normalize(json.loads(json.dumps(edl)))
    rows = render.timeline(norm)
    cuts = [r["start"] for r in rows[1:] if r["overlap"] == 0]
    fades = [(r["start"], r["start"] + r["overlap"]) for r in rows[1:] if r["overlap"] > 0]
    flashes = [rows[k]["start"] for k, c in enumerate(edl["clips"])
               if any(e.get("type") == "flash" for e in c.get("effects", []))]
    t0 = time.time()
    a = analyze.analyze_video(video)
    t_analyze = time.time() - t0
    in_fade = [x for x in a["cuts"] if any(s0 - TOL_CUT <= x <= s1 + TOL_CUT for s0, s1 in fades)]
    fades_found = sum(any(s0 - TOL_CUT <= x <= s1 + TOL_CUT for x in a["cuts"]) for s0, s1 in fades)
    hard_found = [x for x in a["cuts"] if x not in in_fade]
    hits, extra, missed = _match(cuts, hard_found, TOL_CUT)
    fh, fextra, fmissed = _match(flashes, a["flashes"], TOL_FLASH)
    beats = np.array(audio.analyze_beats(music, duration=duration + 2)["beats"])
    edl_on_beat = (float(np.mean([np.min(np.abs(beats - c)) <= TOL_CUT for c in cuts]))
                   if len(beats) and cuts else None)
    # Clips that run across a cut inside their source (Blade's own 30 fps source analysis).
    src_cuts = {s: analyze.analyze_video(s, include_audio=False)["cuts"] for s in set(sources)}
    crossing = []
    for c in edl["clips"]:
        a0 = c["in"]
        a1 = a0 + (sum(o for o, _ in c["ramp"]) if c.get("ramp") else (c["out"] - c["in"]))
        crossing += [[Path(c["src"]).name, round(a0, 2), x] for x in src_cuts[c["src"]] if a0 + 0.02 < x < a1 - 0.02]
    row = {
        "name": name, "style": style, "overrides": overrides or {}, "music": Path(music).name,
        "sources": [Path(s).name for s in sources], "bpm": meta.get("bpm"), "duration": duration,
        "edl_cuts": len(cuts), "found_cuts": len(hard_found), "cut_hits": hits,
        "extra_cuts": extra, "missed_cuts": missed, **{f"cut_{k}": v for k, v in _prf(hits, len(cuts), len(hard_found)).items()},
        "edl_crossfades": len(fades), "crossfades_found": fades_found,
        "cuts_on_beat_share": a["summary"].get("cuts_on_beat_share"), "edl_cuts_on_beat": edl_on_beat,
        "edl_flashes": len(flashes), "found_flashes": len(a["flashes"]), "flash_hits": fh,
        "extra_flashes": fextra, "missed_flashes": fmissed,
        **frozen_runs(video), "clips_crossing_source_cut": crossing,
        "seconds": {"build": round(t_build, 1), "render": round(t_render, 1), "analyze": round(t_analyze, 1)},
        "video": video,
    }
    with open(out / "results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sources", nargs="+", required=True)
    p.add_argument("--music", required=True)
    p.add_argument("--style", default="velocity")
    p.add_argument("--duration", type=float, default=13.5)
    p.add_argument("--name", required=True)
    p.add_argument("--out", default="runs")
    p.add_argument("--set", nargs="*", default=[], help="preset overrides, e.g. flash=0 cut_every=2 slow=0.3")
    a = p.parse_args()
    over = {k: json.loads(v) for k, v in (x.split("=", 1) for x in a.set)}
    row = run([str(Path(s).resolve()) for s in a.sources], str(Path(a.music).resolve()), a.style,
              a.duration, a.name, Path(a.out), over)
    print(json.dumps({k: v for k, v in row.items() if k != "video"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
