"""Small wrappers around ffmpeg and ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np


class FFError(RuntimeError):
    pass


def _bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FFError(f"{name} is not installed or not on PATH.")
    return path


# ffmpeg/ffprobe print UTF-8 (file names, Persian metadata). Without encoding="utf-8", Windows
# decodes with its code page: a Persian title tag then made ffprobe's output None.


def run(args: list[str], timeout: float | None = None) -> str:
    """Run ffmpeg with the given arguments. Raise FFError with the stderr tail on failure."""
    cmd = [_bin("ffmpeg"), "-hide_banner", "-nostdin", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        raise FFError(f"ffmpeg failed (code {proc.returncode}):\n{tail}")
    return proc.stderr


def probe(path: str | Path) -> dict:
    """Return a compact description of a media file."""
    path = Path(path)
    if not path.exists():
        raise FFError(f"File not found: {path}")
    cmd = [
        _bin("ffprobe"), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FFError(f"ffprobe failed: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    fmt = data.get("format", {})
    info: dict = {
        "path": str(path.resolve()),
        "duration": float(fmt.get("duration", 0) or 0),
        "size_bytes": int(fmt.get("size", 0) or 0),
        "video": None,
        "audio": None,
    }
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and info["video"] is None:
            if s.get("disposition", {}).get("attached_pic"):
                continue
            rate = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1"
            try:
                fps = float(Fraction(rate)) if rate != "0/0" else 0.0
            except (ZeroDivisionError, ValueError):
                fps = 0.0
            rotation = 0
            for sd in s.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rotation = int(sd["rotation"])
            w, h = int(s.get("width", 0)), int(s.get("height", 0))
            if abs(rotation) in (90, 270):
                w, h = h, w
            info["video"] = {
                "codec": s.get("codec_name"),
                "width": w,
                "height": h,
                "fps": round(fps, 3),
                "frames": int(s["nb_frames"]) if s.get("nb_frames", "").isdigit() else None,
                "pix_fmt": s.get("pix_fmt"),
                "rotation": rotation,
            }
        elif s.get("codec_type") == "audio" and info["audio"] is None:
            info["audio"] = {
                "codec": s.get("codec_name"),
                "sample_rate": int(s.get("sample_rate", 0) or 0),
                "channels": int(s.get("channels", 0) or 0),
            }
    if info["duration"] == 0 and info["video"] and info["video"]["frames"] and info["video"]["fps"]:
        info["duration"] = info["video"]["frames"] / info["video"]["fps"]
    return info


def read_gray_frames(path: str | Path, width: int = 160, fps: float | None = None,
                     start: float = 0.0, duration: float | None = None) -> tuple[np.ndarray, float]:
    """Decode a video to small grayscale frames. Return (frames[N,H,W] uint8, fps)."""
    info = probe(path)
    if not info["video"]:
        raise FFError("The file has no video stream.")
    v = info["video"]
    src_fps = v["fps"] or 30.0
    use_fps = min(fps or src_fps, src_fps)
    height = max(2, int(round(width * v["height"] / max(1, v["width"]) / 2)) * 2)
    args = [_bin("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(path)]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    args += ["-vf", f"fps={use_fps},scale={width}:{height}:flags=area,format=gray",
             "-f", "rawvideo", "-"]
    proc = subprocess.run(args, capture_output=True)
    if proc.returncode != 0:
        raise FFError(proc.stderr.decode(errors="replace")[-2000:])
    frame_size = width * height
    n = len(proc.stdout) // frame_size
    frames = np.frombuffer(proc.stdout[: n * frame_size], dtype=np.uint8).reshape(n, height, width)
    return frames, use_fps


def read_audio_mono(path: str | Path, sr: int = 22050, start: float = 0.0,
                    duration: float | None = None) -> np.ndarray:
    """Decode audio to a mono float32 array. Return an empty array when no audio exists."""
    info = probe(path)
    if not info["audio"]:
        return np.zeros(0, dtype=np.float32)
    args = [_bin("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(path)]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    args += ["-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    proc = subprocess.run(args, capture_output=True)
    if proc.returncode != 0:
        raise FFError(proc.stderr.decode(errors="replace")[-2000:])
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def extract_frame(path: str | Path, t: float, out: str | Path, width: int = 480) -> Path:
    out = Path(out)
    run(["-ss", f"{max(0.0, t):.3f}", "-i", str(path), "-frames:v", "1",
         "-vf", f"scale={width}:-2", str(out)])
    return out
