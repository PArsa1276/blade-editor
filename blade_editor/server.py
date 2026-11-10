"""Blade Editor MCP server: free, local video editing for AI agents."""

from __future__ import annotations

import functools
import inspect
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import anyio
from mcp.server.mcpserver import Context, Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__, analyze, audio, autoedit, camera, captions, effects, ff, flow, motion, prompts, qa, recipes, remake, render, sfx, shorts, text

HOME = Path(os.environ.get("BLADE_HOME", Path.home() / "blade_projects")).expanduser()

INSTRUCTIONS = """\
Blade Editor edits video locally with ffmpeg. Free, no credit limits.

FIRST: call `start_here` once per conversation. If first_use=true, ask the user (in their
language) if they want the short guide; if yes, call `guide` and translate it fully.

IDEAS: for a creative edit, call `edit_ideas` with the user's request first and build on the best
recipe (structure, rhythm, the "wow" trick) - adapted to the footage and the user's words. Read
the 1-3 `edit_playbook` sections the job needs, and its checklist before the final render.
Every render is a version: "go back" -> edl_versions + restore_version.
LONG VIDEO -> SHORTS: transcript first, then find_highlights; pick by meaning (complete idea,
hook in 3 s, payoff), then make_shorts.
`learn_edit` saves a reference the user likes as a new recipe.

DECIDE BEFORE THE FIRST RENDER: run `reference_breakdown` (when there is a reference) and
`view_frames` on the reference and sources. Map each part to a tool: camera moves -> `camera`
effect with the breakdown's keys (or `camera_preset`); 3D turns, designed titles/graphics ->
`motion_graphic` (Kinetograph); hook titles, name tags, numbers, CTAs -> `motion_template`
(transparent overlay; rules in the blade-motion skill); missing shots -> Google Flow: keyframe images first (`flow_generate_image`, same references for every
shot), then video from them (`first_frame`/`last_frame`, prompt with `video_prompt`); ask before
spending credits); NO footage at all ("make one like this reference") -> `remake_plan` (fewest
Flow clips, measured camera per shot) -> Flow -> `remake_assemble`;
beats -> clip in/out on beats or `auto_edit`. Tell the user briefly what will match exactly,
approximately, or not at all - then make ONE complete, standard edit (no half versions).

TRUST MEASUREMENTS: cuts from `analyze_video` are measured; check doubts once with
`verify_cuts`, re-run at most once with `sensitivity`. Repeated analysis of a file is refused
(`limit_reached`): accept the earlier result. At most 2 previews and 2 revision rounds.

CAPTIONS (3 steps, never skip step 2). Before the first transcription, if `speech_models` shows
no saved choice, show the user its choices (and models found on their computer) and ask which to
use; then pass it with remember=true. `transcribe` (set language; put spoken names/topic words in
`prompt`) -> read every `review` line and correct misheard words, names, spelling and
punctuation with `fix_transcript` (only changed lines; keep the spoken words, do not summarise)
-> `make_caption_texts(transcript_path, keep=<jump-cut pairs>)` -> put its texts_file in `texts`.

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


HEARTBEAT = 20.0  # seconds between progress messages: Claude Code stops a tool after 30 min of silence


async def _with_progress(ctx, work):
    """Run work(tell) in a thread; send MCP progress at least every HEARTBEAT seconds, so a long
    job (model download, a queue of files, a slow CPU) is not stopped as 'no response'."""
    state = {"done": 0.0, "total": None, "msg": "starting"}

    def tell(done, total=None, msg=None):
        state.update(done=float(done or 0), total=total or state["total"], msg=msg or state["msg"])

    async def send():
        if ctx is None:
            return
        try:
            await ctx.report_progress(state["done"], state["total"], state["msg"])
        except Exception:
            pass  # the client did not ask for progress, or it went away: the work goes on

    result: dict = {}

    async def run():
        try:
            result["r"] = await anyio.to_thread.run_sync(work, tell)
        except Exception as e:  # re-raised below as itself, not inside an ExceptionGroup
            result["e"] = e
        tg.cancel_scope.cancel()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run)
        while True:
            await send()
            await anyio.sleep(HEARTBEAT)
    if "e" in result:
        raise result["e"]
    return result["r"]


def _project(name: str | None) -> Path:
    name = name or "default"
    if not re.fullmatch(r"[^/\\:]+", name) or name.strip(".") == "":
        raise ValueError(f"Project name {name!r} is not valid: use a simple name without / \\ : or '..'.")
    p = HOME / name
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


PLAYBOOK = Path(__file__).with_name("PLAYBOOK.md")


@mcp.tool()
def edit_playbook(section: str | None = None) -> dict:
    """The editing taste guide: rules that make edits feel professional, mapped to Blade's tools
    (hook, energy, rhythm, motion, speed, transitions, text, color, sound, ending, platform,
    mistakes, checklist). Without `section` you get the list; ask for 1-3 sections that matter
    for the job (e.g. "hook,rhythm,sound") - and always "checklist" before the final render."""
    text = PLAYBOOK.read_text(encoding="utf-8")
    parts = {m.group(1): m.group(2).strip() for m in re.finditer(r"^## (\w+)\n(.*?)(?=^## |\Z)", text, re.M | re.S)}
    if not section:
        return {"sections": list(parts), "intro": text.split("## ", 1)[0].strip()}
    want = [s.strip().lower() for s in section.split(",") if s.strip()]
    unknown = [s for s in want if s not in parts]
    if unknown:
        raise ValueError(f"Unknown section(s) {unknown}. Use: {', '.join(parts)}")
    return {s: parts[s] for s in want}


@mcp.tool()
def capabilities() -> dict:
    """List everything the editor can do: EDL format, effects, grades, transitions, text styles,
    text animations, sound effects and auto-edit presets. Read this before writing an EDL."""
    return {
        "version": __version__,
        "projects_dir": str(HOME),
        "edl_format": {
            "output": "{path, width=1080, height=1920, fps=30, fit='cover'|'contain'|'blur', grade, global_grade, crf=20 (lower = better and larger; 18 for an archive master), preset='medium', max_mb (size limit for sharing)}",
            "clips[]": "{src (video, image, or 'color:#RRGGBB'), in, out | duration, speed=1, "
                       "ramp=[[source_seconds, speed], ...] (speed ramp, replaces out/speed), slowmo=auto|flow|blend|none (slowed parts: flow = optical-flow in-between frames, real smooth slow motion, slower render; auto = flow in the final render for speed <= 0.75, blend in previews), stabilize=false, reverse=false, "
                       "fit, focus=[x,y] (0..1 crop centre for cover) or 'auto' (follows motion), mute, volume, "
                       "grade (name, path to a .cube LUT, or {brightness, contrast, saturation, warmth}), effects[], "
                       "transition: 'cut' | 'flash' | 'zoom' | 'glitch' | 'whip' | any ffmpeg xfade name, "
                       "or {type, dur}}",
            "texts[]": "{text (emoji become colour stickers above the text), start, end, style, pos ('top','upper','center','lower','bottom','top_left',...) "
                       "or [x,y] fractions, anim, size, color '#RRGGBB', outline_color, font, rotate, "
                       "behind_subject=false (true: the text goes BEHIND the person/object in the shot - big "
                       "bold titles wider than the subject look best; the subject is found by a local AI "
                       "model, about 0.1-0.3 s per frame inside the text's time)}. Top-level "
                       "subject_model: u2net (any subject, default) | birefnet_lite (best edges, slower) | u2net_human_seg (people) | silueta (fast); "
                       "subject_keep / subject_remove: boxes [x0,y0,x1,y1] (0..1) that always stay / go",
            "global_effects[]": "same effect objects, times in output seconds",
            "overlays[]": "{src (png/jpg/video or 'emoji:🔥'), start, end, x, y (0..1 centre), width (fraction of frame), opacity, "
                          "fade_in=0.15, fade_out=0 (seconds), blend='normal'|'screen'|'add' (screen/add: black in the overlay is "
                          "invisible - light leaks, sparks, a title card made on black; no alpha needed)}",
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
        if r["audio"].get("note"):
            reply["audio"]["note"] = r["audio"]["note"]
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
    not the footage. 'pattern' is the reference's shot lengths in beats (auto_edit repeats it on
    the new music); 'flash_rate'/'flash_on_cut' place the same number of flashes on beats;
    'camera_moving' makes auto_edit pick shots whose camera moves about as often as the reference's;
    'color' (the reference's measured colour) gives each shot its own grade toward it."""
    r = autoedit.style_from_reference(_abs(reference_path))
    saved = _save(_project(project), f"style_{Path(reference_path).stem}", r)
    return {"style": r["style"], "reference_summary": r["reference_analysis"]["summary"],
            "saved_json": saved}


