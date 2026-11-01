"""Build ASS subtitle files for titles, captions and animated text.

libass shapes right-to-left scripts (Persian, Arabic) correctly, so all text goes
through ASS and the ffmpeg `ass` filter.
"""

from __future__ import annotations

import re
from pathlib import Path

FONTS_DIR = Path(__file__).parent / "fonts"

# name: (font, size at 1080 short side, primary, outline colour, outline px, shadow px, bold, spacing)
STYLES = {
    "impact":   ("Vazirmatn Black", 140, "#FFFFFF", "#000000", 6, 0, 0, 1),
    "subtitle": ("Vazirmatn", 64, "#FFFFFF", "#000000", 4, 2, 1, 0),
    "minimal":  ("Vazirmatn", 52, "#FFFFFF", "#000000", 0, 3, 0, 2),
    "neon":     ("Vazirmatn Black", 104, "#FFFFFF", "#00E5FF", 5, 0, 0, 2),
    "yellow":   ("Vazirmatn Black", 104, "#FFE600", "#000000", 6, 0, 0, 1),
    "red":      ("Vazirmatn Black", 110, "#FF2D2D", "#000000", 5, 0, 0, 1),
    "boxed":    ("Vazirmatn", 56, "#000000", "#FFFFFF", 14, 0, 1, 0),
}
ANIMS = ("none", "fade", "pop", "slide_up", "zoom_out", "typewriter", "flicker", "word_by_word")

_POS = {  # name: (alignment numpad, x frac, y frac)
    "top": (8, 0.5, 0.12), "upper": (5, 0.5, 0.30), "center": (5, 0.5, 0.5),
    "lower": (5, 0.5, 0.68), "bottom": (2, 0.5, 0.86),
    "top_left": (7, 0.06, 0.08), "top_right": (9, 0.94, 0.08),
    "bottom_left": (1, 0.06, 0.92), "bottom_right": (3, 0.94, 0.92),
}


