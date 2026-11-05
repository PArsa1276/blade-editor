"""Print a Persian Markdown table from a results.jsonl written by bench.py."""
import json
import sys


def main(path: str) -> None:
    rows = [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]
    print("| اجرا | سبک | BPM | کات EDL | اضافه | پیدانشده | F1 کات | روی ضرب (اندازه‌گیری) | فلش EDL / درست / غلط | فریم ثابت (خوشه ≥۲) | روی کات منبع | رندر (ث) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        fl = f"{r['edl_flashes']} / {r['flash_hits']} / {len(r['extra_flashes'])}"
        fade = f" + {r['crossfades_found']}/{r['edl_crossfades']} محو" if r.get("edl_crossfades") else ""
        print(f"| {r['name']} | {r['style']} | {r['bpm']} | {r['edl_cuts']}{fade} | {len(r['extra_cuts'])} | {len(r['missed_cuts'])} | "
              f"{r['cut_f1']} | {r['cuts_on_beat_share']} | {fl} | {r['frozen_runs_2plus']} | {len(r['clips_crossing_source_cut'])} | {r['seconds']['render']} |")
    n = len(rows)
    if n:
        f1 = sum(r["cut_f1"] for r in rows) / n
        ex = sum(len(r["extra_cuts"]) for r in rows); ms = sum(len(r["missed_cuts"]) for r in rows)
        tot = sum(r["edl_cuts"] for r in rows)
        print(f"\nمیانگین F1 کات: {f1:.3f} — کات اضافه در کل: {ex}، پیدانشده: {ms}، از {tot} کات EDL در {n} اجرا.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "runs/results.jsonl")
