"""Find the main subject (person, car, product...) in video frames with a local model
(U^2-Net, or BiRefNet for exact edges).

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
_GH = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
_HF = "https://huggingface.co/"
# name: file, size in bytes (checked after the download), download addresses (tried in order: GitHub
# does not answer on every network, Hugging Face is the mirror), model input size, text for the user.
MODELS = {
    "u2net": ("u2net.onnx", 175997641, [_GH + "u2net.onnx", _HF + "tomjackson2023/rembg/resolve/main/u2net.onnx"],
              320, "any subject (people, animals, cars, products), fast, soft edges; 176 MB"),
    "u2net_human_seg": ("u2net_human_seg.onnx", 175997641,
                        [_GH + "u2net_human_seg.onnx", _HF + "tomjackson2023/rembg/resolve/main/u2net_human_seg.onnx"],
                        320, "people only; 176 MB"),
    "silueta": ("silueta.onnx", 44173029, [_GH + "silueta.onnx", _HF + "tomjackson2023/rembg/resolve/main/silueta.onnx"],
                320, "any subject, small and fastest, least exact; 43 MB"),
    "birefnet_lite": ("birefnet_lite.onnx", 224005088,
                      [_HF + "onnx-community/BiRefNet_lite-ONNX/resolve/main/onnx/model.onnx",
                       _GH + "BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx"],
                      1024, "best edges (hair, scarf, fingers, objects on a desk); slow without a GPU; 214 MB"),
}
_sessions: dict = {}


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def _download(name: str, path: Path) -> None:
    """Download a model once; try every address, check the size, never leave a broken file."""
    _, size, urls, _, _ = MODELS[name]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp, errors = path.with_suffix(".part"), []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "blade-editor"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            if tmp.stat().st_size != size:
                raise OSError(f"got {tmp.stat().st_size} bytes, expected {size}")
            tmp.replace(path)
            return
        except Exception as e:  # 504, timeout, blocked host: try the next address
            errors.append(f"{url.split('/')[2]}: {type(e).__name__} {str(e)[:80]}")
            tmp.unlink(missing_ok=True)
    raise RuntimeError(f"Could not download the subject model '{name}' ({'; '.join(errors)}). Download it by hand "
                       f"from {urls[0]} and save it as {path} - or give the path of an .onnx file as `model`.")


def _resolve(model: str) -> tuple[str, Path, int]:
    """(key, file, input size). model: a name from MODELS, or the path of an .onnx file (the
    file name tells the kind: 'birefnet' in it -> 1024 px input, else U^2-Net 320 px)."""
    if model in MODELS:
        return model, MODEL_DIR / MODELS[model][0], MODELS[model][3]
    f = Path(model).expanduser()
    if f.suffix.lower() == ".onnx":
        if not f.exists():
            raise ValueError(f"Subject model file not found: {f}")
        return str(f), f, 1024 if "birefnet" in f.name.lower() else 320
    raise ValueError(f"Unknown subject model '{model}'. Use: {', '.join(MODELS)} or the path of an .onnx file.")


def _session(model: str):
    key, path, size = _resolve(model)
    if key in _sessions:
        return _sessions[key]
    if not available():
        raise RuntimeError("Subject detection needs onnxruntime. Install it in Blade's environment: "
                           "~/.blade-editor/venv (Windows: Scripts\\pip, else bin/pip) install onnxruntime")
    import onnxruntime as ort

    if not path.exists():
        _download(key, path)
    providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
    if "CUDAExecutionProvider" in providers:
        try:  # onnxruntime-gpu needs the same CUDA 12 / cuDNN 9 libraries as the captions
            from . import captions
            captions._load_cuda_libs()
        except Exception:
            pass
    try:
        s = ort.InferenceSession(str(path), providers=providers)
    except Exception:  # a broken GPU setup must not stop the job
        s = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    _sessions[key] = (s, size)
    return _sessions[key]


def device(model: str = "u2net") -> str:
    return "gpu" if "CUDAExecutionProvider" in _session(model)[0].get_providers() else "cpu"


def mask_frame(rgb: np.ndarray, model: str = "u2net") -> np.ndarray:
    """rgb: HxWx3 uint8 -> HxW float mask 0..1 (1 = subject)."""
    s, size = _session(model)
    h, w = rgb.shape[:2]
    x = np.asarray(Image.fromarray(rgb).resize((size, size), Image.BILINEAR), np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    out = s.run(None, {s.get_inputs()[0].name: x.transpose(2, 0, 1)[None]})[0][0, 0]
    if size == 1024:  # BiRefNet gives logits
        out = 1.0 / (1.0 + np.exp(-out))
    out = (out - out.min()) / max(1e-6, float(out.max() - out.min()))
    return np.asarray(Image.fromarray((out * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR),
                      np.float32) / 255.0


def _box(x: np.ndarray, r: int) -> np.ndarray:
    """Mean over a (2r+1) square, edges handled, with integral images (fast, no SciPy)."""
    h, w = x.shape
    c = np.cumsum(np.cumsum(np.pad(x, ((1, 0), (1, 0))), axis=0, dtype=np.float64), axis=1)
    y0, y1 = np.clip(np.arange(h) - r, 0, h), np.clip(np.arange(h) + r + 1, 0, h)
    x0, x1 = np.clip(np.arange(w) - r, 0, w), np.clip(np.arange(w) + r + 1, 0, w)
    tot = c[y1][:, x1] - c[y0][:, x1] - c[y1][:, x0] + c[y0][:, x0]
    return (tot / ((y1 - y0)[:, None] * (x1 - x0)[None, :])).astype(np.float32)


def refine(mask: np.ndarray, rgb: np.ndarray, r: int = 6, eps: float = 1e-3) -> np.ndarray:
    """Guided filter: move the mask's edge onto the edges of the picture itself (grey guide).
    Used for frames between two analysed frames, where the blended mask is a little off."""
    g = rgb.astype(np.float32).mean(axis=2) / 255.0
    mg, mm = _box(g, r), _box(mask, r)
    a = (_box(g * mask, r) - mg * mm) / (_box(g * g, r) - mg * mg + eps)
    b = mm - a * mg
    return np.clip(_box(a, r) * g + _box(b, r), 0.0, 1.0)


def _regions(shape: tuple[int, int], boxes: list | None) -> np.ndarray | None:
    """boxes [[x0, y0, x1, y1], ...] as 0..1 parts of the frame -> a soft 0..1 map."""
    if not boxes:
        return None
    h, w = shape
    m = np.zeros((h, w), np.float32)
    for x0, y0, x1, y1 in boxes:
        m[int(round(float(y0) * h)):int(round(float(y1) * h)), int(round(float(x0) * w)):int(round(float(x1) * w))] = 1.0
    return np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(1.0, w / 200))),
                      np.float32) / 255.0


def mask_video(src: str, out: str, W: int, H: int, fps: int, windows: list[tuple[float, float]] | None = None,
               model: str = "u2net", smooth: float = 0.5, feather: float = 1.5, analysis_width: int = 640,
               every: int | None = None, keep: list | None = None, remove: list | None = None) -> str:
    """Write a grey mask video (white = subject) the length of `src`. Only frames inside `windows`
    [(start, end), ...] are analysed (others are black); None = every frame.
    every: run the model on every Nth frame; frames between get the blend of the two nearest
    masks, moved onto the picture's own edges (guided filter). None = 1 for the fast models and on
    a GPU, 3 for birefnet_lite on a CPU (about 10 s per analysed frame there). Measured on a moving
    shot against the model on every frame: every=4 IoU 0.969, every=8 0.959 (u2net: 0.960), so a
    high value only pays with a still camera (a talking head: 6-8 is fine). keep / remove: boxes [x0, y0, x1, y1] (0..1 of the frame)
    that always stay (a desk in front of the speaker) or always go (a chair)."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                           capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    n = int(round(float(probe or 0) * fps))
    aw = min(analysis_width, W) // 2 * 2
    ah = int(round(H * aw / W)) // 2 * 2
    _, _, size = _resolve(model)
    if every is None:
        every = 3 if size == 1024 and device(model) == "cpu" else 1
    every = max(1, int(every))
    ema = smooth if every == 1 else 0.0  # blended frames are already smooth in time
    keep_m, remove_m = _regions((ah, aw), keep), _regions((ah, aw), remove)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={fps},scale={aw}:{ah}",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                            "-r", str(fps), "-i", "-", "-c:v", "ffv1", out], stdin=subprocess.PIPE)
    blank, fsize = np.zeros((H, W), np.uint8).tobytes(), aw * ah * 3

    def write(m: np.ndarray) -> None:
        if keep_m is not None:
            m = np.maximum(m, keep_m)
        if remove_m is not None:
            m = m * (1.0 - remove_m)
        img = Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
        if feather > 0:
            img = img.filter(ImageFilter.GaussianBlur(feather * W / 1080))
        enc.stdin.write(img.tobytes())

    def flush(run: list, last: tuple | None) -> None:
        """run: [(frame, mask or None)] from one key frame up to (not with) the next key frame `last`."""
        if not run:
            return
        k0 = run[0][1]
        k1 = last[1] if last else k0
        for j, (fr, m) in enumerate(run):
            if m is None:
                t = j / len(run) if last else 0.0
                m = refine((1 - t) * k0 + t * k1, fr)
            write(m)

    prev, run = None, []
    try:
        for i in range(n):
            raw = dec.stdout.read(fsize)
            if len(raw) < fsize:
                break
            t = i / fps
            if windows is not None and not any(a - 0.2 <= t <= b + 0.2 for a, b in windows):
                flush(run, None)
                prev, run = None, []
                enc.stdin.write(blank)
                continue
            fr = np.frombuffer(raw, np.uint8).reshape(ah, aw, 3)
            if not run or len(run) >= every:  # a key frame: the model runs
                m = mask_frame(fr, model)
                # Temporal smoothing: less edge flicker from frame to frame.
                prev = m if prev is None or not ema else ema * prev + (1 - ema) * m
                flush(run, (fr, prev))
                run = [(fr, prev)]
            else:
                run.append((fr, None))
        flush(run, None)
        enc.stdin.close()
        enc.wait()
    finally:
        dec.kill()
    if enc.returncode:
        raise RuntimeError("Could not write the subject mask video.")
    return out