@mcp.tool()
def edit_ideas(request: str, count: int = 3) -> dict:
    """Ideas library: proven edit formats (beat-sync flash, velocity, aura, cinematic travel,
    glitch, UGC hook, before/after, 3D spin, kinetic type, POV, smooth, sport) plus the user's own
    recipes from learn_edit, best matches first. Each recipe gives structure, cut rhythm, camera,
    transitions, effects, text, grade, sfx, the Blade calls to build it and one 'wow' trick. Use it
    BEFORE planning a creative edit: combine the best recipe with the user's request and footage
    (do not copy it blindly; the user's words win)."""
    return {"ideas": recipes.ideas(request, count)}


@mcp.tool()
def learn_edit(reference_path: str, name: str, tags: str = "", notes: str = "",
               project: str | None = None) -> dict:
    """Learn an edit the user likes (a reference video, e.g. downloaded from a CapCut template
    page or TikTok Creative Center) and save it as a reusable recipe in the ideas library. Its
    measured style can then be used as auto_edit(style=<name>). tags: words to find it by (mood,
    genre). notes: what makes it special (write what you saw with view_frames)."""
    r = autoedit.style_from_reference(_abs(reference_path))
    s = r["reference_analysis"]["summary"]
    recipe = {"tags": tags, "notes": notes, "idea": notes or f"Learned from {Path(reference_path).name}",
              "style": r["style"], "measured": {k: s.get(k) for k in (
                  "cuts_per_second", "median_shot_length", "flashes_per_second", "shake_share",
                  "moving_camera_share", "cuts_on_beat_share")},
              "build": [f"auto_edit(style='{name}')", "or render_edl using the measured rhythm"],
              "reference": _abs(reference_path)}
    path = recipes.save(name, recipe)
    _save(_project(project), f"recipe_{path.stem}", recipe)
    return {"saved": str(path), "name": path.stem, "style": r["style"], "measured": recipe["measured"]}


