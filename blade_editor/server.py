"""Blade Editor MCP server: free, local video editing for AI agents."""

from __future__ import annotations

import functools
import inspect
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__, analyze, audio, autoedit, camera, captions, effects, ff, flow, motion, qa, render, sfx, text

HOME = Path(os.environ.get("BLADE_HOME", Path.home() / "blade_projects")).expanduser()

INSTRUCTIONS = """\
Blade Editor edits video locally with ffmpeg. Free, no credit limits.

FIRST: call `start_here` once per conversation. If first_use=true, ask the user (in their
language) if they want the short guide; if yes, call `guide` and translate it fully.

DECIDE BEFORE THE FIRST RENDER: run `reference_breakdown` (when there is a reference) and
`view_frames` on the reference and sources. Map each part to a tool: camera moves -> `camera`
effect with the breakdown's keys (or `camera_preset`); 3D turns, designed titles/graphics ->
`motion_graphic` (Kinetograph); missing shots -> Google Flow (ask before spending credits);
beats -> clip in/out on beats or `auto_edit`. Tell the user briefly what will match exactly,
approximately, or not at all - then make ONE complete, standard edit (no half versions).

TRUST MEASUREMENTS: cuts from `analyze_video` are measured; check doubts once with
`verify_cuts`, re-run at most once with `sensitivity`. Repeated analysis of a file is refused
(`limit_reached`): accept the earlier result. At most 2 previews and 2 revision rounds.

Loop: preview with render_edl(preview=true) -> view_frames -> final -> quality_check (+
compare_videos with a reference). Times are seconds; clip effect times are from the clip start;
texts/sfx/overlays/global_effects use output time. Persian/Arabic text and colour emoji work.
Skills blade-edit, blade-spec and blade-ponytail give the full rules when installed.
"""

mcp = MCPServer("blade-editor", instructions=INSTRUCTIONS, version=__version__)
_tool = mcp.tool


