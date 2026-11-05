"""Build the Persian captions test sets from Google FLEURS fa_ir (test split, CC BY 4.0).

    python benchmarks/fleurs_fa.py OUT_DIR --music music140.wav

Streams the FLEURS archive and keeps only the first 60 recordings. Writes:
  set1: recordings 1-30, 0.6 s between sentences          -> set1.wav + set1_truth.json
  set2: recordings 1-30, 3-5 s gaps, every 3rd gap music    -> set2.wav + set2_truth.json + set2_gaps.json
  set3: recordings 31-60, 2-5 s gaps, every 3rd gap music   -> set3.wav + set3_truth.json + set3_gaps.json
Then score a transcript with benchmarks/captions_bench.py.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import subprocess
import tarfile
import urllib.request
from pathlib import Path

BASE = "https://huggingface.co/datasets/google/fleurs/resolve/main/data/fa_ir"


def _fetch(out: Path, n: int) -> list[str]:
    wav = out / "wav"; wav.mkdir(parents=True, exist_ok=True)
    have = sorted(p.name for p in wav.glob("*.wav"))
    if len(have) >= n:
        return []
    order = []
    with urllib.request.urlopen(f"{BASE}/audio/test.tar.gz") as r, tarfile.open(fileobj=r, mode="r|gz") as t:
        for m in t:
            if m.isfile() and m.name.endswith(".wav"):
                name = m.name.split("/")[-1]
                (wav / name).write_bytes(t.extractfile(m).read())
                order.append(name)
                if len(order) >= n:
                    break
    (out / "order.json").write_text(json.dumps(order))
    return order


def _build(out: Path, name: str, files: list[str], text: dict, gap, music: str | None, seed: int) -> None:
    rnd = random.Random(seed)
    inputs, filt, truth, gaps, t, n = [], [], [], [], 0.0, 0
    for k, f in enumerate(files):
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", str(out / "wav" / f)]))
        inputs += ["-i", str(out / "wav" / f)]
        filt.append(f"[{n}:a]aresample=16000,aformat=channel_layouts=mono[s{k}]"); n += 1
        truth.append({"start": round(t, 3), "end": round(t + dur, 3), "text": text[f]}); t += dur
        g = gap(rnd)
        if music and k % 3 == 2:
            inputs += ["-ss", f"{rnd.uniform(0, 10):.2f}", "-t", str(g), "-i", music]
            filt.append(f"[{n}:a]aresample=16000,aformat=channel_layouts=mono,volume=0.6[g{k}]"); n += 1
            gaps.append({"start": round(t, 3), "end": round(t + g, 3), "kind": "music"})
        else:
            filt.append(f"anullsrc=r=16000:cl=mono,atrim=duration={g}[g{k}]")
            gaps.append({"start": round(t, 3), "end": round(t + g, 3), "kind": "silence"})
        t += g
    filt.append("".join(f"[s{k}][g{k}]" for k in range(len(files))) + f"concat=n={2 * len(files)}:v=0:a=1[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "[out]",
                    str(out / f"{name}.wav")], check=True)
    (out / f"{name}_truth.json").write_text(json.dumps(truth, ensure_ascii=False), encoding="utf-8")
    (out / f"{name}_gaps.json").write_text(json.dumps(gaps))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out")
    p.add_argument("--music", help="music without vocals for the music gaps (sets 2 and 3)")
    a = p.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    order = _fetch(out, 60) or json.loads((out / "order.json").read_text())
    tsv = urllib.request.urlopen(f"{BASE}/test.tsv").read().decode("utf-8")
    text = {}
    for r in csv.reader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        text.setdefault(r[1], r[2])
    first, second = sorted(order[:30]), sorted(order[30:60])
    _build(out, "set1", first, text, lambda r: 0.6, None, 1)
    _build(out, "set2", first, text, lambda r: r.choice([3, 4, 5]), a.music, 5)
    _build(out, "set3", second, text, lambda r: r.choice([2, 3, 5]), a.music, 11)
    print("sets in", out)


if __name__ == "__main__":
    main()
