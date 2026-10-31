"""Speech-to-text captions with faster-whisper (optional dependency)."""

from __future__ import annotations


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe(path: str, language: str | None = None, model: str = "small") -> dict:
    if not available():
        raise RuntimeError("faster-whisper is not installed. Run: pip install 'shamshir[captions]'")
    from faster_whisper import WhisperModel

    from . import ff

    # Decode with ffmpeg ourselves; this avoids PyAV version problems.
    samples = ff.read_audio_mono(path, sr=16000)
    if len(samples) == 0:
        raise RuntimeError("The file has no audio.")
    m = WhisperModel(model, device="auto", compute_type="auto")
    segments, info = m.transcribe(samples, language=language, word_timestamps=True, vad_filter=True)
    out = []
    for s in segments:
        out.append({
            "start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
            "words": [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
                      for w in (s.words or [])],
        })
    return {"language": info.language, "duration": round(info.duration, 3), "segments": out}
