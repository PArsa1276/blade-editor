"""Speech-to-text captions with faster-whisper (optional dependency)."""

from __future__ import annotations

import json
import os
from pathlib import Path


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


DEFAULT_MODEL = "large-v3-turbo"  # much better than "small" for Persian/Arabic; about 1.6 GB, downloaded once
SETTINGS = Path(os.environ.get("BLADE_SETTINGS", Path.home() / ".blade-editor" / "settings.json"))

# Models faster-whisper downloads by name (sizes on disk; speed on a normal CPU).
CHOICES = [
    {"model": "large-v3-turbo", "size": "1.6 GB", "quality": "very good", "speed": "medium (default)"},
    {"model": "large-v3", "size": "3 GB", "quality": "best", "speed": "slow on CPU"},
    {"model": "medium", "size": "1.5 GB", "quality": "good", "speed": "medium"},
    {"model": "small", "size": "0.5 GB", "quality": "weak for Persian/Arabic", "speed": "fast"},
    {"model": "<path to a .pt file>", "size": "-", "quality": "OpenAI Whisper file (e.g. large-v3.pt)",
     "speed": "needs: pip install openai-whisper"},
    {"model": "<path to a folder>", "size": "-", "quality": "faster-whisper (CTranslate2) model folder",
     "speed": "-"},
]


def saved_model() -> str | None:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8")).get("speech_model")
    except (OSError, ValueError):
        return None


def save_model(model: str) -> None:
    data = {}
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    data["speech_model"] = model
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def find_local_models() -> list[dict]:
    """Whisper models already on this computer (OpenAI .pt files and Hugging Face downloads)."""
    found = []
    dirs = [Path.home() / ".cache" / "whisper", *[Path(d) for d in os.environ.get("BLADE_WHISPER_DIRS", "").split(os.pathsep) if d]]
    for d in dirs:
        for f in sorted(d.glob("*.pt")) if d.is_dir() else []:
            found.append({"model": str(f), "kind": "openai-whisper .pt", "gb": round(f.stat().st_size / 1e9, 1)})
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    for snap in sorted(hub.glob("models--*whisper*/snapshots/*")) if hub.is_dir() else []:
        kind = "faster-whisper" if (snap / "model.bin").exists() else (
            "transformers (needs conversion)" if (snap / "config.json").exists() else None)
        if kind:
            name = snap.parent.parent.name.removeprefix("models--").replace("--", "/")
            found.append({"model": str(snap), "kind": kind, "repo": name})
    return found


def _resolve(model: str) -> tuple[str, str]:
    """-> (backend, model): 'openai' for .pt files, else 'faster'."""
    p = Path(model).expanduser()
    if p.suffix == ".pt":
        if not p.exists():
            raise ValueError(f"Model file not found: {p}")
        return "openai", str(p)
    if p.is_dir():
        if (p / "model.bin").exists():
            return "faster", str(p)
        if (p / "config.json").exists():
            raise ValueError(
                f"{p} is a Hugging Face 'transformers' Whisper model. Convert it once for faster-whisper:\n"
                "pip install transformers torch ctranslate2\n"
                f'ct2-transformers-converter --model "{p}" --output_dir "{p}-ct2" '
                "--copy_files tokenizer.json preprocessor_config.json --quantization float16\n"
                f'then use model="{p}-ct2". (A .pt file from OpenAI Whisper works without conversion.)')
        raise ValueError(f"{p} is not a Whisper model folder (no model.bin).")
    return "faster", model


def _openai(samples, model: str, language, device: str, prompt) -> tuple[list, str, str]:
    try:
        import torch
        import whisper
    except ImportError:
        raise RuntimeError("A .pt Whisper model needs the openai-whisper package. Install it in Blade's "
                           "environment: ~/.blade-editor/venv (Windows: Scripts\\pip, else bin/pip) "
                           "install openai-whisper") from None
    dev = "cuda" if device != "cpu" and torch.cuda.is_available() else "cpu"
    m = whisper.load_model(model, device=dev)
    r = m.transcribe(samples, language=language, word_timestamps=True, temperature=0.0,
                     condition_on_previous_text=False, initial_prompt=prompt or None, fp16=dev == "cuda")
    segs = [{"start": round(s["start"], 3), "end": round(s["end"], 3), "text": s["text"].strip(),
             "words": [{"start": round(w["start"], 3), "end": round(w["end"], 3), "word": w["word"],
                        "p": round(float(w.get("probability", 1)), 2)} for w in s.get("words", [])]}
            for s in r["segments"]]
    return segs, r.get("language"), dev


# Whisper writes these for music or noise where nobody speaks (seen on the Persian benchmark).
NON_SPEECH = {"موسیقی", "موزیک", "music", "تشویق", "خنده", "applause", "laughter"}


