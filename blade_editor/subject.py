"""Find the main subject (person, car, product...) in video frames with a local U^2-Net model.

Used for text behind the subject and for cutouts. The model (ONNX, run with onnxruntime) is
downloaded once to ~/.blade-editor/models. Masks are smoothed over time so edges do not flicker.
"""

from __future__ import annotations

import os
import subprocess
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

MODEL_DIR = Path(os.environ.get("BLADE_MODELS", Path.home() / ".blade-editor" / "models"))
_BASE = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
MODELS = {
    "u2net": ("u2net.onnx", "any subject (people, animals, cars, products); 176 MB"),
    "u2net_human_seg": ("u2net_human_seg.onnx", "people only, cleaner on humans; 176 MB"),
    "silueta": ("silueta.onnx", "any subject, small and faster, a bit less exact; 43 MB"),
}
_sessions: dict = {}


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def _session(model: str):
    if model not in MODELS:
        raise ValueError(f"Unknown subject model '{model}'. Use: {', '.join(MODELS)}")
    if model in _sessions:
        return _sessions[model]
    if not available():
        raise RuntimeError("Subject detection needs onnxruntime. Install it in Blade's environment: "
                           "~/.blade-editor/venv (Windows: Scripts\\pip, else bin/pip) install onnxruntime")
    import onnxruntime as ort

    path = MODEL_DIR / MODELS[model][0]
    if not path.exists():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(_BASE + MODELS[model][0], tmp)  # once; about 43-176 MB
        tmp.replace(path)
    providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
    try:
        s = ort.InferenceSession(str(path), providers=providers)
    except Exception:  # a broken GPU setup must not stop the job
        s = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    _sessions[model] = s
    return s


def mask_frame(rgb: np.ndarray, model: str = "u2net") -> np.ndarray:
    """rgb: HxWx3 uint8 -> HxW float mask 0..1 (1 = subject)."""
    s = _session(model)
    h, w = rgb.shape[:2]
    x = np.asarray(Image.fromarray(rgb).resize((320, 320), Image.BILINEAR), np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    out = s.run(None, {s.get_inputs()[0].name: x.transpose(2, 0, 1)[None]})[0][0, 0]
    out = (out - out.min()) / max(1e-6, float(out.max() - out.min()))
    return np.asarray(Image.fromarray((out * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR),
                      np.float32) / 255.0


def mask_video(src: str, out: str, W: int, H: int, fps: int, windows: list[tuple[float, float]] | None = None,
               model: str = "u2net", smooth: float = 0.5, feather: float = 1.5, analysis_width: int = 640) -> str:
    """Write a grey mask video (white = subject) the length of `src`. Only frames inside `windows`
    [(start, end), ...] are analysed (others are black); None = every frame."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                           capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    n = int(round(float(probe or 0) * fps))
    aw = min(analysis_width, W) // 2 * 2
    ah = int(round(H * aw / W)) // 2 * 2
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={fps},scale={aw}:{ah}",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                            "-r", str(fps), "-i", "-", "-c:v", "ffv1", out], stdin=subprocess.PIPE)
    prev, blank, size = None, np.zeros((H, W), np.uint8).tobytes(), aw * ah * 3
    try:
        for i in range(n):
            raw = dec.stdout.read(size)
            if len(raw) < size:
                break
            t = i / fps
            if windows is not None and not any(a - 0.2 <= t <= b + 0.2 for a, b in windows):
                prev = None
                enc.stdin.write(blank)
                continue
            m = mask_frame(np.frombuffer(raw, np.uint8).reshape(ah, aw, 3), model)
            # Temporal smoothing: less edge flicker from frame to frame.
            prev = m if prev is None else smooth * prev + (1 - smooth) * m
            img = Image.fromarray((np.clip(prev, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
            if feather > 0:
                img = img.filter(ImageFilter.GaussianBlur(feather * W / 1080))
            enc.stdin.write(img.tobytes())
        enc.stdin.close()
        enc.wait()
    finally:
        dec.kill()
    if enc.returncode:
        raise RuntimeError("Could not write the subject mask video.")
    return out


def cutout(src: str, out: str, background: str = "transparent", model: str = "u2net",
           start: float = 0.0, duration: float | None = None) -> dict:
    """Cut the subject out of a clip. background: transparent (ProRes 4444 .mov with alpha),
    blur, a colour (#RRGGBB or name) or an image/video file."""
    import json
    work = Path(out).with_suffix("")
    work.parent.mkdir(parents=True, exist_ok=True)
    piece = f"{work}_src.mp4"
    cut = ["-ss", f"{start:.3f}"] + (["-t", f"{duration:.3f}"] if duration else [])
    subprocess.run(["ffmpeg", "-v", "error", "-y", *cut, "-i", src, "-c:v", "libx264", "-crf", "12",
                    "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", piece], check=True)
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                      "stream=width,height,r_frame_rate", "-of", "json", piece],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace").stdout)["streams"][0]
    W, H = int(info["width"]), int(info["height"])
    a, b = info["r_frame_rate"].split("/")
    fps = max(1, round(int(a) / int(b or 1)))
    mask = mask_video(piece, f"{work}_mask.mkv", W, H, fps, None, model)
    if background == "transparent":
        out = str(Path(out).with_suffix(".mov"))
        graph = "[0:v]format=rgba[c];[1:v]format=gray[m];[c][m]alphamerge[v]"
        venc = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
        extra = []
    else:
        if background == "blur":
            bg = "[0:v]split[c][b];[b]boxblur=20:2[bg]"
            extra = []
        elif Path(background).exists():
            extra = ["-i", background]
            bg = f"[2:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[bg];[0:v]null[c]"
        else:
            extra = ["-f", "lavfi", "-i", f"color=c={background}:s={W}x{H}:r={fps}"]
            bg = "[2:v]null[bg];[0:v]null[c]"
        graph = (f"{bg};[1:v]format=gray[m];[c]format=rgba[cr];[cr][m]alphamerge[fg];"
                 "[bg][fg]overlay=shortest=1,format=yuv420p[v]")
        venc = ["-c:v", "libx264", "-crf", "18", "-preset", "medium"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", piece, "-i", mask, *extra, "-filter_complex", graph,
                    "-map", "[v]", "-map", "0:a?", *venc, "-c:a", "aac", "-shortest", out], check=True)
    for f in (piece, mask):
        Path(f).unlink(missing_ok=True)
    return {"output": str(Path(out).resolve()), "background": background, "model": model, "size": f"{W}x{H}",
            "fps": fps}
