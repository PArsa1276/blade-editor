"""Beat and onset detection with numpy only (no librosa)."""

from __future__ import annotations

import numpy as np

from . import ff

SR = 22050
HOP = 512
NFFT = 2048


def _stft_mag(y: np.ndarray) -> np.ndarray:
    # Centre each frame on its hop time, as librosa does.
    y = np.pad(y, (NFFT // 2, NFFT // 2), mode="reflect" if len(y) > NFFT else "constant")
    if len(y) < NFFT:
        y = np.pad(y, (0, NFFT - len(y)))
    n_frames = 1 + (len(y) - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    window = np.hanning(NFFT).astype(np.float32)
    frames = y[idx] * window
    return np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32)


def onset_envelope(y: np.ndarray) -> np.ndarray:
    """Spectral flux on a log-magnitude spectrum, one value per hop."""
    mag = _stft_mag(y)
    logmag = np.log1p(100.0 * mag)
    flux = np.maximum(0.0, np.diff(logmag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    # Remove a slow local mean so only sharp attacks stay.
    k = 16
    if len(flux) > k:
        kernel = np.ones(k) / k
        local = np.convolve(flux, kernel, mode="same")
        flux = np.maximum(0.0, flux - local)
    m = flux.max()
    return flux / m if m > 0 else flux


def _tempo(env: np.ndarray, fps: float, bpm_min=70.0, bpm_max=180.0) -> float:
    env = env - env.mean()
    n = len(env)
    if n < 8:
        return 120.0
    spec = np.fft.rfft(env, n=2 * n)
    ac = np.fft.irfft(spec * np.conj(spec))[:n]
    lags = np.arange(n)
    with np.errstate(divide="ignore"):
        bpms = 60.0 * fps / np.maximum(lags, 1)
    valid = (bpms >= bpm_min) & (bpms <= bpm_max)
    if not valid.any():
        return 120.0
    # Prefer tempos near 120 BPM a little (log-Gaussian weight), as most edits use that range.
    weight = np.exp(-0.5 * (np.log2(np.maximum(bpms, 1) / 120.0) / 1.0) ** 2)
    score = np.where(valid, ac * weight, -np.inf)
    lag = int(np.argmax(score))
    # Refine with parabolic interpolation.
    if 1 <= lag < n - 1:
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
        denom = a - 2 * b + c
        if denom != 0:
            lag = lag + 0.5 * (a - c) / denom
    return float(60.0 * fps / lag)


def _track_beats(env: np.ndarray, fps: float, bpm: float, tightness: float = 100.0) -> np.ndarray:
    """Dynamic-programming beat tracker (Ellis 2007)."""
    period = 60.0 * fps / bpm
    n = len(env)
    score = env.astype(np.float64).copy()
    back = np.full(n, -1, dtype=np.int64)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    offsets = np.arange(-hi, -lo + 1)
    penalty = -tightness * (np.log(-offsets / period)) ** 2
    for i in range(n):
        prev = i + offsets
        ok = prev >= 0
        if not ok.any():
            continue
        cand = score[prev[ok]] + penalty[ok]
        j = int(np.argmax(cand))
        if cand[j] > 0:
            score[i] = env[i] + cand[j]
            back[i] = prev[ok][j]
    # Start from the best score in the last period.
    tail = max(0, n - int(period))
    i = tail + int(np.argmax(score[tail:]))
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    return np.array(beats[::-1], dtype=np.int64)


def analyze_beats(path: str, start: float = 0.0, duration: float | None = None) -> dict:
    """Return tempo, beat times, downbeat guesses, strong onsets and a loudness curve."""
    y = ff.read_audio_mono(path, SR, start, duration)
    if len(y) < SR // 2:
        return {"has_audio": False, "bpm": None, "beats": [], "downbeats": [], "onsets": [],
                "loudness_per_second": []}
    fps = SR / HOP
    env = onset_envelope(y)
    bpm = _tempo(env, fps)
    beat_idx = _track_beats(env, fps, bpm)
    beats = (beat_idx * HOP / SR + start).round(3)

    # Downbeats: choose the phase (0..3) whose beats have the largest mean onset strength.
    downbeats: list[float] = []
    if len(beat_idx) >= 8:
        strengths = env[beat_idx]
        phase = int(np.argmax([strengths[p::4].mean() for p in range(4)]))
        downbeats = beats[phase::4].tolist()

    # Strong onsets: local peaks clearly above the median.
    thr = max(0.25, float(np.median(env) + 2.5 * np.std(env)))
    peaks = np.where((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]) & (env[1:-1] > thr))[0] + 1
    keep: list[int] = []
    min_gap = int(0.1 * fps)
    for p in peaks:
        if not keep or p - keep[-1] >= min_gap:
            keep.append(int(p))
    onsets = [{"t": round(p * HOP / SR + start, 3), "strength": round(float(env[p]), 3)} for p in keep]

    # Loudness per second (RMS in dBFS).
    loud = []
    for s in range(0, len(y), SR):
        seg = y[s: s + SR]
        rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
        loud.append(round(20 * np.log10(max(rms, 1e-6)), 1))

    # Silence, room noise or a single sound has no tempo: say so instead of a made-up BPM.
    note = None
    if max(loud, default=-120) < -45:
        note = "The audio is (almost) silent: no beat."
    elif len(beats) < 4:
        note = f"No regular beat found ({len(beats)} beat(s)): no BPM."
    if note:
        return {"has_audio": True, "bpm": None, "beat_interval": None, "beats": [], "downbeats": [],
                "onsets": onsets, "loudness_per_second": loud, "note": note}

    return {
        "has_audio": True,
        "bpm": round(bpm, 2),
        "beat_interval": round(60.0 / bpm, 4),
        "beats": beats.tolist(),
        "downbeats": downbeats,
        "onsets": onsets,
        "loudness_per_second": loud,
    }
