"""Shamshir MCP server: free, local video editing for AI agents."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer

from . import __version__, analyze, audio, autoedit, captions, effects, ff, qa, render, sfx, text

HOME = Path(os.environ.get("SHAMSHIR_HOME", Path.home() / "shamshir_projects")).expanduser()

INSTRUCTIONS = """\
Shamshir edits video locally with ffmpeg. It is free and has no credit limits.

Recommended loop for an edit:
1. probe_media / analyze_video on every input. Use view_frames to SEE the footage; do not guess.
2. With a reference edit: style_from_reference (measures cut rhythm, flashes, shake, colour)
   and view_frames on the reference.
3. Fast path: auto_edit (beat-synced edit in a preset or reference style).
   Full control: write an EDL (see capabilities) and call render_edl with preview=true first.
4. view_frames on the preview, fix the EDL, then render_edl with preview=false.
5. quality_check on the final file. Report the output path to the user.

All times are seconds. Clip effect times are relative to the clip start; texts, sfx and
global_effects use output time. Text supports Persian/Arabic (Vazirmatn font is bundled).
"""

mcp = MCPServer("shamshir", instructions=INSTRUCTIONS, version=__version__)


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


@mcp.tool()
def capabilities() -> dict:
    """List everything the editor can do: EDL format, effects, grades, transitions, text styles,
    text animations, sound effects and auto-edit presets. Read this before writing an EDL."""
    return {
        "version": __version__,
        "projects_dir": str(HOME),
        "edl_format": {
            "output": "{path, width=1080, height=1920, fps=30, fit='cover'|'contain'|'blur', grade, global_grade, crf=18, preset='medium'}",
            "clips[]": "{src (video, image, or 'color:#RRGGBB'), in, out | duration, speed=1, reverse=false, "
                       "fit, focus=[x,y] (0..1 crop centre for cover), mute, volume, grade, effects[], "
                       "transition: 'cut' | 'flash' | 'zoom' | 'glitch' | 'whip' | any ffmpeg xfade name, "
                       "or {type, dur}}",
            "texts[]": "{text, start, end, style, pos ('top','upper','center','lower','bottom','top_left',...) "
                       "or [x,y] fractions, anim, size, color '#RRGGBB', outline_color, font, rotate}",
            "global_effects[]": "same effect objects, times in output seconds",
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


@mcp.tool()
def analyze_video(path: str, project: str | None = None, max_fps: float = 30.0) -> dict:
    """Measure a video's edit language: cut times, shots (length, camera move, shake), flashes,
    activity per second, and music beats (BPM, beats, downbeats, onsets) when it has audio.
    The full result is saved as JSON; the reply holds the main parts."""
    r = analyze.analyze_video(_abs(path), max_fps=max_fps)
    saved = _save(_project(project), f"analysis_{Path(path).stem}", r)
    reply = {k: r[k] for k in ("summary", "cuts", "flashes", "shots")}
    reply["file"] = r["file"]
    reply["per_second"] = r["per_second"][:120]
    if "audio" in r:
        reply["audio"] = {k: r["audio"][k] for k in ("bpm", "beat_interval", "downbeats")}
        reply["audio"]["beats"] = r["audio"]["beats"][:200]
    reply["saved_json"] = saved
    return reply


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
def transcribe(path: str, language: str | None = None, model: str = "small",
               project: str | None = None) -> dict:
    """Speech to text with word times (needs faster-whisper). Use the segments with
    make_caption_texts to get karaoke-style captions for an EDL."""
    r = captions.transcribe(_abs(path), language, model)
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


def main() -> None:
    import sys

    if "--version" in sys.argv:
        print(__version__)
        return
    mcp.run("stdio")


if __name__ == "__main__":
    main()
