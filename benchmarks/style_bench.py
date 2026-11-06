"""Style benchmark: "edit my footage like this reference" - how close does Blade get?

For every reference: its style is measured (autoedit.style_from_reference), an auto_edit is made
from new footage with the reference's own music and length, and both videos are measured the
same way. Reported per metric: reference, output and the gap.

    python benchmarks/style_bench.py --refs ref/*.mp4 --footage-sets "a.mp4,b.mp4" "c.mp4,d.mp4" --out runs/style
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from blade_editor import analyze, autoedit, ff, render

KEYS = ("cuts_per_second", "median_shot_length", "cuts_on_beat_share", "flashes_per_second",
        "moving_camera_share", "shake_share")
COLOR = ("saturation", "warmth", "brightness", "contrast")


def measure(path: str) -> dict:
    a = analyze.analyze_video(path)
    s = a["summary"]
    out = {k: s.get(k) for k in KEYS}
    out.update(autoedit.color_profile(path))
    out["duration"] = round(a["file"]["duration"], 2)
    return out


def run(ref: str, sources: list[str], name: str, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    music = out / f"{Path(ref).stem}_music.wav"
    if not music.exists():
        ff.run(["-i", ref, "-vn", "-ac", "2", "-ar", "44100", str(music)])
    st = autoedit.style_from_reference(ref)["style"]
    dur = ff.probe(ref)["duration"]
    edl = autoedit.build_edl(sources, str(music), str(out / f"{name}.mp4"), st, duration=round(dur - 0.05, 2),
                             width=540, height=960)
    edl.pop("_meta")
    (out / f"{name}_edl.json").write_text(json.dumps(edl, indent=1))
    video = render.render(edl, out / "work")["output"]
    r, o = measure(ref), measure(video)
    gap = {}
    for k in KEYS + COLOR:
        if r.get(k) is None or o.get(k) is None:
            continue
        gap[k] = round(o[k] - r[k], 3)
    row = {"name": name, "ref": Path(ref).name, "style": {k: v for k, v in st.items() if k != "source"},
           "reference": r, "output": o, "gap": gap}
    with open(out / "style_results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refs", nargs="+", required=True)
    p.add_argument("--footage-sets", nargs="+", required=True, help="comma-separated files per set")
    p.add_argument("--out", default="runs/style")
    a = p.parse_args()
    for ref in a.refs:
        for k, fs in enumerate(a.footage_sets):
            row = run(str(Path(ref).resolve()), [str(Path(x).resolve()) for x in fs.split(",")],
                      f"{Path(ref).stem}_set{k + 1}", Path(a.out))
            print(json.dumps({"name": row["name"], "gap": row["gap"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