def _tool_with_errors():
    """Like mcp.tool(), but the agent sees the real error text (MCP hides unexpected errors)."""
    def deco(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapped(*a, **k):
                try:
                    return await fn(*a, **k)
                except ToolError:
                    raise
                except Exception as e:
                    raise ToolError(f"{type(e).__name__}: {e}") from e
        else:
            @functools.wraps(fn)
            def wrapped(*a, **k):
                try:
                    return fn(*a, **k)
                except ToolError:
                    raise
                except Exception as e:
                    raise ToolError(f"{type(e).__name__}: {e}") from e
        return _tool()(wrapped)
    return deco


mcp.tool = _tool_with_errors


def _project(name: str | None) -> Path:
    p = HOME / (name or "default")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _abs(path: str) -> str:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        raise ValueError(f"File not found: {p}")
    return str(p.resolve())


def _save(project: Path, stem: str, data: Any) -> str:
    out = project / f"{stem}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(out)


GUIDE = Path(__file__).with_name("GUIDE.md")
FIRST_USE_MARK = HOME / ".welcomed"


@mcp.tool()
def start_here() -> dict:
    """Call once per conversation before other Blade Editor tools. Says if this is the user's first
    use of Blade Editor; then ask the user (in their language) if they want the guide."""
    first = not FIRST_USE_MARK.exists()
    if first:
        HOME.mkdir(parents=True, exist_ok=True)
        FIRST_USE_MARK.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    return {"first_use": first, "version": __version__,
            "next": ("Ask the user, in their own language, if they want the Blade Editor user guide. "
                     "If yes, call `guide`." if first else
                     "Continue with the user's request. The guide is available with `guide`.")}


@mcp.tool()
def guide() -> dict:
    """The Blade Editor user guide (in English). Translate the whole guide into the language the
    user writes in before you give it to them; keep commands, file names and tool names as they are."""
    return {"guide_markdown": GUIDE.read_text(encoding="utf-8"),
            "instruction": "Translate everything into the user's language; do not shorten it."}


@mcp.tool()
def capabilities() -> dict:
    """List everything the editor can do: EDL format, effects, grades, transitions, text styles,
    text animations, sound effects and auto-edit presets. Read this before writing an EDL."""
    return {
        "version": __version__,
        "projects_dir": str(HOME),
        "edl_format": {
            "output": "{path, width=1080, height=1920, fps=30, fit='cover'|'contain'|'blur', grade, global_grade, crf=18, preset='medium', max_mb}",
            "clips[]": "{src (video, image, or 'color:#RRGGBB'), in, out | duration, speed=1, "
                       "ramp=[[source_seconds, speed], ...] (speed ramp, replaces out/speed), stabilize=false, reverse=false, "
                       "fit, focus=[x,y] (0..1 crop centre for cover) or 'auto' (follows motion), mute, volume, "
                       "grade (name or path to a .cube LUT), effects[], "
                       "transition: 'cut' | 'flash' | 'zoom' | 'glitch' | 'whip' | any ffmpeg xfade name, "
                       "or {type, dur}}",
            "texts[]": "{text (emoji become colour stickers above the text), start, end, style, pos ('top','upper','center','lower','bottom','top_left',...) "
                       "or [x,y] fractions, anim, size, color '#RRGGBB', outline_color, font, rotate}",
            "global_effects[]": "same effect objects, times in output seconds",
            "overlays[]": "{src (png/jpg/video or 'emoji:🔥'), start, end, x, y (0..1 centre), width (fraction of frame), opacity}",
            "audio": "{music, music_start, volume, fade_in, fade_out, keep_clip_audio, clip_audio_volume, duck, normalize=true (-14 LUFS)}",
            "sfx[]": "{kind | file, at, volume=0.8, dur}",
        },
        "effects": effects.EFFECT_DOCS,
        "grades": list(effects.GRADES),
        "transitions_custom": sorted(render.CUSTOM_TRANSITIONS),
        "transitions_xfade_examples": ["fade", "fadeblack", "fadewhite", "dissolve", "slideleft", "slideright",
                                        "slideup", "slidedown", "wipeleft", "circleopen", "circleclose",
                                        "radial", "pixelize", "hblur", "smoothleft", "zoomin", "squeezeh"],
        "text_styles": list(text.STYLES),
        "text_anims": list(text.ANIMS),
        "sfx_kinds": sfx.kinds(),
        "auto_edit_presets": autoedit.PRESETS,
        "captions_available": captions.available(),
    }


@mcp.tool()
def probe_media(path: str) -> dict:
    """Return duration, resolution, fps, codecs and audio info of a media file."""
    return ff.probe(_abs(path))


_CALLS: dict[tuple[str, str], int] = {}
LIMITS = {"analyze_video": 2, "verify_cuts": 1, "reference_breakdown": 2}


def _budget(tool: str, path: str) -> dict | None:
    """Hard cap on repeated checks of the same file, so a doubt can never become a loop."""
    key = (tool, str(Path(path).expanduser()))
    _CALLS[key] = _CALLS.get(key, 0) + 1
    if _CALLS[key] > LIMITS[tool]:
        return {"limit_reached": True,
                "message": f"{tool} already ran {LIMITS[tool]}x on this file in this chat. Use the "
                           "earlier result as final; do not check it again. Tell the user any doubt."}
    return None


@mcp.tool()
def analyze_video(path: str, project: str | None = None, max_fps: float = 30.0,
                  sensitivity: str = "normal") -> dict:
    """Measure a video's edit language: cut times (+ confidence 0..1), shots (length, camera
    move, shake), flashes, activity per second, and music beats when it has audio.
    The cut detector is measured and usually right: do NOT overrule it from guesses. If you doubt
    some cuts, call verify_cuts ONCE and look; only then you may re-run with sensitivity
    'low' (fewer cuts) or 'high' (more cuts). Max 2 runs per file per chat."""
    if sensitivity not in analyze.SENSITIVITY:
        raise ValueError(f"sensitivity must be one of {list(analyze.SENSITIVITY)}")
    if (stop := _budget("analyze_video", path)):
        return stop
    r = analyze.analyze_video(_abs(path), max_fps=max_fps, sensitivity=sensitivity)
    saved = _save(_project(project), f"analysis_{Path(path).stem}", r)
    reply = {k: r[k] for k in ("summary", "cuts", "cut_confidence", "flashes", "shots")}
    reply["file"] = r["file"]
    reply["per_second"] = r["per_second"][:120]
    if "audio" in r:
        reply["audio"] = {k: r["audio"][k] for k in ("bpm", "beat_interval", "downbeats")}
        reply["audio"]["beats"] = r["audio"]["beats"][:200]
    reply["saved_json"] = saved
    return reply


@mcp.tool()
def verify_cuts(path: str, cuts: list[float], project: str | None = None) -> list:
    """One image to check cuts by eye: for each cut time, the frame just before and just after
    (max 24 cuts; pass the low-confidence ones first). A real cut shows two different shots.
    Use it once per file; then accept the result."""
    if (stop := _budget("verify_cuts", path)):
        return [json.dumps(stop)]
    src = _abs(path)
    proj = _project(project)
    from PIL import Image as PILImage, ImageDraw
    tiles = []
    for c in cuts[:24]:
        pair = []
        for k, t in enumerate((c - 0.07, c + 0.04)):
            fp = proj / f"vc_{int(time.time() * 1000)}_{k}.jpg"
            ff.extract_frame(src, max(0.0, t), fp, 200)
            pair.append(PILImage.open(fp).convert("RGB"))
            fp.unlink()
        w, h = pair[0].size
        tile = PILImage.new("RGB", (2 * w + 6, h + 20), (20, 20, 20))
        tile.paste(pair[0], (0, 20)); tile.paste(pair[1], (w + 6, 20))
        ImageDraw.Draw(tile).text((4, 3), f"cut {c:.2f}s  before | after", fill=(255, 220, 0))
        tiles.append(tile)
    if not tiles:
        raise ValueError("Give at least one cut time.")
    cols = 3
    tw, th = tiles[0].size
    sheet = PILImage.new("RGB", (cols * tw, -(-len(tiles) // cols) * th), (0, 0, 0))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
    out = proj / f"verify_cuts_{int(time.time())}.jpg"
    sheet.save(out, quality=80)
    return [Image(path=str(out)), json.dumps({"cuts": cuts[:24], "image": str(out)})]


@mcp.tool()
def extract_motion(path: str, start: float = 0.0, end: float | None = None, max_keys: int = 16) -> dict:
    """Measure the camera move of ONE shot (no cut inside): movement, rotation and zoom, as a
    short list of keyframes [t, x, y, rot_deg, zoom] plus plain words (sway, whip, rotation,
    zoom, shake). Put the keys in a clip effect {"type": "camera", "keys": ...} to copy the move
    onto any clip (key times are from the shot start)."""
    m = camera.measure(_abs(path), start, end)
    return {"keys": camera.keyframes(m, max_keys), "moves": camera.describe(m),
            "duration": round(float(m["t"][-1]), 3)}


@mcp.tool()
def camera_preset(name: str, duration: float, amount: float | None = None, count: int | None = None) -> dict:
    """Ready, smooth camera keyframes for a clip effect {"type":"camera","keys":...}:
    spin360_holds (360-degree turn that stops at each of `count` angles, default 4 = 90/180/270/360),
    sway (left-right and back, amount = fraction of width), whip_left / whip_right,
    zoom_pulse (amount = extra zoom), tilt_swing (rotation back and forth, amount = degrees).
    For 3D turns (card flip, orbit, perspective) use motion_graphic with Kinetograph instead."""
    return {"keys": camera.preset(name, duration, amount, count)}


@mcp.tool()
def reference_breakdown(path: str, max_shots: int = 30, project: str | None = None) -> dict:
    """The recipe of a reference edit, shot by shot, in few tokens: length, cut on beat, camera
    moves with ready `camera` keys, flashes, shake, and which Blade Editor tool reproduces each
    part. Call this FIRST for any "copy this edit" request, then decide what you can rebuild."""
    if (stop := _budget("reference_breakdown", path)):
        return stop
    src = _abs(path)
    a = analyze.analyze_video(src)
    beats = (a.get("audio") or {}).get("beats") or []
    shots = []
    for sh in a["shots"][:max_shots]:
        row = {"start": sh["start"], "end": sh["end"], "duration": sh["duration"]}
        if beats:
            row["starts_on_beat"] = any(abs(b - sh["start"]) <= 0.07 for b in beats)
        fl = [f for f in a["flashes"] if sh["start"] <= f < sh["end"]]
        if fl:
            row["flashes"] = [round(f - sh["start"], 2) for f in fl]
        how = ["clip trim (in/out) on the beat grid"]
        if sh["duration"] >= 0.3:
            m = camera.measure(src, sh["start"], sh["end"])
            moves = camera.describe(m)
            if moves:
                row["moves"] = moves
                row["camera_keys"] = camera.keyframes(m, 10)
                how.append('effect {"type":"camera","keys":camera_keys}')
                if any("shake" in x for x in moves):
                    how.append('effect {"type":"shake"} for the jitter')
        if fl:
            how.append('effect {"type":"flash","at":<flash time>}')
        row["how"] = how
        shots.append(row)
    out = {"summary": a["summary"], "bpm": (a.get("audio") or {}).get("bpm"), "shots": shots,
           "not_measurable": ["3D rotation/perspective (card flips, orbit)", "masks and tracked text",
                              "particles"],
           "for_those": "use motion_graphic (Kinetograph) or say the limit to the user before rendering"}
    out["saved_json"] = _save(_project(project), f"breakdown_{Path(path).stem}", out)
    return out


@mcp.tool()
def view_frames(path: str, start: float = 0.0, end: float | None = None, count: int = 12,
                every: float | None = None, cols: int = 4, thumb_width: int = 320,
                project: str | None = None) -> list:
    """Show frames of a video as one contact-sheet image so you can SEE the content.
    Each tile is labelled with its index, time and frame number. Use `every` for a fixed step
    (for example 0.1 for a frame-by-frame read of a short part)."""
    out = _project(project) / f"sheet_{Path(path).stem}_{int(time.time() * 1000)}.jpg"
    r = analyze.contact_sheet(_abs(path), str(out), start, end, every, count, cols, thumb_width)
    return [Image(path=r["image"]), json.dumps({"times": r["times"], "image": r["image"]})]


@mcp.tool()
def analyze_music(path: str, start: float = 0.0, duration: float | None = None) -> dict:
    """Find tempo (BPM), beat times, downbeats (bar starts), strong hits and loudness per second
    in a music or video file. Use the beats to place cuts and effects."""
    r = audio.analyze_beats(_abs(path), start, duration)
    r["onsets"] = r["onsets"][:300]
    return r


@mcp.tool()
def style_from_reference(reference_path: str, project: str | None = None) -> dict:
    """Measure a reference edit and turn it into a style (cut rhythm in beats, zoom punch, flash
    and shake rates, colour grade, transition type) for auto_edit. Copies the edit *language*,
    not the footage."""
    r = autoedit.style_from_reference(_abs(reference_path))
    saved = _save(_project(project), f"style_{Path(reference_path).stem}", r)
    return {"style": r["style"], "reference_summary": r["reference_analysis"]["summary"],
            "saved_json": saved}


@mcp.tool()
def auto_edit(sources: list[str], music: str, output_path: str,
              style: str | dict = "hype", duration: float | None = None, music_start: float = 0.0,
              width: int = 1080, height: int = 1920, fps: int = 30, title: str | None = None,
              keep_order: bool = False, seed: int = 7, preview: bool = False,
              project: str | None = None) -> dict:
    """Make a beat-synced edit from your clips and a music track in one call.
    style: a preset name (hype, phonk, cinematic, smooth, glitch), a style dict from
    style_from_reference, or a path to a reference video. The EDL is saved so you can change it
    and call render_edl again."""
    src = [_abs(s) for s in sources]
    if isinstance(style, str) and style not in autoedit.PRESETS:
        style = autoedit.style_from_reference(_abs(style))["style"]
    out = str(Path(output_path).expanduser().resolve())
    edl = autoedit.build_edl(src, _abs(music), out, style, duration, music_start, width, height, fps,
                             title, seed, keep_order)
    proj = _project(project)
    meta = edl.pop("_meta")
    edl_path = _save(proj, "edl_auto", edl)
    r = render.render(edl, proj / "work", preview=preview)
    return {"result": r, "edl_path": edl_path, "meta": meta}


@mcp.tool()
def render_edl(edl: dict | None = None, edl_path: str | None = None, preview: bool = True,
               project: str | None = None) -> dict:
    """Render an edit decision list (see capabilities for the format). Give `edl` inline or an
    `edl_path`. preview=true renders at half size quickly; check it with view_frames, then render
    with preview=false. Clip segments are cached, so small changes render fast."""
    if edl is None:
        if not edl_path:
            raise ValueError("Give edl or edl_path.")
        edl = json.loads(Path(_abs(edl_path)).read_text(encoding="utf-8"))
    proj = _project(project)
    saved = edl_path or _save(proj, "edl", edl)
    r = render.render(edl, proj / "work", preview=preview)
    r["edl_path"] = saved
    return r


@mcp.tool()
def quality_check(path: str) -> dict:
    """Check a finished video for black frames, frozen picture, silence, loudness (LUFS) and peak."""
    return qa.check(_abs(path))


@mcp.tool()
def speech_segments(path: str, noise_db: float = -35.0, min_silence: float = 0.35) -> dict:
    """Find the parts with speech/sound so you can cut out the pauses (jump cuts). Use each
    `keep` pair as one clip {src, in, out} in an EDL."""
    return qa.speech_segments(_abs(path), noise_db, min_silence)


@mcp.tool()
def compare_videos(reference: str, output: str, count: int = 8, project: str | None = None) -> list:
    """Put a reference and your output side by side (top row reference, bottom row output) and
    compare their measured edit style: cuts per second, shot length, flashes, shake, cuts on
    beat. Use it to check how close the edit is to the reference and what to fix."""
    proj = _project(project)
    stamp = int(time.time() * 1000)
    rows = []
    for name, p in (("ref", reference), ("out", output)):
        r = analyze.contact_sheet(_abs(p), str(proj / f"cmp_{name}_{stamp}.jpg"), count=count,
                                  cols=count, thumb_width=200)
        rows.append(r["image"])
    from PIL import Image as PILImage

    a, b = (PILImage.open(x) for x in rows)
    sheet = PILImage.new("RGB", (max(a.width, b.width), a.height + b.height))
    sheet.paste(a, (0, 0))
    sheet.paste(b, (0, a.height))
    path = proj / f"compare_{stamp}.jpg"
    sheet.save(path, quality=85)
    keys = ("cuts_per_second", "median_shot_length", "flashes_per_second", "shake_share",
            "moving_camera_share", "cuts_on_beat_share", "mean_activity")
    sa = analyze.analyze_video(_abs(reference))["summary"]
    sb = analyze.analyze_video(_abs(output))["summary"]
    table = {k: {"reference": sa.get(k), "output": sb.get(k)} for k in keys}
    return [Image(path=str(path)), json.dumps({"style": table, "image": str(path)})]


@mcp.tool()
def transcribe(path: str, language: str | None = None, model: str = "small", device: str = "auto",
               project: str | None = None) -> dict:
    """Speech to text with word times (needs faster-whisper). Use the segments with
    make_caption_texts to get karaoke-style captions for an EDL. device: auto (falls back to the
    CPU when the GPU's CUDA libraries are missing), cpu or cuda."""
    r = captions.transcribe(_abs(path), language, model, device)
    r["saved_json"] = _save(_project(project), f"transcript_{Path(path).stem}", r)
    return r


@mcp.tool()
def make_caption_texts(segments: list[dict], style: str = "subtitle", pos: str = "lower",
                       karaoke: bool = True, max_words: int = 4, offset: float = 0.0) -> dict:
    """Turn transcript segments [{start,end,text,words[]}] into EDL `texts` items. Karaoke mode
    highlights the spoken word. `offset` moves all times (use it when the clip starts later)."""
    segs = []
    for s in segments:
        s = dict(s)
        s["start"] = s["start"] + offset
        s["end"] = s["end"] + offset
        s["words"] = [dict(w, start=w["start"] + offset, end=w["end"] + offset) for w in s.get("words", [])]
        segs.append(s)
    return {"texts": text.captions_to_items(segs, style, pos, karaoke, max_words)}


@mcp.tool()
def make_sfx(kind: str, duration: float | None = None, project: str | None = None) -> dict:
    """Make a sound effect file (whoosh, hit, riser, click, glitch, boom, swish)."""
    return {"path": str(sfx.make(kind, _project(project), duration))}


@mcp.tool()
def motion_graphic(entry: str, output_path: str, comp: str | None = None, props: dict | None = None,
                   draft: bool = False) -> dict:
    """Render a Kinetograph (Remotion-style TSX) motion graphic - title, lower third, kinetic text,
    shapes, Lottie - to a TRANSPARENT ProRes 4444 clip for `overlays` (width 1.0 = full frame).
    Needs Node.js and `npm i -D kinetograph` next to the entry, and the composition must use
    background={process.env.BLADE_BG ?? "transparent"}. Write Persian/Arabic text in a
    <div dir="rtl"> (HTML path), not <Text> (no right-to-left support there)."""
    return motion.render(_abs(entry), str(Path(output_path).expanduser().resolve()), comp, props, draft)


def _with_shot(r: dict) -> list:
    shot = r.pop("_screenshot", None)
    return ([Image(data=shot, format="jpeg")] if shot else []) + [json.dumps(r, ensure_ascii=False)]


@mcp.tool()
def flow_setup(port: int = 0) -> dict:
    """How to connect Google Flow (AI video with your own Google account and credits) through
    YOUR normal Chrome: install the Blade Bridge extension once (no other setting); Blade opens the
    Flow tab itself. Fallback: chrome://inspect/#remote-debugging. A port number connects to a
    Chrome started with --remote-debugging-port."""
    return flow.setup_help(port)


@mcp.tool()
async def flow_status(port: int = 0) -> list:
    """Check the connection to the Flow tab in your Chrome and show a screenshot of it."""
    return _with_shot(await flow.status(port))


@mcp.tool()
async def flow_generate_video(prompt: str, confirm: bool = False, port: int = 0, direct: bool = True,
                              timeout: float = 600, project: str | None = None) -> list:
    """Generate a video clip with Google Flow (Veo) in your logged-in Chrome.
    confirm=false (default) only types the prompt and returns a screenshot; no credits are spent.
    Ask the user, then call with confirm=true to submit; the new video is downloaded to the
    project folder and can be used as a clip `src` in an EDL. Blade Editor never approves credit
    dialogs; if Flow shows one, the user approves it in the browser."""
    out = _project(project) / "flow"
    return _with_shot(await flow.generate_video(prompt, out, confirm, port, direct, timeout))


@mcp.tool()
async def flow_collect(port: int = 0, limit: int = 4, project: str | None = None) -> dict:
    """Download the newest videos visible in the Flow tab (use after a flow_generate_video timeout)."""
    return await flow.collect(_project(project) / "flow", port, limit)


def _config_files() -> list[Path]:
    """MCP config files: Claude Code (CLI and the desktop app's Code tab) and Claude Desktop."""
    files = [Path.home() / ".claude.json"]
    if os.name == "nt":
        desktop = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude"
    elif sys.platform == "darwin":
        desktop = Path.home() / "Library" / "Application Support" / "Claude"
    else:
        desktop = Path.home() / ".config" / "Claude"
    if desktop.is_dir():  # only when the Claude desktop app is installed
        files.append(desktop / "claude_desktop_config.json")
    return files


def register() -> list[str]:
    """Add this Python as the `blade-editor` MCP server, without the `claude` command."""
    entry = {"type": "stdio", "command": sys.executable, "args": ["-m", "blade_editor.server"], "env": {}}
    done = []
    for f in _config_files():
        data = {}
        if f.exists():
            text = f.read_text(encoding="utf-8")
            data = json.loads(text) if text.strip() else {}
            f.with_name(f.name + ".blade-backup").write_text(text, encoding="utf-8")
        data.setdefault("mcpServers", {})["blade-editor"] = entry
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)  # atomic, so a crash never leaves a half-written config
        done.append(str(f))
    return done


def main() -> None:
    if "--version" in sys.argv:
        print(__version__)
        return
    if "--register" in sys.argv:
        for f in register():
            print(f"OK: {f}")
        return
    mcp.run("stdio")


if __name__ == "__main__":
    main()
