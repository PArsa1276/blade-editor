"""Render an edit decision list (EDL) to a finished video with ffmpeg.

Pipeline: each clip -> normalized segment (cached) -> join with cuts/transitions ->
global effects -> text (ASS) -> music + clip audio + sfx mix -> final encode.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from . import effects, ff, sfx, text

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
CUSTOM_TRANSITIONS = {"cut", "flash", "zoom", "glitch", "whip"}


def _num(v, default):
    return default if v is None else float(v)


def _atempo(speed: float) -> list[str]:
    chain, s = [], speed
    while s > 2.0:
        chain.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        chain.append("atempo=0.5")
        s /= 0.5
    chain.append(f"atempo={s:.5f}")
    return chain


def _fit_graph(fit: str, W: int, H: int, focus: tuple[float, float], src: str, dst: str) -> str:
    fx, fy = focus
    cover = (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
             f"crop={W}:{H}:x='(iw-{W})*{fx:.3f}':y='(ih-{H})*{fy:.3f}'")
    contain = f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos"
    if fit == "cover":
        return f"[{src}]{cover},setsar=1[{dst}]"
    if fit == "contain":
        return f"[{src}]{contain},pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1[{dst}]"
    if fit == "blur":
        return (f"[{src}]split[fb1][fb2];[fb1]{cover},gblur=sigma=40,eq=brightness=-0.12[fbg];"
                f"[fb2]{contain}[ffg];[fbg][ffg]overlay=(W-w)/2:(H-h)/2,setsar=1[{dst}]")
    raise ValueError(f"Unknown fit '{fit}'. Use cover, contain or blur.")


def normalize(edl: dict) -> dict:
    """Fill defaults, check sources and compute each clip's output duration."""
    out = dict(edl.get("output") or {})
    out.setdefault("width", 1080)
    out.setdefault("height", 1920)
    out.setdefault("fps", 30)
    out.setdefault("fit", "cover")
    out.setdefault("crf", 18)
    out.setdefault("preset", "medium")
    if not out.get("path"):
        raise ValueError("output.path is required.")
    out["width"] = int(out["width"]) // 2 * 2
    out["height"] = int(out["height"]) // 2 * 2
    clips = []
    if not edl.get("clips"):
        raise ValueError("The EDL has no clips.")
    for i, c in enumerate(edl["clips"]):
        c = dict(c)
        src = c.get("src")
        if not src:
            raise ValueError(f"clip {i}: src is required.")
        if not str(src).startswith("color:") and not Path(src).exists():
            raise ValueError(f"clip {i}: file not found: {src}")
        is_image = Path(str(src)).suffix.lower() in IMAGE_EXT or str(src).startswith("color:")
        c["_image"] = is_image
        c["speed"] = _num(c.get("speed"), 1.0)
        if c["speed"] <= 0:
            raise ValueError(f"clip {i}: speed must be > 0.")
        c["in"] = _num(c.get("in"), 0.0)
        if is_image:
            if c.get("duration") is None:
                raise ValueError(f"clip {i}: an image or color clip needs 'duration'.")
            c["_src_dur"] = float(c["duration"])
            c["_has_audio"] = False
        else:
            info = ff.probe(src)
            if not info["video"]:
                raise ValueError(f"clip {i}: {src} has no video stream.")
            if c.get("out") is not None:
                c["_src_dur"] = float(c["out"]) - c["in"]
            elif c.get("duration") is not None:
                c["_src_dur"] = float(c["duration"]) * c["speed"]
            else:
                c["_src_dur"] = info["duration"] - c["in"]
            if c["in"] + c["_src_dur"] > info["duration"] + 0.05:
                raise ValueError(f"clip {i}: in+length ({c['in'] + c['_src_dur']:.2f}s) is past the "
                                 f"end of {Path(src).name} ({info['duration']:.2f}s).")
            c["_has_audio"] = bool(info["audio"])
        if c["_src_dur"] <= 0.02:
            raise ValueError(f"clip {i}: the clip length must be positive.")
        c["_dur"] = c["_src_dur"] / c["speed"]
        c.setdefault("effects", [])
        effects.validate(c["effects"])
        tr = c.get("transition") or {"type": "cut"}
        if isinstance(tr, str):
            tr = {"type": tr}
        tr.setdefault("dur", 0.3)
        c["transition"] = tr
        clips.append(c)

    # Custom transitions are effects at the head of the clip.
    for c in clips:
        t = c["transition"]["type"]
        if t == "flash":
            c["effects"].append({"type": "flash", "at": 0, "dur": 0.18, "amount": 0.9})
        elif t == "zoom":
            c["effects"].append({"type": "zoom_punch", "at": 0, "dur": 0.3, "amount": 0.25})
        elif t == "glitch":
            c["effects"].append({"type": "glitch", "at": 0, "dur": 0.2, "amount": 1.0})
        elif t == "whip":
            c["effects"] += [{"type": "blur", "at": 0, "dur": 0.12, "amount": 18},
                             {"type": "shake", "at": 0, "dur": 0.2, "amount": 30}]
    edl = dict(edl)
    edl["output"], edl["clips"] = out, clips
    edl.setdefault("texts", [])
    edl.setdefault("global_effects", [])
    effects.validate(edl["global_effects"])
    edl.setdefault("sfx", [])
    edl.setdefault("audio", {})
    return edl


