"""Remake benchmark (no Flow credits): plan a reference, simulate the generated clips, assemble.

A video model does not cut exactly when asked. Each multi-shot unit is simulated as a clip of the
planned length whose shots are real footage segments, with each cut moved by a random offset
(+-jitter s). Two assemblies are compared on the same clips:
  planned  - cut the clip at the planned beat times (how rea-video's assemble works)
  measured - Blade: find the real cuts in the clip, take each shot from the middle of its segment
Known truth (the simulated cut times) gives exact numbers:
  leaked_shots   - output shots that contain frames of a neighbour shot
  leaked_seconds - total length of those wrong frames
  length_error   - |output length - reference length|

    python benchmarks/remake_bench.py --refs ref/*.mp4 --footage src/*.mp4 --out runs/ --jitter 0.35 --seeds 3
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from blade_editor import ff, remake, render


def simulate(unit: dict, footage: list[str], durs: dict, rnd: random.Random, jitter: float, out: Path) -> tuple[str, list[float]]:
    """A fake 'generated clip' for one unit: one footage segment per beat, cuts moved by +-jitter."""
    g = unit["generate_s"]
    planned = [b["t0"] for b in unit["beats"]][1:]
    cuts = []
    for c in planned:
        lo = (cuts[-1] if cuts else 0.0) + 0.3
        cuts.append(round(min(g - 0.3, max(lo, c + rnd.uniform(-jitter, jitter))), 3))
    bounds = [0.0, *cuts, g]
    parts, filt = [], []
    for k in range(len(bounds) - 1):
        src = rnd.choice(footage)
        d = bounds[k + 1] - bounds[k]
        st = rnd.uniform(0, max(0.0, durs[src] - d - 0.5))
        parts += ["-ss", f"{st:.3f}", "-t", f"{d:.3f}", "-i", src]
        filt.append(f"[{k}:v]scale=540:960:force_original_aspect_ratio=increase,crop=540:960,setsar=1,fps=30,"
                    f"trim=duration={d:.4f},setpts=PTS-STARTPTS[v{k}]")
    n = len(bounds) - 1
    filt.append("".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[o]")
    path = out / f"{unit['id']}.mp4"
    ff.run([*parts, "-filter_complex", ";".join(filt), "-map", "[o]", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "18", str(path)])
    return str(path), cuts


def leaks(edl: dict, truth: dict[str, list[float]]) -> tuple[int, float]:
    """Output shots whose [in, out] crosses a true cut of their clip, and the wrong seconds."""
    n, sec = 0, 0.0
    for c in edl["clips"]:
        if "out" not in c:
            continue
        a0, a1 = c["in"], c["out"]
        bad = [x for x in truth.get(c["src"], []) if a0 + 1 / 30 < x < a1 - 1 / 30]
        if bad:
            n += 1
            mid = (a0 + a1) / 2
            x = min(bad, key=lambda v: abs(v - mid))
            sec += min(x - a0, a1 - x) / c.get("speed", 1.0)  # the smaller side is the wrong content
    return n, round(sec, 3)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refs", nargs="+", required=True)
    p.add_argument("--footage", nargs="+", required=True)
    p.add_argument("--out", default="runs/remake")
    p.add_argument("--jitter", type=float, default=0.35)
    p.add_argument("--seeds", type=int, default=3)
    a = p.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    durs = {f: ff.probe(f)["duration"] for f in a.footage}
    rows = []
    for ref in a.refs:
        plan = remake.plan(ref, out / "work")
        ref_len = plan["reference"]["duration"]
        for seed in range(a.seeds):
            rnd = random.Random(seed)
            d = out / f"{Path(ref).stem}_s{seed}"; d.mkdir(exist_ok=True)
            clips, truth = {}, {}
            for u in plan["units"]:
                if u["kind"] != "generate" or u["calls"] != 1:
                    continue  # long single shots and stills have no inner cuts
                path, cuts = simulate(u, a.footage, durs, rnd, a.jitter, d)
                clips[u["id"]], truth[path] = path, cuts
            plan_g = {**plan, "units": [u for u in plan["units"] if u["id"] in clips]}
            row = {"ref": Path(ref).name, "seed": seed, "shots": plan["reference"]["shots"],
                   "flow_calls": plan["flow_calls"], "one_call_per_shot": plan["one_call_per_shot"]}
            for mode in ("planned", "measured"):
                if mode == "planned":  # rea-video style: cut at the planned beat times
                    orig = remake.analyze.analyze_video
                    remake.analyze.analyze_video = lambda *x, **k: {"cuts": []}
                    try:
                        res = remake.assemble(plan_g, clips, str(d / f"{mode}.mp4"))
                    finally:
                        remake.analyze.analyze_video = orig
                else:
                    res = remake.assemble(plan_g, clips, str(d / f"{mode}.mp4"))
                n, sec = leaks(res["edl"], truth)
                length = render.timeline(render.normalize(json.loads(json.dumps(res["edl"]))))[-1]["end"]
                want = sum(sum(plan["shots"][i]["duration"] for i in u["shots"]) for u in plan_g["units"])
                row[mode] = {"leaked_shots": n, "leaked_seconds": sec, "length_error": round(abs(length - want), 3),
                             "units_measured": sum(1 for r in res["units"] if r["used"] != "planned"),
                             "units": len(res["units"])}
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    (out / "remake_results.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    tot = {m: {k: sum(r[m][k] for r in rows) for k in ("leaked_shots", "leaked_seconds")} for m in ("planned", "measured")}
    print("TOTAL", json.dumps({"runs": len(rows), **tot}))


if __name__ == "__main__":
    main()