@mcp.tool()
def auto_edit(sources: list[str], music: str, output_path: str,
              style: str | dict = "hype", duration: float | None = None, music_start: float = 0.0,
              width: int = 1080, height: int = 1920, fps: int = 30, title: str | None = None,
              keep_order: bool = False, seed: int = 7, preview: bool = False,
              project: str | None = None) -> dict:
    """Make a beat-synced edit from your clips and a music track in one call.
    style: a preset name (hype, phonk, cinematic, smooth, glitch, velocity), a recipe saved with learn_edit,
    a style dict from style_from_reference, or a path to a reference video. The EDL is saved so you
    can change it and call render_edl again."""
    src = [_abs(s) for s in sources]
    saved = {r["name"]: r for r in recipes.user_recipes() if r.get("style")}
    if isinstance(style, str) and style in saved:
        style = saved[style]["style"]
    elif isinstance(style, str) and style not in autoedit.PRESETS:
        style = autoedit.style_from_reference(_abs(style))["style"]
    out = str(Path(output_path).expanduser().resolve())
    edl = autoedit.build_edl(src, _abs(music), out, style, duration, music_start, width, height, fps,
                             title, seed, keep_order)
    proj = _project(project)
    meta = edl.pop("_meta")
    edl_path = _save(proj, "edl_auto", edl)
    snapshot = json.loads(json.dumps(edl))
    r = render.render(edl, proj / "work", preview=preview)
    r["version"] = _add_version(snapshot, preview, f"auto_edit {style if isinstance(style, str) else 'style'}",
                                project)
    return {"result": r, "edl_path": edl_path, "meta": meta}


def _versions_dir(output_path: str, project: str | None) -> Path:
    stem = re.sub(r"[^\w-]+", "_", Path(output_path).stem)
    return _project(project) / "versions" / stem


def _add_version(edl: dict, preview: bool, note: str, project: str | None) -> int:
    d = _versions_dir(edl["output"]["path"], project)
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob("v*.json"))) + 1
    (d / f"v{n:03d}.json").write_text(json.dumps(
        {"version": n, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "preview": preview, "note": note,
         "edl": edl}, ensure_ascii=False, indent=1), encoding="utf-8")
    return n


