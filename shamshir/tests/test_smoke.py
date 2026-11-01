"""End-to-end smoke tests on synthetic media (needs ffmpeg)."""

import subprocess

import numpy as np
import pytest

from shamshir import analyze, audio, autoedit, ff, qa, render


def _ff(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    _ff("-f", "lavfi", "-i", "sine=f=1000:d=0.04,apad=pad_dur=0.46", "-t", "0.5", str(d / "click.wav"))
    _ff("-stream_loop", "39", "-i", str(d / "click.wav"), "-t", "12", "-ar", "44100", str(d / "beat.wav"))
    _ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=3",
        "-f", "lavfi", "-i", "smptehdbars=s=640x360:r=30:d=3",
        "-f", "lavfi", "-i", "mandelbrot=s=640x360:r=30,trim=duration=3",
        "-filter_complex", "[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[2:v]format=yuv420p[c];"
                           "[a][b][c]concat=n=3:v=1[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", str(d / "src.mp4"))
    return d


def test_beats_120bpm(media):
    r = audio.analyze_beats(str(media / "beat.wav"))
    assert abs(r["bpm"] - 120) < 2
    gaps = np.diff(r["beats"])
    assert abs(np.median(gaps) - 0.5) < 0.03


def test_cuts_found(media):
    r = analyze.analyze_video(str(media / "src.mp4"), include_audio=False)
    assert any(abs(c - 3.0) < 0.1 for c in r["cuts"])
    assert any(abs(c - 6.0) < 0.1 for c in r["cuts"])


def test_render_edl_with_persian_text(media, tmp_path):
    out = tmp_path / "out.mp4"
    edl = {
        "output": {"path": str(out), "width": 360, "height": 640, "fps": 30},
        "clips": [
            {"src": str(media / "src.mp4"), "in": 0.5, "out": 2.0, "grade": "teal_orange",
             "effects": [{"type": "zoom_punch", "at": 0}, {"type": "shake", "at": 0.5}]},
            {"src": str(media / "src.mp4"), "in": 3.5, "out": 5.0, "transition": "flash"},
            {"src": str(media / "src.mp4"), "in": 6.5, "out": 8.0, "transition": {"type": "fade", "dur": 0.3}},
        ],
        "texts": [{"text": "سلام دنیا", "start": 0.1, "end": 1.5, "style": "impact", "anim": "pop"}],
        "audio": {"music": str(media / "beat.wav")},
        "sfx": [{"kind": "whoosh", "at": 1.3}],
    }
    r = render.render(edl, tmp_path / "work")
    assert abs(r["duration"] - (1.5 + 1.5 + 1.5 - 0.3)) < 0.1
    assert r["width"] == 360 and r["height"] == 640
    q = qa.check(str(out))
    assert q["loudness_lufs"] is not None and q["peak_dbfs"] < -0.5


def test_auto_edit_cuts_on_beat(media, tmp_path):
    out = tmp_path / "auto.mp4"
    edl = autoedit.build_edl([str(media / "src.mp4")], str(media / "beat.wav"), str(out),
                             "hype", duration=6, width=360, height=640)
    edl.pop("_meta")
    render.render(edl, tmp_path / "work")
    assert abs(ff.probe(out)["duration"] - 6) < 0.15
    r = analyze.analyze_video(str(out))
    assert r["summary"].get("cuts_on_beat_share", 0) >= 0.5


def test_ramp_overlay_lut_and_speech(media, tmp_path):
    lut = tmp_path / "id.cube"
    lut.write_text("LUT_3D_SIZE 2\n" + "".join(f"{r} {g} {b}\n" for b in (0, 1) for g in (0, 1) for r in (0, 1)))
    out = tmp_path / "ramp.mp4"
    edl = {
        "output": {"path": str(out), "width": 360, "height": 640, "max_mb": 2},
        "clips": [{"src": str(media / "src.mp4"), "in": 0, "ramp": [[1, 1.0], [1, 0.5], [2, 2.0]],
                   "focus": "auto", "grade": str(lut)}],
        "overlays": [{"src": str(media / "src.mp4"), "start": 0.5, "end": 2, "width": 0.3}],
        "audio": {"music": str(media / "beat.wav")},
    }
    r = render.render(edl, tmp_path / "work")
    assert abs(r["duration"] - (1 + 2 + 1)) < 0.1
    assert r["size_mb"] < 2
    bursts = tmp_path / "bursts.wav"
    _ff("-f", "lavfi", "-i", "sine=f=300:d=0.4,apad=pad_dur=0.8", "-t", "1.2", str(tmp_path / "b.wav"))
    _ff("-stream_loop", "4", "-i", str(tmp_path / "b.wav"), str(bursts))
    seg = qa.speech_segments(str(bursts))
    assert len(seg["keep"]) == 5  # one kept part per tone burst
