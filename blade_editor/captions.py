"""Speech-to-text captions with faster-whisper (optional dependency)."""

from __future__ import annotations


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


DEFAULT_MODEL = "large-v3-turbo"  # much better than "small" for Persian/Arabic; about 1.6 GB, downloaded once


def transcribe(path: str, language: str | None = None, model: str = DEFAULT_MODEL, device: str = "auto",
               prompt: str | None = None) -> dict:
    if not available():
        raise RuntimeError("faster-whisper is not installed. Run: pip install 'blade-editor[captions]'")
    from faster_whisper import WhisperModel

    from . import ff

    # Decode with ffmpeg ourselves; this avoids PyAV version problems.
    samples = ff.read_audio_mono(path, sr=16000)
    if len(samples) == 0:
        raise RuntimeError("The file has no audio.")
    def run(dev: str, compute: str):
        m = WhisperModel(model, device=dev, compute_type=compute)
        # temperature 0 and no carry-over of earlier text: the same file gives the same text, and one
        # wrong sentence does not spread into the next ones.
        segs, inf = m.transcribe(samples, language=language, word_timestamps=True, vad_filter=True,
                                 beam_size=5, temperature=0.0, condition_on_previous_text=False,
                                 initial_prompt=prompt or None)
        return list(segs), inf  # list() runs the decoding here, where a GPU error can be caught

    try:
        segments, info = run(device, "auto")
    except (RuntimeError, OSError) as e:
        # A GPU without its CUDA libraries (e.g. "cublas64_12.dll is not found") fails late: use the CPU.
        if device == "cpu":
            raise
        segments, info = run("cpu", "int8")
        device = f"cpu (GPU failed: {str(e)[:80]})"
    out = []
    for s in segments:
        out.append({
            "start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
            "words": [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word,
                       "p": round(float(w.probability), 2)}
                      for w in (s.words or [])],
        })
    return {"language": info.language, "duration": round(info.duration, 3), "device": device,
            "segments": out}


def review_text(tr: dict, low: float = 0.5) -> str:
    """One numbered line per segment for the agent to read; unsure words are in [[ ]]."""
    lines = []
    for i, s in enumerate(tr["segments"]):
        words = s.get("words") or []
        body = " ".join((f"[[{w['word'].strip()}]]" if w.get("p", 1) < low else w["word"].strip())
                        for w in words) if words else s["text"]
        lines.append(f"{i}. [{s['start']:.1f}-{s['end']:.1f}] {body}")
    return "\n".join(lines)


def _norm(w: str) -> str:
    w = w.strip().replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").replace("\u200c", "")
    return "".join(ch for ch in w if ch.isalnum()).lower()


def _align(old: list[dict], new: list[str], start: float, end: float) -> list[dict]:
    """Give corrected words times: matched or replaced words keep theirs, the rest share the time
    of what they replace (by length)."""
    import difflib

    out: list[dict | None] = [None] * len(new)
    ops = difflib.SequenceMatcher(None, [_norm(w["word"]) for w in old], [_norm(w) for w in new],
                                  autojunk=False).get_opcodes()
    for tag, i1, i2, j1, j2 in ops:
        if j1 == j2:
            continue
        if i2 - i1 == j2 - j1:
            for k in range(j2 - j1):
                out[j1 + k] = {"start": old[i1 + k]["start"], "end": old[i1 + k]["end"]}
            continue
        if i1 < i2:
            t0, t1 = old[i1]["start"], old[i2 - 1]["end"]
        else:
            t0 = old[i1 - 1]["end"] if i1 > 0 else start
            t1 = old[i1]["start"] if i1 < len(old) else end
        if t1 - t0 < 0.08 * (j2 - j1):
            t1 = t0 + 0.08 * (j2 - j1)
        weights = [max(1, len(w)) for w in new[j1:j2]]
        t = t0
        for k, wt in enumerate(weights):
            d = (t1 - t0) * wt / sum(weights)
            out[j1 + k] = {"start": round(t, 3), "end": round(t + d, 3)}
            t += d
    return [dict(o, word=" " + w, p=1.0) for o, w in zip(out, new)]


def apply_fixes(tr: dict, fixes: dict) -> dict:
    """fixes: {segment number: corrected text}; empty text removes the segment."""
    segs = [dict(s) for s in tr["segments"]]
    for k, txt in fixes.items():
        i = int(k)
        if not 0 <= i < len(segs):
            raise ValueError(f"No segment {i}: the transcript has {len(segs)} (0-{len(segs) - 1}).")
        txt = " ".join(str(txt).split())
        if not txt:
            segs[i] = None
            continue
        s = segs[i]
        words = _align(s.get("words") or [], txt.split(), s["start"], s["end"])
        segs[i] = dict(s, text=txt, words=words, start=min(s["start"], words[0]["start"]),
                       end=max(s["end"], words[-1]["end"]), edited=True)
    return dict(tr, segments=[s for s in segs if s])


def remap(segments: list[dict], keep: list) -> list[dict]:
    """Move times from the source onto a jump-cut timeline made of the `keep` [in, out] pairs, in
    order. Words in removed parts are dropped."""
    spans, t = [], 0.0
    for a, b in keep:
        spans.append((float(a), float(b), t))
        t += float(b) - float(a)

    def where(x: float):
        return next(((a, b, o) for a, b, o in spans if a <= x <= b), None)

    out = []
    for s in segments:
        words = []
        for w in s.get("words") or []:
            sp = where((w["start"] + w["end"]) / 2)
            if sp:
                a, b, o = sp
                words.append(dict(w, start=round(o + max(a, w["start"]) - a, 3),
                                  end=round(o + min(b, w["end"]) - a, 3)))
        if words:
            out.append(dict(s, words=words, start=words[0]["start"], end=words[-1]["end"]))
        elif not s.get("words") and (sp := where(s["start"])):
            a, b, o = sp
            out.append(dict(s, start=o + s["start"] - a, end=o + min(b, s["end"]) - a))
    return out
