"""Speech-to-text captions with faster-whisper (optional dependency)."""

from __future__ import annotations


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe(path: str, language: str | None = None, model: str = "small", device: str = "auto") -> dict:
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
        segs, inf = m.transcribe(samples, language=language, word_timestamps=True, vad_filter=True)
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
            "words": [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
                      for w in (s.words or [])],
        })
    return {"language": info.language, "duration": round(info.duration, 3), "device": device,
            "segments": out}