def render_edl(edl: dict | None = None, edl_path: str | None = None, preview: bool = True,
               note: str = "", project: str | None = None, timecode: bool = False) -> dict:
    """Render an edit decision list (see capabilities for the format). Give `edl` inline or an
    `edl_path`. preview=true renders at half size quickly; check it with view_frames, then render
    with preview=false. Clip segments are cached, so small changes render fast. Every render is
    saved as a numbered version of its output (note: what changed, e.g. "faster cuts"); see
    edl_versions / restore_version to compare or go back.
    The result's `timeline` gives the REAL output start/end of every clip (a transition overlaps
    two clips, so later clips start earlier than the sum of the lengths): take the times for
    texts, overlays and sfx from it. timecode=true writes the output time on the picture (use it
    on previews to name exact moments). Layers, bottom to top: clips (with their effects and
    grade) -> global_effects -> overlays (in list order) -> texts with behind_subject -> the
    subject -> all other texts (so captions are always above a B-roll overlay)."""
    if edl is None:
        if not edl_path:
            raise ValueError("Give edl or edl_path.")
        edl = json.loads(Path(_abs(edl_path)).read_text(encoding="utf-8"))
    proj = _project(project)
    saved = edl_path or _save(proj, "edl", edl)
    snapshot = json.loads(json.dumps(edl))  # render() fills in defaults; keep what was asked
    if timecode:
        edl = {**edl, "output": {**(edl.get("output") or {}), "timecode": True}}
    r = render.render(edl, proj / "work", preview=preview)
    r["edl_path"] = saved
    r["version"] = _add_version(snapshot, preview, note, project)
    return r


@mcp.tool()
def edl_versions(output_path: str, project: str | None = None) -> dict:
    """All saved versions of an output (newest last): number, time, preview or final, note, and
    the clip/text counts. Use it when the user says "go back", "the earlier one was better"."""
    d = _versions_dir(output_path, project)
    out = []
    for f in sorted(d.glob("v*.json")) if d.is_dir() else []:
        v = json.loads(f.read_text(encoding="utf-8"))
        e = v["edl"]
        out.append({"version": v["version"], "time": v["time"], "preview": v["preview"], "note": v["note"],
                    "clips": len(e.get("clips", [])), "texts": len(e.get("texts", [])), "path": str(f)})
    return {"output": output_path, "versions": out}


@mcp.tool()
def restore_version(output_path: str, version: int, preview: bool = False, project: str | None = None) -> dict:
    """Go back to a saved version: render its EDL again (fast: unchanged clips are cached). The
    restored render becomes a new version, so nothing is lost."""
    f = _versions_dir(output_path, project) / f"v{int(version):03d}.json"
    if not f.exists():
        raise ValueError(f"No version {version} for {output_path}. Call edl_versions to see them.")
    edl = json.loads(f.read_text(encoding="utf-8"))["edl"]
    return _render_edl(edl=edl, preview=preview, note=f"restored v{int(version):03d}", project=project)


_render_edl = render_edl
render_edl = mcp.tool()(render_edl)


@mcp.tool()
def find_highlights(path: str, count: int = 5, min_seconds: float = 20, max_seconds: float = 60,
                    transcript_path: str | None = None, project: str | None = None) -> dict:
    """Long video -> shorts, step 1: score the whole video (loudness, movement and - with a
    transcript - dense speech, strong opening lines, complete sentences) and return the best
    non-overlapping moments with their text (about count x 2, best first). For talking videos run
    transcribe (+ fix_transcript) first and pass transcript_path: the moments then start and end on
    sentences and you can read what is said. YOU choose the final `count` by meaning (a complete
    idea, a strong hook in the first 3 s, a payoff), adjust start/end, write a short title for each,
    then call make_shorts."""
    tr = json.loads(Path(_abs(transcript_path)).read_text(encoding="utf-8")) if transcript_path else None
    r = shorts.find(_abs(path), tr, count, min_seconds, max_seconds)
    r["saved_json"] = _save(_project(project), f"highlights_{Path(path).stem}", r)
    return r


@mcp.tool()
def make_shorts(path: str, shorts_list: list[dict], output_dir: str, transcript_path: str | None = None,
                jump_cut: bool = True, captions: bool = True, width: int = 1080, height: int = 1920,
                fps: int = 30, preview: bool = False, project: str | None = None) -> dict:
    """Long video -> shorts, step 2: render each chosen moment as a finished vertical short.
    shorts_list: [{start, end, title?}] in source seconds (from find_highlights, adjusted by you).
    Each short gets: pauses removed (jump_cut), a crop that follows the action, a hook title for
    3 s, karaoke captions from the transcript (moved onto the cut timeline), -14 LUFS. Files are
    <output_dir>/short_01.mp4 ...; each EDL is saved, so one short can be changed with render_edl."""
    tr = json.loads(Path(_abs(transcript_path)).read_text(encoding="utf-8")) if transcript_path else None
    src, outd = _abs(path), Path(output_dir).expanduser().resolve()
    outd.mkdir(parents=True, exist_ok=True)
    done = []
    for k, s in enumerate(shorts_list, 1):
        edl = shorts.build_edl(src, float(s["start"]), float(s["end"]), str(outd / f"short_{k:02d}.mp4"),
                               s.get("title"), tr, jump_cut, captions, width, height, fps)
        edl_path = _save(_project(project), f"edl_short_{k:02d}", edl)
        r = _render_edl(edl=edl, preview=preview, note=f"short {k}: {s.get('title') or ''}", project=project)
        done.append({"short": k, "output": r["output"], "duration": r["duration"], "edl_path": edl_path,
                     "pieces": len(edl["clips"]), "captions": sum(1 for t in edl["texts"] if "_raw" in t)})
    return {"shorts": done, "next": "Check each with view_frames / quality_check."}