def timeline(edl: dict) -> list[dict]:
    """Output start/end of every clip after transitions overlap."""
    t, rows = 0.0, []
    for i, c in enumerate(edl["clips"]):
        tr = c["transition"]
        overlap = float(tr["dur"]) if i and tr["type"] not in CUSTOM_TRANSITIONS else 0.0
        overlap = min(overlap, c["_dur"] * 0.5, rows[-1]["duration"] * 0.5) if i else 0.0
        start = t - overlap
        rows.append({"index": i, "start": round(start, 3), "end": round(start + c["_dur"], 3),
                     "duration": round(c["_dur"], 3), "overlap": round(overlap, 3)})
        t = start + c["_dur"]
    return rows


def _segment(c: dict, out: dict, seg_dir: Path, scale: float) -> Path:
    W = int(out["width"] * scale) // 2 * 2
    H = int(out["height"] * scale) // 2 * 2
    fps = out["fps"]
    key = json.dumps({k: v for k, v in c.items() if not k.startswith("_") or k in ("_dur",)},
                     sort_keys=True, default=str) + f"{W}x{H}@{fps}"
    src = c["src"]
    if not str(src).startswith("color:"):
        st = Path(src).stat()
        key += f"{st.st_mtime_ns}:{st.st_size}"
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    seg = seg_dir / f"seg_{h}.mkv"
    if seg.exists():
        return seg

    D = c["_dur"]
    args: list[str] = []
    if str(src).startswith("color:"):
        args += ["-f", "lavfi", "-i", f"color=c={src[6:]}:s={W}x{H}:r={fps}:d={D:.4f}"]
    elif c["_image"]:
        args += ["-loop", "1", "-framerate", str(fps), "-t", f"{D:.4f}", "-i", src]
    else:
        args += ["-ss", f"{c['in']:.4f}", "-t", f"{c['_src_dur']:.4f}", "-i", src]
    args += ["-f", "lavfi", "-t", f"{D:.4f}", "-i", "anullsrc=r=48000:cl=stereo"]

    v = ["setpts=PTS-STARTPTS"]
    if c.get("reverse") and not c["_image"]:
        v.append("reverse")
    if c["speed"] != 1.0:
        v.append(f"setpts=PTS/{c['speed']:.5f}")
    v.append(f"fps={fps}")
    graph = [f"[0:v]{','.join(v)}[v0]"]
    fit = c.get("fit") or out["fit"]
    focus = tuple(c.get("focus") or (0.5, 0.5))
    graph.append(_fit_graph(fit, W, H, focus, "v0", "v1"))
    post = effects.grade(c.get("grade") or out.get("grade"))
    scaled = [dict(e, amount=e.get("amount")) for e in c["effects"]]
    post += effects.motion_chain(scaled, W, H, D)
    post += effects.look_chain(scaled, W, H, D)
    post += ["tpad=stop_mode=clone:stop_duration=1", f"trim=duration={D:.4f}",
             "setpts=PTS-STARTPTS", "format=yuv420p"]
    graph.append(f"[v1]{','.join(post)}[vout]")

    use_audio = c["_has_audio"] and not c.get("mute")
    if use_audio:
        a = ["asetpts=PTS-STARTPTS"]
        if c.get("reverse"):
            a.append("areverse")
        if c["speed"] != 1.0:
            a += _atempo(c["speed"])
        a += [f"volume={_num(c.get('volume'), 1.0):.3f}",
              "aformat=sample_rates=48000:channel_layouts=stereo", "apad", f"atrim=duration={D:.4f}"]
        graph.append(f"[0:a]{','.join(a)}[aout]")
    else:
        graph.append(f"[1:a]atrim=duration={D:.4f}[aout]")

    ff.run([*args, "-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-g", str(int(fps)),
            "-c:a", "pcm_s16le", "-shortest", str(seg)])
    return seg