def _fill_holes(samples, segs: list[dict], decode) -> list[dict]:
    """Second pass: speech (VAD) that got no text at all is decoded again on its own.

    In one long pass Whisper sometimes returns nothing for a whole sentence (Persian benchmark:
    6 of 30 sentences, half of all word errors). Holes >= 1 s are decoded alone; segments that
    are only a non-speech label ("موسیقی" for music) are dropped.
    """
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps
    except ImportError:
        return segs
    sr = 16000
    speech = [[a["start"] / sr, a["end"] / sr] for a in get_speech_timestamps(samples, VadOptions(speech_pad_ms=200))]
    merged: list[list[float]] = []
    for a, b in speech:
        if merged and a - merged[-1][1] < 0.5:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    covered = [(s["start"] - 0.3, s["end"] + 0.3) for s in segs]
    holes = []
    for a, b in merged:
        pieces = [(a, b)]
        for c0, c1 in covered:
            pieces = [q for p0, p1 in pieces for q in
                      ([(p0, p1)] if c1 <= p0 or c0 >= p1 else [x for x in ((p0, c0), (c1, p1)) if x[1] > x[0]])]
        holes += [(p0, p1) for p0, p1 in pieces if p1 - p0 >= 1.0]
    new = []
    for a, b in holes:
        a0, b0 = max(0.0, a - 0.3), b + 0.3
        for s in decode(samples[int(a0 * sr):int(b0 * sr)], a0):
            words = "".join(ch for ch in s["text"].lower() if ch.isalnum() or ch.isspace()).split()
            if words and not all(w in NON_SPEECH for w in words):
                new.append(s)
    return sorted(segs + new, key=lambda s: s["start"])


def transcribe(path: str, language: str | None = None, model: str | None = None, device: str = "auto",
               prompt: str | None = None) -> dict:
    from . import ff

    model = model or saved_model() or DEFAULT_MODEL
    backend, model = _resolve(model)
    # Decode with ffmpeg ourselves; this avoids PyAV version problems.
    samples = ff.read_audio_mono(path, sr=16000)
    if len(samples) == 0:
        raise RuntimeError("The file has no audio.")
    duration = round(len(samples) / 16000, 3)
    if backend == "openai":
        segs, lang, dev = _openai(samples, model, language, device, prompt)
        return {"language": lang, "duration": duration, "device": dev, "model": model, "segments": segs}

    if not available():
        raise RuntimeError("faster-whisper is not installed. Run: pip install 'blade-editor[captions]'")
    from faster_whisper import WhisperModel

    def run(dev: str, compute: str):
        m = WhisperModel(model, device=dev, compute_type=compute)
        used.update(m=m)
        # temperature 0 and no carry-over of earlier text: the same file gives the same text, and one
        # wrong sentence does not spread into the next ones.
        # vad speech_pad_ms 1000: the default (400) cut the start/end of sentences and whole
        # sentences were lost. Persian benchmark (FLEURS fa_ir, 3 sets): WER 28.2/37.7/46.6% ->
        # 21.7/37.1/37.3%, CER 15.3/25.7/36.0% -> 8.1/23.3/24.3%; still no text over 40 s of music.
        # (No VAD at all was also better on errors, but it invented text over long music.)
        segs, inf = m.transcribe(samples, language=language, word_timestamps=True, vad_filter=True,
                                 vad_parameters={"speech_pad_ms": 1000},
                                 beam_size=5, temperature=0.0, condition_on_previous_text=False,
                                 initial_prompt=prompt or None)
        return list(segs), inf  # list() runs the decoding here, where a GPU error can be caught

    used: dict = {}

    def run_on(x):
        # The second pass (holes, see _fill_holes) uses the model that worked; no VAD: it is speech.
        segs, _ = used["m"].transcribe(x, language=language or info.language, word_timestamps=True, vad_filter=False,
                               beam_size=5, temperature=0.0, condition_on_previous_text=False,
                               initial_prompt=prompt or None)
        return list(segs)

    try:
        segments, info = run(device, "auto")
    except (RuntimeError, OSError) as e:
        # A GPU without its CUDA libraries (e.g. "cublas64_12.dll is not found") fails late: use the CPU.
        if device == "cpu":
            raise
        segments, info = run("cpu", "int8")
        device = f"cpu (GPU failed: {str(e)[:80]})"
    def seg(s, off: float = 0.0) -> dict:
        return {"start": round(s.start + off, 3), "end": round(s.end + off, 3), "text": s.text.strip(),
                "words": [{"start": round(w.start + off, 3), "end": round(w.end + off, 3), "word": w.word,
                           "p": round(float(w.probability), 2)} for w in (s.words or [])]}

    out = [seg(s) for s in segments]
    out = _fill_holes(samples, out, lambda x, off: [seg(s, off) for s in run_on(x)])
    return {"language": info.language, "duration": round(info.duration, 3), "device": device,
            "model": model, "segments": out}


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