_RTL = re.compile("[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]")


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"Colour must be #RRGGBB, not {hex_color!r}")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def build_ass(items: list[dict], width: int, height: int) -> str:
    """items: {text, start, end, style, pos, size, color, outline_color, anim, font}"""
    k = min(width, height) / 1080.0
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    for name, (font, size, prim, outc, ol, sh, bold, sp) in STYLES.items():
        border_style = 3 if name == "boxed" else 1
        lines.append(
            f"Style: {name},{font},{int(size * k)},{_ass_color(prim)},{_ass_color('#FFE600')},"
            f"{_ass_color(outc)},{_ass_color('#000000', 0x80)},{-1 if bold else 0},0,0,0,100,100,"
            f"{sp},0,{border_style},{max(0, ol * k):.1f},{sh * k:.1f},5,{int(60 * k)},{int(60 * k)},0,1")
    lines += ["", "[Events]",
              "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    for it in items:
        text = str(it.get("text", "")).strip()
        if not text:
            continue
        start, end = float(it["start"]), float(it["end"])
        if end <= start:
            raise ValueError(f"Text '{text}' ends before it starts.")
        style = it.get("style", "impact")
        if style not in STYLES:
            raise ValueError(f"Unknown text style '{style}'. Use: {', '.join(STYLES)}")
        anim = it.get("anim", "pop")
        if anim not in ANIMS:
            raise ValueError(f"Unknown text anim '{anim}'. Use: {', '.join(ANIMS)}")
        pos = it.get("pos", "center")
        if isinstance(pos, (list, tuple)):
            an, fx, fy = 5, float(pos[0]), float(pos[1])
        else:
            if pos not in _POS:
                raise ValueError(f"Unknown pos '{pos}'. Use: {', '.join(_POS)} or [x, y] fractions.")
            an, fx, fy = _POS[pos]
        x, y = int(fx * width), int(fy * height)
        tags = [f"\\an{an}", f"\\pos({x},{y})"]
        if _RTL.search(text):
            # libass stops joining Arabic-script letters when letter spacing is not zero.
            tags.append("\\fsp0")
        if it.get("size"):
            tags.append(f"\\fs{int(float(it['size']) * k)}")
        if it.get("color"):
            tags.append(f"\\1c&H{_ass_color(it['color'])[4:]}&")
        if it.get("outline_color"):
            tags.append(f"\\3c&H{_ass_color(it['outline_color'])[4:]}&")
        if it.get("font"):
            tags.append(f"\\fn{it['font']}")
        if it.get("rotate"):
            tags.append(f"\\frz{float(it['rotate']):.1f}")
        dur_ms = int((end - start) * 1000)
        body = _esc(text)
        layer = int(it.get("layer", 1))

        def ev(s: float, e: float, extra: str, txt: str = body) -> None:
            lines.append(f"Dialogue: {layer},{_ts(s)},{_ts(e)},{style},,0,0,0,,"
                         f"{{{''.join(tags)}{extra}}}{txt}")

        if anim == "none":
            ev(start, end, "")
        elif anim == "fade":
            ev(start, end, "\\fad(180,180)")
        elif anim == "pop":
            ev(start, end, "\\fscx30\\fscy30\\t(0,110,\\fscx118\\fscy118)\\t(110,220,\\fscx100\\fscy100)\\fad(0,120)")
        elif anim == "zoom_out":
            ev(start, end, "\\fscx170\\fscy170\\alpha&HFF&\\t(0,200,\\fscx100\\fscy100\\alpha&H00&)\\fad(0,120)")
        elif anim == "slide_up":
            tags.pop(1)
            ev(start, end, f"\\move({x},{y + int(90 * k)},{x},{y},0,220)\\fad(140,140)")
        elif anim == "flicker":
            t, on, step = start, True, 0.06
            while t < min(end, start + 0.42):
                if on:
                    ev(t, t + step, "")
                t += step
                on = not on
            if t < end:
                ev(t, end, "\\fad(0,120)")
        elif anim == "typewriter":
            chars = list(text)
            total = min(dur_ms / 1000 * 0.6, 0.045 * len(chars))
            step = total / max(1, len(chars))
            for i in range(1, len(chars) + 1):
                s = start + (i - 1) * step
                e = start + i * step if i < len(chars) else end
                ev(s, e, "", _esc("".join(chars[:i])))
        elif anim == "word_by_word":
            words = text.split()
            per = (end - start) / max(1, len(words))
            for i in range(len(words)):
                shown = " ".join(words[: i + 1])
                ev(start + i * per, start + (i + 1) * per if i < len(words) - 1 else end,
                   "\\fscx100\\fscy100" if i else "\\fscx40\\fscy40\\t(0,120,\\fscx100\\fscy100)",
                   _esc(shown))
    return "\n".join(lines) + "\n"


def captions_to_items(segments: list[dict], style: str = "subtitle", pos: str = "lower",
                      karaoke: bool = True, max_words: int = 4) -> list[dict]:
    """Convert transcript segments [{start,end,text,words?[{start,end,word}]}] to text items.

    With word timings, groups of up to `max_words` words are shown and the spoken word is
    highlighted (CapCut style).
    """
    items: list[dict] = []
    for seg in segments:
        words = seg.get("words") or []
        if not words:
            items.append({"text": seg["text"], "start": seg["start"], "end": seg["end"],
                          "style": style, "pos": pos, "anim": "fade"})
            continue
        for g in range(0, len(words), max_words):
            group = words[g: g + max_words]
            for j, w in enumerate(group):
                s = w["start"]
                e = group[j + 1]["start"] if j + 1 < len(group) else w["end"]
                if karaoke:
                    toks = [_esc(ww["word"].strip()) for ww in group]
                    runs = [" ".join(toks[:j]), "{\\1c&H00E6FF&}" + toks[j] + "{\\1c&HFFFFFF&}", " ".join(toks[j + 1:])]
                    raw = ""
                    if _RTL.search(" ".join(toks)):
                        # libass orders right-to-left text only inside each colour run and puts the runs
                        # left to right, so the runs go in visual order: later words first.
                        runs.reverse()
                        raw = "{\\fsp0}"
                    raw += " ".join(r for r in runs if r)
                    items.append({"_raw": raw, "text": "x", "start": s, "end": max(e, s + 0.05),
                                  "style": style, "pos": pos, "anim": "none"})
                elif j == 0:
                    items.append({"text": " ".join(x["word"].strip() for x in group),
                                  "start": s, "end": group[-1]["end"], "style": style, "pos": pos,
                                  "anim": "pop"})
    return items


def write_ass(items: list[dict], width: int, height: int, out: str | Path) -> Path:
    raw_items = [i for i in items if "_raw" in i]
    plain = [i for i in items if "_raw" not in i]
    content = build_ass(plain, width, height)
    if raw_items:
        extra = []
        for it in raw_items:
            an, fx, fy = _POS[it.get("pos", "lower")]
            extra.append(f"Dialogue: 2,{_ts(it['start'])},{_ts(it['end'])},{it['style']},,0,0,0,,"
                         f"{{\\an{an}\\pos({int(fx * width)},{int(fy * height)})}}{it['_raw']}")
        content += "\n".join(extra) + "\n"
    out = Path(out)
    out.write_text(content, encoding="utf-8")
    return out
