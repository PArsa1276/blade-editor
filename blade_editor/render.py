"""Render an edit decision list (EDL) to a finished video with ffmpeg.

Pipeline: each clip -> normalized segment (cached) -> join with cuts/transitions ->
global effects -> text (ASS) -> music + clip audio + sfx mix -> final encode.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np

from . import camera, effects, emoji, ff, sfx, text

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


def _stabilize(src: str, start: float, length: float, cmd_file: Path, margin: float = 0.08) -> list[str]:
    """Translation stabilizer: measure camera motion, smooth the path, crop against the shake."""
    from .analyze import _phase_shift

    info = ff.probe(src)["video"]
    frames, fps = ff.read_gray_frames(src, width=320, start=start, duration=length)
    if len(frames) < 3:
        return []
    f = frames.astype(np.float32)
    win = np.outer(np.hanning(f.shape[1]), np.hanning(f.shape[2])).astype(np.float32)
    step = np.array([[0.0, 0.0]] + [_phase_shift(f[i - 1], f[i], win)[:2] for i in range(1, len(f))])
    path = np.cumsum(step, axis=0)
    k = max(3, int(fps * 0.5)) | 1
    pad = np.pad(path, ((k // 2, k // 2), (0, 0)), mode="edge")
    smooth = np.stack([np.convolve(pad[:, j], np.ones(k) / k, mode="valid") for j in range(2)], axis=1)
    scale = info["width"] / 320.0
    W, H = info["width"], info["height"]
    cw, ch = int(W * (1 - 2 * margin)) // 2 * 2, int(H * (1 - 2 * margin)) // 2 * 2
    mx, my = (W - cw) / 2, (H - ch) / 2
    lines = []
    for i, (px, py) in enumerate((path - smooth) * scale):
        x = min(max(mx + px, 0), W - cw)
        y = min(max(my + py, 0), H - ch)
        # Half a frame early, so the command is due on its own frame (not the next one).
        lines.append(f"{max(0.0, (i - 0.5) / fps):.4f} crop x {x:.1f}, crop y {y:.1f};")
    cmd_file.write_text("\n".join(lines), encoding="utf-8")
    return [f"sendcmd=f='{_fesc(cmd_file)}'", f"crop={cw}:{ch}:{mx:.0f}:{my:.0f}", f"scale={W}:{H}"]


def _auto_focus(src: str, start: float, length: float) -> list[float]:
    """Crop centre that follows where the picture moves (static for the clip)."""
    frames, _ = ff.read_gray_frames(src, width=160, fps=6, start=start, duration=length)
    if len(frames) < 2:
        return [0.5, 0.5]
    m = np.abs(np.diff(frames.astype(np.float32), axis=0)).mean(axis=0)
    if m.sum() < 1e-3:
        return [0.5, 0.5]
    ys, xs = np.indices(m.shape)
    return [round(float((m * xs).sum() / m.sum() / (m.shape[1] - 1)), 3),
            round(float((m * ys).sum() / m.sum() / (m.shape[0] - 1)), 3)]


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
    Path(out["path"]).parent.mkdir(parents=True, exist_ok=True)
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
            c["_has_audio"] = bool(info["audio"])
            c["_file_dur"] = info["duration"]
        if c["_src_dur"] <= 0.02:
            raise ValueError(f"clip {i}: the clip length must be positive.")
        if c.get("ramp"):
            # ramp: [[source_seconds, speed], ...] played in order from `in`.
            ramp = [(float(a), float(b)) for a, b in c["ramp"]]
            if any(a <= 0 or b <= 0 for a, b in ramp) or c["_image"]:
                raise ValueError(f"clip {i}: ramp needs a video and positive [seconds, speed] pairs.")
            c["_src_dur"] = sum(a for a, _ in ramp)
            c["_dur"] = sum(a / b for a, b in ramp)
        else:
            c["_dur"] = c["_src_dur"] / c["speed"]
        # Checked after the ramp length is known (a ramp longer than the file froze the picture).
        if not c["_image"] and c["in"] + c["_src_dur"] > c["_file_dur"] + 0.05:
            raise ValueError(f"clip {i}: in+length ({c['in'] + c['_src_dur']:.2f}s) is past the end of "
                             f"{Path(src).name} ({c['_file_dur']:.2f}s). Shorten out/duration or the ramp "
                             f"pieces (their source seconds must add up to at most "
                             f"{c['_file_dur'] - c['in']:.2f}s).")
        if c.get("focus") == "auto" and not c["_image"]:
            c["focus"] = _auto_focus(src, c["in"], c["_src_dur"])
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
    # Put every clip end on a whole frame of the output timeline. Rounding each clip on its own
    # lost ~0.5 frame per clip, so the picture drifted ahead of the music over many short cuts.
    fps, exact, frames = float(out["fps"]), 0.0, 0
    for c in clips:
        exact += c["_dur"]
        end = round(exact * fps)
        c["_dur"] = max(1, end - frames) / fps
        frames = end
        c["transition"]["dur"] = round(float(c["transition"]["dur"]) * fps) / fps
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
    if c.get("stabilize") and not c["_image"]:
        v += _stabilize(src, c["in"], c["_src_dur"], seg.with_suffix(".cmd"))
    if c.get("reverse") and not c["_image"]:
        v.append("reverse")
    if c["speed"] != 1.0:
        v.append(f"setpts=PTS/{c['speed']:.5f}")
    v.append(f"fps={fps}")
    graph = [f"[0:v]{','.join(v)}[v0]"]
    if c.get("ramp"):
        n, t, parts = len(c["ramp"]), 0.0, []
        # Keep stabilize/reverse from `v` (drop its final fps; the ramp sets fps after concat).
        graph = [f"[0:v]{','.join(v[:-1])},split={n}" + "".join(f"[r{k}]" for k in range(n))]
        for k, (ln, sp) in enumerate(c["ramp"]):
            graph.append(f"[r{k}]trim=start={t:.4f}:duration={float(ln):.4f},setpts=(PTS-STARTPTS)/{float(sp):.5f}[q{k}]")
            parts.append(f"[q{k}]")
            t += float(ln)
        graph.append(f"{''.join(parts)}concat=n={n}:v=1:a=0,fps={fps}[v0]")
    fit = c.get("fit") or out["fit"]
    focus = tuple(c.get("focus") or (0.5, 0.5))
    graph.append(_fit_graph(fit, W, H, focus, "v0", "v1"))
    post = effects.grade(c.get("grade") or out.get("grade"))
    scaled = [dict(e, amount=e.get("amount")) for e in c["effects"]]
    for e in scaled:
        if e.get("type") == "camera":
            post += camera.camera_chain(e["keys"], W, H, e.get("ease", "smooth"))
    post += effects.motion_chain(scaled, W, H, D)
    post += effects.look_chain(scaled, W, H, D)
    post += [f"tpad=stop_mode=clone:stop_duration={D:.4f}", f"trim=duration={D:.4f}",
             "setpts=PTS-STARTPTS", "format=yuv420p"]
    graph.append(f"[v1]{','.join(post)}[vout]")

    use_audio = c["_has_audio"] and not c.get("mute")
    if use_audio:
        a = ["asetpts=PTS-STARTPTS"]
        if c.get("reverse"):
            a.append("areverse")
        if c.get("ramp"):
            # Same pieces as the video ramp, each time-stretched (pitch kept) and joined.
            n, t = len(c["ramp"]), 0.0
            graph.append(f"[0:a]asetpts=PTS-STARTPTS,asplit={n}" + "".join(f"[ra{k}]" for k in range(n)))
            for k, (ln, sp) in enumerate(c["ramp"]):
                graph.append(f"[ra{k}]atrim=start={t:.4f}:duration={float(ln):.4f},asetpts=PTS-STARTPTS,"
                             f"{','.join(_atempo(float(sp)))}[qa{k}]")
                t += float(ln)
            graph.append("".join(f"[qa{k}]" for k in range(n)) + f"concat=n={n}:v=0:a=1[ramped]")
            a = ["asetpts=PTS-STARTPTS"]
        elif c["speed"] != 1.0:
            a += _atempo(c["speed"])
        a += [f"volume={_num(c.get('volume'), 1.0):.3f}",
              "aformat=sample_rates=48000:channel_layouts=stereo", "apad", f"atrim=duration={D:.4f}"]
        if c.get("ramp"):
            graph.append(f"[ramped]{','.join(a)}[aout]")
            a = None
        if a:
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
    vpost.append("format=yuv420p")
    graph.append(f"[{cur_v}]{','.join(vpost)}[vbase]")
    cur_v, vpost = "vbase", []
    overlays = list(edl.get("overlays") or [])
    texts = []
    for it in edl["texts"]:
        clean, found = emoji.split(str(it.get("text", "")))
        if found:
            pos = it.get("pos", "center")
            _, fx, fy = (5, *pos) if isinstance(pos, (list, tuple)) else text._POS[pos]
            w = 0.12
            for k, e in enumerate(found):
                overlays.append({"src": f"emoji:{e}", "start": it["start"], "end": it["end"], "width": w,
                                 "x": fx + (k - (len(found) - 1) / 2) * w * 1.1,
                                 "y": fy - (0.1 if clean else 0.0) * W / H})
            it = dict(it, text=clean)
        if it.get("text"):
            texts.append(it)
    edl["texts"] = texts
    for j, ov in enumerate(overlays):
        # {src, start, end, x, y (0..1 centre), width (fraction of frame width), opacity}
        osrc = str(emoji.png(ov["src"][6:])) if str(ov["src"]).startswith("emoji:") else _check_src(ov["src"])
        st, en = float(ov.get("start", 0)), float(ov.get("end", total))
        args += (["-loop", "1", "-framerate", str(out["fps"])] if Path(osrc).suffix.lower() in IMAGE_EXT else []) + ["-i", osrc]
        ow = int(W * float(ov.get("width", 0.3))) // 2 * 2
        x, y = float(ov.get("x", 0.5)), float(ov.get("y", 0.5))
        idx = _input_count(args) - 1
        graph.append(f"[{idx}:v]scale={ow}:-2,format=rgba,colorchannelmixer=aa={float(ov.get('opacity', 1)):.3f},"
                     f"fade=t=in:st=0:d=0.15:alpha=1,setpts=PTS-STARTPTS+{st:.4f}/TB[ov{j}]")
        graph.append(f"[{cur_v}][ov{j}]overlay=x='{x:.3f}*W-w/2':y='{y:.3f}*H-h/2':eof_action=pass:"
                     f"enable='between(t,{st:.4f},{en:.4f})'[vo{j}]")
        cur_v = f"vo{j}"
    if edl["texts"]:
        ass = text.write_ass(edl["texts"], W, H, work / ("preview.ass" if preview else "final.ass"))
        vpost.append(f"ass=filename='{_fesc(ass)}':fontsdir='{_fesc(text.FONTS_DIR)}':shaping=complex")
    vpost += ["format=yuv420p"]
    graph.append(f"[{cur_v}]{','.join(vpost)}[vfinal]")

    # Audio mix.
    aud = edl["audio"] or {}
    mix_inputs: list[str] = []
    n_in = _input_count(args)
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
        final = final.with_name(f"{final.stem}_preview.mp4")
    final.parent.mkdir(parents=True, exist_ok=True)
    venc = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26"] if preview else
            ["-c:v", "libx264", "-preset", out["preset"], "-crf", str(out["crf"]),
             "-profile:v", "high", "-pix_fmt", "yuv420p"])
    if out.get("max_mb") and not preview:
        # Cap the file size (platform upload limits): CRF quality, but never above this bitrate.
        kbps = max(300, int(float(out["max_mb"]) * 8000 * 0.93 / total) - 192)
        venc += ["-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k"]
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


def _input_count(args: list[str]) -> int:
    return sum(1 for a in args if a == "-i")


def _check_src(src: str) -> str:
    if not Path(src).exists():
        raise ValueError(f"File not found: {src}")
    return src


def _fesc(p: str | Path) -> str:
    """Escape a path for use inside a filtergraph option value."""
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