@mcp.tool()
def subject_cutout(path: str, output_path: str, background: str = "transparent", model: str = "u2net",
                   start: float = 0.0, duration: float | None = None, clean_edges: bool = True,
                   every: int | None = None, keep: list[list[float]] | None = None,
                   remove: list[list[float]] | None = None) -> dict:
    """Cut the main subject (person, animal, car, product) out of a clip with a local AI model.
    background: "transparent" (ProRes 4444 .mov with alpha - put it in `overlays`, e.g. over
    another clip), "blur", a colour ("#101010", "white") or an image/video file (new background).
    model: birefnet_lite (BEST edges: hair, scarf, fingers; use it for a talking person on a new
    background; slow on a CPU), u2net (any subject, fast, soft edges), u2net_human_seg (people),
    silueta (fastest), or the path of an .onnx file. Downloaded once (43-214 MB; GitHub, then
    Hugging Face). clean_edges: removes the old background's colour from soft edges (no bright halo).
    every: run the model on every Nth frame and fit the frames between to the picture (default: 3
    for birefnet_lite on a CPU, else 1). keep / remove: boxes [x0, y0, x1, y1] as 0..1 of the frame
    that always stay (e.g. a desk in front of the speaker: [[0, 0.78, 1, 1]]) or always go.
    For text behind the subject use texts[].behind_subject instead."""
    from . import subject
    bg = background if background in ("transparent", "blur") or not Path(background).expanduser().exists() \
        else _abs(background)
    return subject.cutout(_abs(path), str(Path(output_path).expanduser().resolve()), bg, model, start, duration,
                          clean_edges, every, keep, remove)


@mcp.tool()
def quality_check(path: str) -> dict:
    """Check a finished video for black frames, frozen picture, silence, loudness (LUFS) and peak."""
    return qa.check(_abs(path))


@mcp.tool()
def speech_segments(path: str, noise_db: float = -35.0, min_silence: float = 0.35) -> dict:
    """Find the parts with speech/sound so you can cut out the pauses (jump cuts). Use each
    `keep` pair as one clip {src, in, out} in an EDL. For cuts chosen from a transcript, pass
    your in/out pairs through snap_cuts."""
    return qa.speech_segments(_abs(path), noise_db, min_silence)


@mcp.tool()
def snap_cuts(path: str, keep: list[list[float]], window: float = 0.35) -> dict:
    """Move cut points to the real pauses in the sound. ALWAYS use it when clip in/out times come
    from transcript word times (they are loose: the first sound of the next sentence stays in the
    clip): keep = [[in, out], ...] -> `keep` with every in just before the speech starts and
    every out just after it ends. `inside_speech` lists boundaries with no pause within `window`
    seconds: choose another sentence end there, or accept a hard jump."""
    return qa.snap_cuts(_abs(path), keep, window)


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
def speech_models() -> dict:
    """The speech-recognition (Whisper) models the user can choose for captions: ready names, the
    models already on this computer (e.g. an OpenAI large-v3 .pt file) and the saved choice. If
    `saved` is empty, ask the user which one to use before the first `transcribe`."""
    return {"saved": captions.saved_model(), "default": captions.DEFAULT_MODEL, "choices": captions.CHOICES,
            "found_on_this_computer": captions.find_local_models(),
            "how": "Pass the name or the file/folder path as transcribe(model=...); remember=true makes it "
                   "the default for next time."}