def decontaminate(rgb: np.ndarray, alpha: np.ndarray, radius: float = 6.0) -> np.ndarray:
    """Remove the old background's colour from the soft edge (the bright halo around hair or a
    scarf on a new background): edge pixels get the colour of the solid subject next to them.
    rgb HxWx3 uint8, alpha HxW 0..1 -> rgb uint8."""
    # The solid inside of the subject, 2 px away from the edge (edge pixels can hold wall colour too).
    solid = Image.fromarray(((alpha > 0.97) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(5))
    core = (np.asarray(solid) > 0).astype(np.float32)
    edge = np.maximum(np.clip((0.98 - alpha) / 0.25, 0.0, 1.0), 1.0 - core) * (alpha > 0.02)
    if not edge.any() or not core.any():
        return rgb
    out = rgb.astype(np.float32)
    est, have = np.zeros_like(out), np.zeros(alpha.shape, bool)
    for rad in (radius, radius * 3):  # near the solid subject first; a wider look for the far edge
        blur = lambda x: np.asarray(Image.fromarray(x).filter(ImageFilter.GaussianBlur(rad)), np.float32)  # noqa: E731,B023
        den = blur((core * 255).astype(np.uint8)) / 255.0
        new = (den > 0.02) & ~have
        for c in range(3):
            num = blur((rgb[..., c] * core).astype(np.uint8))
            est[..., c] = np.where(new, num / np.maximum(den, 1e-3), est[..., c])
        have |= new
    w = (edge * have)[..., None]
    return np.clip(out * (1 - w) + est * w, 0, 255).astype(np.uint8)


def _clean_edges(piece: str, mask: str, out: str, W: int, H: int, fps: int) -> str:
    """The clip with the old background's colour removed from the subject's soft edge."""
    size = W * H
    dv = subprocess.Popen(["ffmpeg", "-v", "error", "-i", piece, "-vf", f"fps={fps}", "-f", "rawvideo",
                           "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    dm = subprocess.Popen(["ffmpeg", "-v", "error", "-i", mask, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                          stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(fps), "-i", "-", "-i", piece, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264",
                            "-crf", "10", "-preset", "veryfast", "-pix_fmt", "yuv444p", "-c:a", "copy", out],
                           stdin=subprocess.PIPE)
    try:
        while True:
            a, b = dv.stdout.read(size * 3), dm.stdout.read(size)
            if len(a) < size * 3 or len(b) < size:
                break
            rgb = np.frombuffer(a, np.uint8).reshape(H, W, 3)
            alpha = np.frombuffer(b, np.uint8).reshape(H, W).astype(np.float32) / 255.0
            enc.stdin.write(decontaminate(rgb, alpha, max(2.0, 6.0 * W / 1080)).tobytes())
        enc.stdin.close()
        enc.wait()
    finally:
        dv.kill()
        dm.kill()
    if enc.returncode:
        raise RuntimeError("Could not write the cleaned subject video.")
    return out


def cutout(src: str, out: str, background: str = "transparent", model: str = "u2net",
           start: float = 0.0, duration: float | None = None, clean_edges: bool = True,
           every: int | None = None, keep: list | None = None, remove: list | None = None) -> dict:
    """Cut the subject out of a clip. background: transparent (ProRes 4444 .mov with alpha),
    blur, a colour (#RRGGBB or name) or an image/video file. clean_edges: remove the old
    background's colour from hair and other soft edges (no bright halo on the new background)."""
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
    mask = mask_video(piece, f"{work}_mask.mkv", W, H, fps, None, model, every=every, keep=keep, remove=remove)
    fg, temp = piece, [piece, mask]
    if clean_edges and background != "blur":
        fg = _clean_edges(piece, mask, f"{work}_fg.mkv", W, H, fps)
        temp.append(fg)
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
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", fg, "-i", mask, *extra, "-filter_complex", graph,
                    "-map", "[v]", "-map", "0:a?", *venc, "-c:a", "aac", "-shortest", out], check=True)
    for f in temp:
        Path(f).unlink(missing_ok=True)
    return {"output": str(Path(out).resolve()), "background": background, "model": model, "size": f"{W}x{H}",
            "fps": fps, "device": device(model), "edges_cleaned": fg != piece}
