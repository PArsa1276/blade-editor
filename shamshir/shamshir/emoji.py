"""Colour emoji as PNG stickers (libass cannot draw colour emoji)."""

from __future__ import annotations

import os
import re
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_E = "[\u2600-\u27BF\u2B00-\u2BFF\U0001F000-\U0001FAFF]"
_MOD = "[\uFE0F\U0001F3FB-\U0001F3FF]?"
EMOJI_RE = re.compile(f"(?:[\U0001F1E6-\U0001F1FF]{{2}}|{_E}{_MOD}(?:\u200d{_E}{_MOD})*)")
CACHE = Path(os.environ.get("SHAMSHIR_CACHE", Path.home() / ".cache" / "shamshir")) / "emoji"
_FONTS = [  # (path, size Pillow can draw it at)
    ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109),
    ("/usr/share/fonts/noto/NotoColorEmoji.ttf", 109),
    ("/System/Library/Fonts/Apple Color Emoji.ttc", 160),
    ("C:/Windows/Fonts/seguiemj.ttf", 160),
]
TWEMOJI = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/{}.png"


def split(text: str) -> tuple[str, list[str]]:
    """Return the text without emoji and the emoji found in it."""
    found = EMOJI_RE.findall(text)
    return re.sub(r"\s{2,}", " ", EMOJI_RE.sub("", text)).strip(), found


def png(cluster: str) -> Path:
    """PNG of one emoji: system colour-emoji font first, Twemoji download second (cached)."""
    code = "-".join(f"{ord(ch):x}" for ch in cluster
                    if not (ch == "\ufe0f" and "\u200d" not in cluster))
    out = CACHE / f"{code}.png"
    if out.exists():
        return out
    CACHE.mkdir(parents=True, exist_ok=True)
    for path, size in _FONTS:
        if not Path(path).exists():
            continue
        try:
            font = ImageFont.truetype(path, size)
            im = Image.new("RGBA", (size * 3, size * 2), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((size // 2, size // 4), cluster, font=font, embedded_color=True)
            box = im.getbbox()
            # One glyph is about one em wide; a wider result means the font split the cluster.
            if box and box[2] - box[0] <= size * 1.4:
                im.crop(box).save(out)
                return out
        except OSError:
            continue
    try:
        urllib.request.urlretrieve(TWEMOJI.format(code), out)
        return out
    except OSError as e:
        raise ValueError(f"No colour emoji font found and Twemoji download failed for {cluster!r}: {e}")