@mcp.tool()
async def transcribe(path: str, language: str | None = None, model: str | None = None, remember: bool = False,
                     device: str = "auto", prompt: str | None = None, project: str | None = None,
                     ctx: Context | None = None) -> dict:
    """Step 1 of captions: speech to text with word times (needs faster-whisper). The full result
    is saved to `transcript_path`; you get `review`: one numbered line per segment, unsure words
    in [[ ]]. READ IT and correct it with `fix_transcript` before captions (step 2).
    language: e.g. "fa", "en" (set it; detection can be wrong). prompt: names, brands and topic
    words that are spoken (helps the recogniser spell them). model: the user's choice (see
    speech_models): a name (large-v3-turbo, large-v3, medium, small), an OpenAI Whisper .pt file
    (e.g. .../large-v3.pt) or a faster-whisper folder; empty = the saved choice or large-v3-turbo.
    remember=true saves `model` as the default. device: auto (falls back to the CPU when the GPU's
    CUDA libraries are missing), cpu or cuda. If the result has 'gpu_fix', tell the user: the GPU
    failed and the CPU was used; that text is the one install command that makes the GPU work.
    Several files: calls run one at a time (one shared model); sending them together is fine."""
    r = await _with_progress(ctx, lambda tell: captions.transcribe(_abs(path), language, model, device, prompt,
                                                                    progress=tell))
    if remember and model:
        captions.save_model(model)
    model = r["model"]
    tp = _save(_project(project), f"transcript_{Path(path).stem}", r)
    unsure = sum(w.get("p", 1) < 0.5 for s in r["segments"] for w in s.get("words") or [])
    return {"language": r["language"], "duration": r["duration"], "device": r["device"], "model": model,
            "transcript_path": tp, "segments": len(r["segments"]), "unsure_words": unsure,
            "review": captions.review_text(r),
            "next": "Check every line against the meaning, the topic and the language's spelling; "
                    "then call fix_transcript with only the lines that need changes."}