def render(edl: dict, work_dir: str | Path, preview: bool = False) -> dict:
    """Render the EDL. With preview=True, render at half size and fast settings."""
    t0 = time.time()
    edl = normalize(edl)
    out = edl["output"]
    work = Path(work_dir)
    seg_dir = work / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    scale = 0.5 if preview else 1.0
    W = int(out["width"] * scale) // 2 * 2
    H = int(out["height"] * scale) // 2 * 2

    segs = [_segment(c, out, seg_dir, scale) for c in edl["clips"]]
    rows = timeline(edl)
    total = rows[-1]["end"]

    args: list[str] = []
    for s in segs:
        args += ["-i", str(s)]
    graph: list[str] = []
    for i in range(len(segs)):
        graph.append(f"[{i}:v]setpts=PTS-STARTPTS,fps={out['fps']},format=yuv420p,settb=AVTB[sv{i}]")
        graph.append(f"[{i}:a]asetpts=PTS-STARTPTS[sa{i}]")
    cur_v, cur_a = "sv0", "sa0"
    cur_len = rows[0]["duration"]
    for i in range(1, len(segs)):
        tr = edl["clips"][i]["transition"]
        ov = rows[i]["overlap"]
        if ov > 0:
            graph.append(f"[{cur_v}][sv{i}]xfade=transition={tr['type']}:duration={ov:.4f}:"
                         f"offset={cur_len - ov:.4f}[xv{i}]")
            graph.append(f"[{cur_a}][sa{i}]acrossfade=d={ov:.4f}[xa{i}]")
        else:
            graph.append(f"[{cur_v}][{cur_a}][sv{i}][sa{i}]concat=n=2:v=1:a=1[xv{i}][xa{i}]")
        cur_v, cur_a = f"xv{i}", f"xa{i}"
        cur_len = cur_len - ov + rows[i]["duration"]

    # Global effects, then text.
    vpost = ["settb=AVTB", "setpts=PTS-STARTPTS"]
    vpost += effects.grade(out.get("global_grade"))
    vpost += effects.motion_chain(edl["global_effects"], W, H, total)
    vpost += effects.look_chain(edl["global_effects"], W, H, total)
    if edl["texts"]:
        ass = text.write_ass(edl["texts"], W, H, work / ("preview.ass" if preview else "final.ass"))
        vpost.append(f"ass=filename='{_fesc(ass)}':fontsdir='{_fesc(text.FONTS_DIR)}':shaping=complex")
    vpost += ["format=yuv420p"]
    graph.append(f"[{cur_v}]{','.join(vpost)}[vfinal]")

    # Audio mix.
    aud = edl["audio"] or {}
    mix_inputs: list[str] = []
    n_in = len(segs)
    keep_clip = aud.get("keep_clip_audio", not aud.get("music"))
    clip_vol = _num(aud.get("clip_audio_volume"), 1.0 if not aud.get("music") else 0.35)
    graph.append(f"[{cur_a}]volume={clip_vol if keep_clip else 0:.3f},asetpts=PTS-STARTPTS[aclip]")
    if aud.get("music"):
        if not Path(aud["music"]).exists():
            raise ValueError(f"Music file not found: {aud['music']}")
        args += ["-ss", f"{_num(aud.get('music_start'), 0.0):.3f}", "-i", aud["music"]]
        fo = _num(aud.get("fade_out"), 0.8)
        fi = _num(aud.get("fade_in"), 0.0)
        mchain = ["aformat=sample_rates=48000:channel_layouts=stereo", "asetpts=PTS-STARTPTS",
                  f"atrim=duration={total:.4f}", f"volume={_num(aud.get('volume'), 1.0):.3f}"]
        if fi > 0:
            mchain.append(f"afade=t=in:d={fi:.3f}")
        if fo > 0:
            mchain.append(f"afade=t=out:st={max(0, total - fo):.3f}:d={fo:.3f}")
        if aud.get("duck") and keep_clip:
            graph.append(f"[{n_in}:a]{','.join(mchain)}[mus0]")
            graph.append("[aclip]asplit[aclip][akey]")
            graph.append("[mus0][akey]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[mus]")
        else:
            graph.append(f"[{n_in}:a]{','.join(mchain)}[mus]")
        mix_inputs.append("[mus]")
        n_in += 1
    mix_inputs.insert(0, "[aclip]")
    for j, s in enumerate(edl["sfx"]):
        fpath = s.get("file") or str(sfx.make(s.get("kind", "whoosh"), seg_dir, s.get("dur")))
        if not Path(fpath).exists():
            raise ValueError(f"SFX file not found: {fpath}")
        args += ["-i", fpath]
        ms = int(max(0.0, float(s["at"])) * 1000)
        graph.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                     f"volume={_num(s.get('volume'), 0.8):.3f},adelay={ms}|{ms}[sfx{j}]")
        mix_inputs.append(f"[sfx{j}]")
        n_in += 1
    graph.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0:duration=first,"
                 f"atrim=duration={total:.4f}"
                 + (",loudnorm=I=-14:TP=-2:LRA=11,aresample=48000" if aud.get("normalize", True) else "")
                 + ",alimiter=limit=0.79:level=0[afinal]")

    final = Path(out["path"])
    if preview:
        final = work / f"preview_{final.stem}.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    venc = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26"] if preview else
            ["-c:v", "libx264", "-preset", out["preset"], "-crf", str(out["crf"]),
             "-profile:v", "high", "-pix_fmt", "yuv420p"])
    graph_file = work / ("preview_graph.txt" if preview else "final_graph.txt")
    graph_file.write_text(";\n".join(graph), encoding="utf-8")
    ff.run([*args, "-filter_complex_script", str(graph_file), "-map", "[vfinal]", "-map", "[afinal]",
            *venc, "-r", str(out["fps"]), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-t", f"{total:.4f}", str(final)])
    info = ff.probe(final)
    return {"output": str(final.resolve()), "duration": round(info["duration"], 3),
            "width": info["video"]["width"], "height": info["video"]["height"],
            "size_mb": round(info["size_bytes"] / 1e6, 2), "timeline": rows,
            "render_seconds": round(time.time() - t0, 1), "preview": preview}


def _fesc(p: str | Path) -> str:
    """Escape a path for use inside a filtergraph option value."""
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
