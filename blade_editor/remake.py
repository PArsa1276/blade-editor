"""Remake a reference video without the user's footage: a production plan for Google Flow.

Ideas adapted from rea-video (Apache-2.0, github.com/JuneYaooo/rea-video, production.py), rebuilt
on Blade's own measurements:
- edit shots are facts (Blade's cut + crossfade detection); generation units are how the shots are
  made again: consecutive same-scene shots joined by hard cuts go into ONE Flow call (fewest calls by
  dynamic programming, within the video model's limits: rules S01/S02/S06);
- a unit that continues the same scene starts from the previous unit's last frame (continuity);
- shots too short to generate alone are generated longer and trimmed; shots longer than the
  model's limit are split, each part starting from the last frame of the part before.
Blade-specific: camera moves are measured (camera.measure), not guessed; frozen shots need no video
generation (an image + Blade's camera effect); the plan ends in a ready EDL that cuts the generated
clips to the reference's exact shot lengths. Claude, who can see the frames, writes the content
(subject, action, light) - no second vision model.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from . import analyze, camera, ff

# Google Flow, Omni 1.1 Flash: 3-10 s per clip. Several hard cuts in one clip stay reliable up to
# about 8 s (rea-video S06: "over ~10 s often fails"). Very short generations are unstable: make at
# least 4 s and trim. Omni 1.2 Flash (Nov 2026): 3-15 s in whole seconds and fewer unwanted cuts; how
# many planned cuts it keeps in one 15 s clip is not measured yet, so multi-shot clips stay <= 12 s
# (assemble measures the real cuts anyway).
LIMITS = {"omni-1.2-flash": {"min": 3.0, "max": 15.0, "multi_prefer": 12.0, "multi_max": 15.0, "unit_min": 4.0},
          "omni-1.1-flash": {"min": 3.0, "max": 10.0, "multi_prefer": 8.0, "multi_max": 10.0, "unit_min": 4.0},
          "veo": {"min": 4.0, "max": 8.0, "multi_prefer": 8.0, "multi_max": 8.0, "unit_min": 4.0}}
SAME_SCENE = 0.5  # Bhattacharyya distance of HSV histograms (rea-video default)


def _hsv_hist(path: str, t: float, tmp: Path) -> np.ndarray:
    f = ff.extract_frame(path, t, tmp / f"h_{t:.3f}.jpg", width=160)
    hsv = np.asarray(Image.open(f).convert("HSV"), dtype=np.int32).reshape(-1, 3)
    h, _ = np.histogramdd(hsv, bins=(18, 4, 4), range=((0, 256), (0, 256), (0, 256)))
    return (h / max(1.0, h.sum())).ravel()


def scene_distance(a: list[np.ndarray], b: list[np.ndarray]) -> float:
    """Smallest Bhattacharyya distance between any key frame of two shots (0 = same, 1 = unrelated)."""
    return min(float(np.sqrt(max(0.0, 1.0 - np.sqrt(x * y).sum()))) for x in a for y in b)


def camera_words(m: dict, dur: float) -> str:
    """Measured content motion -> camera language for a video prompt."""
    if len(m["x"]) < 3 or dur <= 0:
        return "static camera"
    dx, dy = float(m["x"][-1] - m["x"][0]), float(m["y"][-1] - m["y"][0])
    z = float(m["zoom"][-1] / max(m["zoom"][0], 1e-6))
    rot = float(m["rot"][-1] - m["rot"][0])
    vx = np.diff(m["x"]) * m["fps"]
    jitter = float(np.abs(np.diff(vx)).mean()) if len(vx) > 2 else 0.0
    words = []

    def speed(v: float) -> str:  # fraction of the frame per second
        return "slow" if v < 0.08 else ("fast" if v > 0.4 else "steady")
    if z > 1.04:
        words.append(f"{speed((z - 1) / dur)} push-in")
    elif z < 0.96:
        words.append(f"{speed((1 / z - 1) / dur)} pull-out")
    if abs(dx) > 0.05:  # content moves left -> camera pans right
        words.append(f"{speed(abs(dx) / dur)} pan {'right' if dx < 0 else 'left'}")
    if abs(dy) > 0.05:
        words.append(f"{speed(abs(dy) / dur)} tilt {'down' if dy < 0 else 'up'}")
    if abs(rot) > 3:
        words.append(f"camera roll {abs(rot):.0f} degrees {'clockwise' if rot > 0 else 'counter-clockwise'}")
    if np.abs(vx).max() > 1.5:
        words.append("whip")
    if jitter > 0.6:
        words.append("handheld shake")
    return ", ".join(words) or "static camera, locked off"


BEAT_MIN = 1.5  # each shot inside a multi-shot clip is generated at least this long (a usable middle)
MONTAGE = 2.0   # shots shorter than this may share a clip even across scenes ("Cut to:")
MAX_BEATS = 5   # cuts per clip the model follows well (blade-prompt: 3-5 beats)
MATCH = 0.6     # s: a measured cut this close to a planned one is that cut


def _gen_len(seg: list[dict], lim: dict) -> float:
    if len(seg) == 1:
        return min(lim["max"], max(seg[0]["duration"], lim["unit_min"]))
    return sum(max(r["duration"], BEAT_MIN) for r in seg)


def _split(run: list[dict], lim: dict, multi_shot: bool) -> list[list[dict]]:
    """Fewest clips (Flow calls), then avoid multi-shot clips past the preferred length
    (dynamic programming over the cut points)."""
    if not multi_shot:
        return [[r] for r in run]
    n = len(run)
    best, prev = [0.0] + [float("inf")] * n, [0] * (n + 1)
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            seg = run[i:j]
            g = _gen_len(seg, lim)
            if len(seg) > 1 and (g > lim["multi_max"] or len(seg) > MAX_BEATS):
                break
            cost = 1.0 + (0.4 if len(seg) > 1 and g > lim["multi_prefer"] else 0.0)
            if best[i] + cost < best[j]:
                best[j], prev[j] = best[i] + cost, i
    out, j = [], n
    while j:
        out.append(run[prev[j]:j])
        j = prev[j]
    return out[::-1]


def plan(path: str, work: Path, model: str = "omni-1.2-flash", aspect: str | None = None,
         multi_shot: bool = True, a: dict | None = None) -> dict:
    if model not in LIMITS:
        raise ValueError(f"Unknown model '{model}'. Use: {', '.join(LIMITS)}")
    lim = LIMITS[model]
    work.mkdir(parents=True, exist_ok=True)
    info = ff.probe(path)
    w, h = info.get("width") or 1080, info.get("height") or 1920
    aspect = aspect or ("9:16" if h > w else "16:9")
    a = a or analyze.analyze_video(path)
    fades = a.get("dissolves", [])
    shots = []
    for k, sh in enumerate(a["shots"]):
        s0, s1 = sh["start"], sh["end"]
        row = {"index": k, "start": s0, "end": s1, "duration": sh["duration"],
               "transition_in": "crossfade" if any(abs(s0 - f) < 0.05 for f in fades) else ("cut" if k else "start"),
               "camera": "static camera"}
        if sh["duration"] >= 0.3:
            m = camera.measure(path, s0, s1)
            row["camera"] = camera_words(m, sh["duration"])
            if not row["camera"].startswith("static"):
                row["camera_keys"] = camera.keyframes(m, 10)  # to replay the move on a still (camera effect)
        row["frozen"] = sh.get("activity", 1.0) < 0.3 and row["camera"].startswith("static")
        row["_sig"] = [_hsv_hist(path, t, work) for t in (s0 + 0.04, max(s0 + 0.04, s1 - 0.08))]
        shots.append(row)
    for p, r in zip(shots, shots[1:]):
        r["same_scene_as_previous"] = scene_distance(p["_sig"], r["_sig"]) <= SAME_SCENE

    # Shots that may share one clip: joined by a hard cut, and either the same scene (one continuous
    # look) or both short (a montage: "Cut to:" a new place). Frozen shots need no video at all.
    runs, cur = [], []
    for r in shots:
        if r["frozen"]:
            runs += ([cur] if cur else []) + [[r]]
            cur = []
            continue
        joinable = cur and r["transition_in"] == "cut" and (
            r["same_scene_as_previous"] or (cur[-1]["duration"] < MONTAGE and r["duration"] < MONTAGE))
        if cur and not joinable:
            runs.append(cur)
            cur = []
        cur.append(r)
    if cur:
        runs.append(cur)

    units, calls = [], 0
    for run in runs:
        for seg in ([run] if run[0]["frozen"] else _split(run, lim, multi_shot)):
            dur = round(sum(r["duration"] for r in seg), 3)
            u = {"id": f"G{len(units) + 1}", "shots": [r["index"] for r in seg], "start": seg[0]["start"],
                 "end": seg[-1]["end"], "duration": dur}
            if seg[0]["frozen"]:
                u.update(kind="still", calls=0, how="the shot does not move: one still image held, no video "
                                                    "generation (flow_generate_image or the user's picture)")
                units.append(u)
                continue
            parts = int(-(-dur // lim["max"])) if len(seg) == 1 and dur > lim["max"] else 1
            gen = float(np.ceil(dur / parts)) if parts > 1 else float(np.ceil(_gen_len(seg, lim)))
            gen = min(lim["max"], max(lim["min"], gen))
            beats, acc = [], 0.0
            for r in seg:
                g = gen if len(seg) == 1 else max(r["duration"], BEAT_MIN)
                beats.append({"t0": round(acc, 2), "t1": round(acc + g, 2), "keep": r["duration"] if parts == 1 else
                              round(dur / parts, 3), "camera": r["camera"], "subject": "", "action": "",
                              "setting": "", "lighting": "", "ref_shot": r["index"]})
                acc += g
            beats[-1]["t1"] = round(gen, 2)  # the last beat runs to the clip's end
            prev = units[-1] if units else None
            cont = None
            if prev and prev.get("kind") == "generate" and seg[0].get("same_scene_as_previous") \
                    and seg[0]["transition_in"] == "cut":
                cont = f"first_frame: the last frame of {prev['id']}'s clip ('<{prev['id']}>@end') - the action goes on"
            u.update(kind="generate", calls=parts, generate_s=gen, takes="cuts" if len(seg) > 1 else "single",
                     beats=beats, continuity=cont,
                     look_at=f"view_frames(reference, {seg[0]['start']:.2f}, {seg[-1]['end']:.2f}, "
                             f"count={min(12, 3 * len(seg))})")
            if parts > 1:
                u["note"] = (f"{dur:.1f}s is over the {lim['max']:.0f}s limit: {parts} clips of {gen:.0f}s, each "
                             "starting from the last frame of the clip before")
            calls += parts
            units.append(u)
    for r in shots:
        r.pop("_sig", None)
    return {
        "reference": {"path": path, "duration": round(info["duration"], 3), "aspect": aspect,
                      "shots": len(shots), "bpm": (a.get("audio") or {}).get("bpm")},
        "model": model, "shots": shots, "units": units, "flow_calls": calls,
        "one_call_per_shot": sum(len(u["shots"]) for u in units if u["kind"] == "generate"),
    }


def _take(a0: float, a1: float, keep: float) -> tuple[float, float, float]:
    """(in, out, speed) for `keep` seconds from the middle of [a0, a1]; slows down (>= 0.5x) when the
    segment is too short, so the shot keeps the reference's length."""
    a0, a1 = a0 + 0.04, a1 - 0.04  # stay clear of the cut frames
    room = a1 - a0
    if room >= keep:
        mid = (a0 + a1) / 2
        return round(mid - keep / 2, 3), round(mid + keep / 2, 3), 1.0
    speed = max(0.5, room / keep)
    use = keep * speed
    mid = (a0 + a1) / 2
    return round(mid - use / 2, 3), round(mid + use / 2, 3), round(speed, 3)