@mcp.tool()
def fix_transcript(transcript_path: str, fixes: dict[str, str]) -> dict:
    """Step 2 of captions: apply YOUR corrections to a transcript. fixes: {"segment number":
    "corrected full text of that line"} - only lines that change; "" removes a line (noise,
    hallucinated text). Fix misheard words, names, spelling (Persian: ی/ک, half-spaces), and
    punctuation; keep the spoken words and their order (do not summarise or translate). Word times
    are re-aligned to the new words. Saves a new file; give its path to make_caption_texts."""
    src = Path(_abs(transcript_path))
    tr = captions.apply_fixes(json.loads(src.read_text(encoding="utf-8")), fixes)
    out = src.with_name(src.stem.removesuffix("_fixed") + "_fixed.json")
    out.write_text(json.dumps(tr, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"transcript_path": str(out), "changed": len(fixes), "review": captions.review_text(tr)}


@mcp.tool()
def make_caption_texts(transcript_path: str | None = None, segments: list[dict] | None = None,
                       style: str = "subtitle", pos: str = "lower", karaoke: bool = True,
                       max_words: int = 4, offset: float = 0.0, keep: list[list[float]] | None = None,
                       project: str | None = None) -> dict:
    """Step 3 of captions: turn a (corrected) transcript into EDL `texts` items, saved to
    `texts_file`. Put that path as a string inside the EDL `texts` list (it can sit next to other
    text items): "texts": ["<texts_file>", {"text": "Title", ...}]. Karaoke highlights the spoken
    word. keep: the [in, out] source pairs of a jump-cut edit (from speech_segments, in clip
    order): times are moved onto the edited timeline and words in removed parts are dropped.
    offset: moves all times (when the clip starts later in the edit)."""
    if transcript_path:
        segments = json.loads(Path(_abs(transcript_path)).read_text(encoding="utf-8"))["segments"]
    if not segments:
        raise ValueError("Give transcript_path (from transcribe or fix_transcript) or segments.")
    if keep:
        segments = captions.remap(segments, keep)
    segs = []
    for s in segments:
        s = dict(s)
        s["start"] = s["start"] + offset
        s["end"] = s["end"] + offset
        s["words"] = [dict(w, start=w["start"] + offset, end=w["end"] + offset) for w in s.get("words", [])]
        segs.append(s)
    items = text.captions_to_items(segs, style, pos, karaoke, max_words)
    path = _save(_project(project), "captions", {"texts": items})
    return {"texts_file": path, "count": len(items),
            "span": [items[0]["start"], items[-1]["end"]] if items else None,
            "use": f'"texts": ["{path}"]'}


@mcp.tool()
def make_sfx(kind: str, duration: float | None = None, project: str | None = None) -> dict:
    """Make a sound effect file (whoosh, hit, riser, click, glitch, boom, swish)."""
    return {"path": str(sfx.make(kind, _project(project), duration))}


@mcp.tool()
def motion_template(name: str, output_path: str, props: dict | None = None, width: int = 1080,
                    height: int = 1920, fps: int = 30, duration: float = 3.0, draft: bool = False) -> dict:
    """Professional animated graphics from ready templates (Kinetograph, installs itself), rendered
    to a TRANSPARENT ProRes 4444 clip - put it in EDL `overlays` (width 1.0, x 0.5, y 0.5, start =
    where it should appear). Templates: title, lower_third, counter, kinetic_words, cta (see
    `templates` in the error for their props). Persian/Arabic text works. Match width/height/fps
    to the edit; colours as '#RRGGBB'. Built on motion-design rules: enter -> hold -> exit, spring
    overshoot, stagger, idle life, a payoff at the key moment. Add a sound effect 2-3 frames
    before each hit (make_sfx + sfx). For a custom design write your own TSX with motion_graphic."""
    r = motion.template(name, str(Path(output_path).expanduser().resolve()), props, width, height, fps,
                        duration, draft)
    r["overlay"] = {"src": r["path"], "x": 0.5, "y": 0.5, "width": 1.0}
    return r


@mcp.tool()
def motion_graphic(entry: str, output_path: str, comp: str | None = None, props: dict | None = None,
                   draft: bool = False) -> dict:
    """Render a Kinetograph (Remotion-style TSX) motion graphic - title, lower third, kinetic text,
    shapes, Lottie - to a TRANSPARENT ProRes 4444 clip for `overlays` (width 1.0 = full frame).
    Needs Node.js (Kinetograph installs itself on first use), and the composition must use
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
def remake_plan(reference: str, aspect: str | None = None, model: str = "omni-1.2-flash",
                multi_shot: bool = True, project: str | None = None) -> dict:
    """Plan a NEW video in the style of a reference when the user has no footage: Google Flow makes
    the shots. Measures the reference (cuts, crossfades, camera move per shot, same-scene groups)
    and groups the shots into the fewest Flow clips ("units"): same-scene shots and short montage
    shots share one clip ("Cut to:"), each shot made >= 1.5 s so its middle can be used; frozen
    shots need no video. For each unit: `look_at` (call it and SEE the reference shots), `beats`
    with the measured `camera` - fill subject/action/setting/lighting with the USER'S content
    (never copy people, logos or brands of the reference), then video_prompt(beats, takes=unit
    takes, duration=generate_s) -> flow_generate_video (dry run first). Then remake_assemble."""
    p = remake.plan(_abs(reference), _project(project) / "remake_work", model, aspect, multi_shot)
    p["saved_plan"] = _save(_project(project), f"remake_plan_{Path(reference).stem}", p)
    p["next"] = ("1) per unit: look_at, write beats, video_prompt, flow_generate_video (continuity: first_frame); "
                 "'still' units: one image; 2) remake_assemble(saved_plan, {unit id: clip path}, output_path, music)")
    return p


@mcp.tool()
def remake_assemble(plan_path: str, clips: dict[str, str], output_path: str, music: str | None = None,
                    preview: bool = True, project: str | None = None) -> dict:
    """Put the generated Flow clips on the reference's timeline: every shot is cut from its own
    segment of its unit's clip (the real cuts in the clip are measured - video models do not cut
    exactly when asked) and keeps the reference's shot length. clips: {"G1": "path.mp4", ...}
    ("G3.1", "G3.2" for a long shot in several clips; the image path for 'still' units).
    Renders a preview by default; check it with view_frames, then render_edl the saved EDL."""
    p = json.loads(Path(_abs(plan_path)).read_text(encoding="utf-8"))
    res = remake.assemble(p, {k: _abs(v) for k, v in clips.items()}, str(Path(output_path).expanduser().resolve()),
                          _abs(music) if music else None)
    res["edl_path"] = _save(_project(project), "edl_remake", res["edl"])
    res["result"] = render.render(json.loads(json.dumps(res["edl"])), _project(project) / "work", preview=preview)
    off = [u for u in res["units"] if u["used"] != "measured"]
    if off:
        res["check"] = (f"{len(off)} clip(s) did not cut as planned ({[u['unit'] for u in off]}): the planned times "
                        "were used - look at those shots with view_frames; regenerate or move 'in' if wrong")
    return res


@mcp.tool()
def video_prompt(beats: list[dict], style: str, duration: float = 8.0, aspect: str = "16:9",
                 subject: str = "", setting: str = "", audio: str = "", negative: str = "",
                 continuity: str = "", model: str = "omni-1.2-flash", takes: str = "single") -> dict:
    """Build a detailed, timed (second-by-second) Google Flow prompt from a shot list and
    check it. ALWAYS use this before flow_generate_video - short prompts give weak clips.
    beats: [{t0, t1, camera (angle + movement + lens, e.g. "low-angle 24mm, slow dolly in"),
    subject?, action (what moves, how fast, the physics), setting?, lighting (source, direction,
    colour), audio?, dialogue?: ["the woman", "line"]}] covering 0..duration, about one change per
    1.5-2 s. model: omni-1.2-flash (default: 3-15 s in whole seconds, 16:9/9:16, English; with both
    first_frame and last_frame at most 10 s), omni-1.1-flash (3-10 s) or veo. takes: "single"
    (one continuous shot, camera moves between beats) or "cuts" (each beat is its own shot).
    dialogue may add the voice: ["the man", "line", "in a calm deep voice"]. style: film look/genre (e.g. "Cinematic 35mm film, teal-orange grade, shallow depth of
    field"). subject/setting/continuity: what stays the same in every beat (face, clothes, props).
    audio: music, ambience and effects. negative: things to leave out as plain words ("text,
    watermark, extra fingers, blurry face"). Fix every item in `issues`, then pass `prompt` to
    flow_generate_video with direct=false."""
    return prompts.build(beats, style, duration, aspect, subject, setting, audio, negative, continuity,
                         model, takes)


@mcp.tool()
async def flow_generate_video(prompt: str, confirm: bool = False, port: int = 0, direct: bool = True,
                              timeout: float = 90, force_new: bool = False, first_frame: str | None = None,
                              last_frame: str | None = None, project: str | None = None) -> list:
    """Generate a video clip with Google Flow (Veo) in your logged-in Chrome.
    confirm=false (default) only types the prompt and returns a screenshot; no credits are spent.
    Ask the user, then call with confirm=true to submit; the new video is downloaded to the
    project folder and can be used as a clip `src` in an EDL. Blade Editor never approves credit
    dialogs; if Flow shows one, the user approves it in the browser. It waits at most `timeout`
    seconds; status "generating" means: call flow_collect (never generate again - the sent clip
    is remembered even if Blade restarts, and a second confirm is refused unless force_new=true
    after the user asks for a new clip).
    first_frame / last_frame: start and/or end the clip on an exact picture, so it joins the
    user's footage: an image path, or "video.mp4@12.5" (the frame at 12.5 s of a video - e.g. the
    last frame of the shot before, or the first frame of the shot after). The images are attached
    in Flow and the prompt says which is first/last; check `frames_visible` and the screenshot in
    the dry run. Write the prompt about the MOTION between the frames."""
    out = _project(project) / "flow"
    return _with_shot(await flow.generate_video(prompt, out, confirm, port, direct, timeout,
                                                force_new=force_new, first_frame=first_frame,
                                                last_frame=last_frame))


@mcp.tool()
async def flow_generate_image(prompt: str, confirm: bool = False, references: list[str] | None = None,
                              port: int = 0, timeout: float = 120, project: str | None = None) -> list:
    """Make still images with Flow's image model (the project's 'Image generation default', e.g.
    Nano Banana 2.1) in the user's Chrome. Use it for KEYFRAMES: make the first and last frame of a
    shot as images, check them, then pass them to flow_generate_video(first_frame=..., last_frame=...)
    - video from keyframes is sharper and keeps the same character/place across shots.
    references: images or "video.mp4@t" frames to keep the same person, product, place or style
    (e.g. a character sheet made first, or the user's own footage). Write the prompt in English:
    subject, pose/action, framing and lens, setting, light, style, aspect (match the video: 9:16
    or 16:9). confirm=false types it only; confirm=true makes and downloads the image(s)."""
    out = _project(project) / "flow" / "images"
    return _with_shot(await flow.generate_image(prompt, out, confirm, port, references, timeout))


@mcp.tool()
async def flow_collect(port: int = 0, limit: int = 4, wait: float = 90, project: str | None = None) -> list:
    """Wait (up to `wait` s) for the clip sent by flow_generate_video and download it; call again
    while status is "generating". With no clip waiting, downloads the newest videos in Flow."""
    return _with_shot(await flow.collect(_project(project) / "flow", port, limit, wait))


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
    # PYTHONUTF8: on Windows, Python then reads and prints UTF-8 everywhere (Persian text on the
    # console gave "UnicodeEncodeError (cp1252)").
    entry = {"type": "stdio", "command": sys.executable, "args": ["-m", "blade_editor.server"],
             "env": {"PYTHONUTF8": "1"}}
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