def assemble(p: dict, clips: dict[str, str], out_path: str, music: str | None = None) -> dict:
    """EDL from the generated clips: each shot is cut from ITS segment of the clip. The cuts inside a
    clip are measured (video models do not cut exactly when asked); when their number does not match
    the plan, the planned beat times are used and the unit is reported."""
    shots = {r["index"]: r for r in p["shots"]}
    edl_clips, report = [], []
    for u in p["units"]:
        if u["kind"] == "still":
            src = clips.get(u["id"])
            if not src:
                raise ValueError(f"{u['id']}: give the still image for shots {u['shots']}")
            edl_clips.append({"src": src, "duration": u["duration"]})
            continue
        if u["calls"] > 1:
            for k in range(u["calls"]):
                src = clips.get(f"{u['id']}.{k + 1}")
                if not src:
                    raise ValueError(f"{u['id']}.{k + 1}: missing clip")
                d = ff.probe(src)["duration"]
                i0, i1, sp = _take(0.0, d, u["duration"] / u["calls"])
                edl_clips.append({"src": src, "in": i0, "out": i1, **({"speed": sp} if sp < 1 else {})})
            continue
        src = clips.get(u["id"])
        if not src:
            raise ValueError(f"{u['id']}: missing clip")
        d = ff.probe(src)["duration"]
        f = d / max(u["generate_s"], 1e-6)  # the clip's real length can differ a little from the plan
        bounds = [b["t0"] * f for b in u["beats"]] + [d]
        if len(u["shots"]) > 1:
            # Each planned cut takes the nearest measured cut within MATCH s (one each, in order);
            # a cut the model did not make (or the detector missed) keeps its planned time.
            found = [c for c in analyze.analyze_video(src, include_audio=False)["cuts"] if 0.2 < c < d - 0.2]
            hit = 0
            for k in range(1, len(bounds) - 1):
                near = [c for c in found if abs(c - bounds[k]) <= MATCH and c > bounds[k - 1] + 0.2]
                if near:
                    c = min(near, key=lambda x: abs(x - bounds[k]))
                    found.remove(c)
                    bounds[k], hit = c, hit + 1
            want = len(u["shots"]) - 1
            report.append({"unit": u["id"], "cuts_expected": want, "cuts_matched": hit,
                           "used": "measured" if hit == want else ("partly measured" if hit else "planned")})
        for k, (b, i) in enumerate(zip(u["beats"], u["shots"])):
            i0, i1, sp = _take(bounds[k], bounds[k + 1], b["keep"])
            c = {"src": src, "in": i0, "out": i1, **({"speed": sp} if sp < 1 else {})}
            if shots[i]["transition_in"] == "crossfade":
                c["transition"] = {"type": "fade", "dur": 0.4}
            edl_clips.append(c)
    aspect = p["reference"]["aspect"]
    edl = {"output": {"path": out_path, "width": 1080 if aspect == "9:16" else 1920,
                      "height": 1920 if aspect == "9:16" else 1080, "fps": 30, "fit": "cover"},
           "clips": edl_clips}
    if music:
        edl["audio"] = {"music": music, "keep_clip_audio": False}
    return {"edl": edl, "units": report}
