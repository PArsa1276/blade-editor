"""End-to-end smoke tests on synthetic media (needs ffmpeg)."""

import subprocess

import numpy as np
import pytest

from blade_editor import analyze, audio, autoedit, ff, qa, render


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


def test_stabilize_and_emoji(media, tmp_path):
    shaky = tmp_path / "shaky.mp4"
    _ff("-f", "lavfi", "-i", "testsrc=s=640x360:r=30:d=3",
        "-vf", "crop=560:320:x='40+20*sin(t*13)':y='20+15*sin(t*17)',scale=640:360", str(shaky))
    out = tmp_path / "st.mp4"
    edl = {"output": {"path": str(out), "width": 640, "height": 360},
           "clips": [{"src": str(shaky), "stabilize": True, "ramp": [[1.5, 1.0], [1.5, 0.5]]}],
           "texts": [{"text": "داغ 🔥", "start": 0, "end": 2}]}
    r = render.render(edl, tmp_path / "work")
    assert abs(r["duration"] - 4.5) < 0.1

    def jitter(p):
        f, _ = ff.read_gray_frames(str(p), width=320, duration=1.4)
        f = f.astype(np.float32)
        win = np.outer(np.hanning(f.shape[1]), np.hanning(f.shape[2])).astype(np.float32)
        return np.mean([np.abs(analyze._phase_shift(f[i - 1], f[i], win)[:2]).sum() for i in range(1, len(f))])

    assert jitter(out) < 0.4 * jitter(shaky)


@pytest.mark.skipif(not __import__("os").environ.get("BLADE_TEST_KG_ENTRY"),
                    reason="set BLADE_TEST_KG_ENTRY to a Kinetograph entry to run")
def test_motion_graphic_alpha(tmp_path):
    import os
    from blade_editor import motion
    r = motion.render(os.environ["BLADE_TEST_KG_ENTRY"], tmp_path / "mg.mov", draft=True)
    assert r["pix_fmt"].startswith("yuva")


def test_register_writes_both_configs_and_keeps_old_keys(tmp_path, monkeypatch):
    import json
    from blade_editor import server
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}))
    for d in (tmp_path / ".config" / "Claude", tmp_path / "Library" / "Application Support" / "Claude",
              tmp_path / "AppData" / "Claude"):
        d.mkdir(parents=True)
    written = server.register()
    assert len(written) == 2
    cli = json.loads((tmp_path / ".claude.json").read_text())
    assert cli["theme"] == "dark" and "other" in cli["mcpServers"]
    assert cli["mcpServers"]["blade-editor"]["args"] == ["-m", "blade_editor.server"]
    desk = json.loads(open(written[1]).read())
    assert "blade-editor" in desk["mcpServers"]


def test_camera_copy_replays_reference_sway(media, tmp_path):
    from blade_editor import camera
    ref = tmp_path / "sway.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=2",
        "-vf", "crop=800:450:x='240+160*sin(2*PI*t)':y=135,scale=640:360", str(ref))
    m0 = camera.measure(str(ref))
    assert any("sway" in d for d in camera.describe(m0))
    out = tmp_path / "copy.mp4"
    render.render({"output": {"path": str(out), "width": 640, "height": 360},
                   "clips": [{"src": str(media / "src.mp4"), "in": 3, "out": 5,
                              "effects": [{"type": "camera", "keys": camera.keyframes(m0)}]}]}, tmp_path / "w")
    m1 = camera.measure(str(out))
    n = min(len(m0["x"]), len(m1["x"]))
    assert np.corrcoef(m0["x"][:n], m1["x"][:n])[0, 1] > 0.9
    keys = camera.preset("spin360_holds", 4)
    assert keys[-1][3] == 360 and keys[2][3] == keys[1][3]  # holds at each stop


def test_repeat_analysis_is_refused(media):
    from blade_editor import server
    server._CALLS.clear()
    p = str(media / "src.mp4")
    assert "cuts" in server.analyze_video(p)
    assert "cuts" in server.analyze_video(p, sensitivity="low")
    assert server.analyze_video(p).get("limit_reached")


def test_too_long_ramp_is_refused_and_many_short_clips_keep_sync(media, tmp_path):
    with pytest.raises(ValueError, match="past the end"):
        render.render({"output": {"path": str(tmp_path / "x.mp4"), "width": 320, "height": 568},
                       "clips": [{"src": str(media / "src.mp4"), "in": 8.5, "ramp": [[1, 1], [1, 0.5]]}]},
                      tmp_path / "w")
    clips = [{"src": str(media / "src.mp4"), "in": 0.1 * i, "out": 0.1 * i + 0.487} for i in range(24)]
    out = tmp_path / "sync.mp4"
    render.render({"output": {"path": str(out), "width": 320, "height": 568}, "clips": clips,
                   "audio": {"music": str(media / "beat.wav")}}, tmp_path / "w")
    lens = qa.check(str(out))["stream_seconds"]
    assert abs(lens["video"] - lens["audio"]) < 0.05 and abs(lens["video"] - 24 * 0.487) < 0.05


def test_short_music_is_looped_to_the_asked_length(media, tmp_path):
    short = tmp_path / "short.wav"
    _ff("-i", str(media / "beat.wav"), "-t", "5", str(short))
    edl = autoedit.build_edl([str(media / "src.mp4")], str(short), str(tmp_path / "a.mp4"), "hype",
                             duration=9, width=320, height=568)
    assert edl["_meta"]["duration"] == 9 and edl["_meta"]["warnings"]


def test_rtl_karaoke_runs_in_visual_order():
    from blade_editor import text
    words = [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.5} for i, w in enumerate("یک دو سه".split())]
    raw = [i["_raw"] for i in text.captions_to_items([{"start": 0, "end": 1.5, "text": "", "words": words}])]
    # libass puts colour runs left to right, so for Persian the later words come first.
    assert raw[1] == "{\\fsp0}سه {\\1c&H00E6FF&}دو{\\1c&HFFFFFF&} یک"


def test_transcript_fix_and_jump_cut_remap(tmp_path):
    import json
    from blade_editor import captions, render
    tr = {"segments": [{"start": 1.0, "end": 3.0, "text": "salam dost aziz",
                        "words": [{"start": 1.0, "end": 1.5, "word": " salam", "p": 0.9},
                                  {"start": 1.6, "end": 2.2, "word": " dost", "p": 0.3},
                                  {"start": 2.3, "end": 3.0, "word": " aziz", "p": 0.9}]},
                       {"start": 5.0, "end": 6.0, "text": "noise", "words": []}]}
    assert "[[dost]]" in captions.review_text(tr)
    fixed = captions.apply_fixes(tr, {"0": "salam doostane aziz man", "1": ""})
    w = fixed["segments"][0]["words"]
    assert len(fixed["segments"]) == 1 and [x["word"].strip() for x in w] == ["salam", "doostane", "aziz", "man"]
    assert w[0]["start"] == 1.0 and w[1]["start"] == 1.6  # kept and replaced words keep their times
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(w, w[1:]))
    # Jump cut keeps 0.5-1.55 and 2.25-3.5: "salam" moves to 0.5, the cut word "doostane" goes.
    m = captions.remap(fixed["segments"], [[0.5, 1.55], [2.25, 3.5]])[0]["words"]
    assert [x["word"].strip() for x in m] == ["salam", "aziz", "man"] and m[0]["start"] == 0.5
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"texts": [{"text": "hi", "start": 0, "end": 1}]}))
    edl = {"output": {"path": str(tmp_path / "o.mp4"), "width": 320, "height": 240},
           "clips": [{"src": "color:black", "duration": 1}], "texts": [str(f), {"text": "t", "start": 0, "end": 1}]}
    assert len(render.normalize(edl)["texts"]) == 2


def test_no_bpm_without_a_beat(tmp_path):
    from blade_editor import audio
    for name, src in (("quiet", "anoisesrc=a=0.002:d=5"), ("tone", "sine=f=200:d=5")):
        f = tmp_path / f"{name}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, str(f)], check=True)
        r = audio.analyze_beats(str(f))
        assert r["bpm"] is None and r["beats"] == [] and r["note"]


def test_speech_model_choice_and_openai_pt(tmp_path, monkeypatch):
    import sys
    import types
    from blade_editor import captions
    monkeypatch.setattr(captions, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setenv("BLADE_WHISPER_DIRS", str(tmp_path))
    pt = tmp_path / "large-v3.pt"
    pt.write_bytes(b"x")
    assert {"model": str(pt), "kind": "openai-whisper .pt", "gb": 0.0} in captions.find_local_models()
    captions.save_model(str(pt))
    assert captions.saved_model() == str(pt)
    # Fake openai-whisper and torch: check that the saved .pt file goes to that backend.
    seen = {}

    class M:
        def transcribe(self, audio, **kw):
            seen.update(kw)
            return {"language": "fa", "segments": [{"start": 0.0, "end": 1.0, "text": " سلام",
                    "words": [{"start": 0.0, "end": 1.0, "word": " سلام", "probability": 0.4}]}]}
    monkeypatch.setitem(sys.modules, "whisper", types.SimpleNamespace(load_model=lambda m, device: seen.update(m=m) or M()))
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False)))
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=1", str(wav)], check=True)
    r = captions.transcribe(str(wav), "fa")
    assert seen["m"] == str(pt) and seen["word_timestamps"] and r["segments"][0]["words"][0]["p"] == 0.4
    assert "[[سلام]]" in captions.review_text(r)


def test_edit_ideas_and_user_recipes(tmp_path, monkeypatch):
    from blade_editor import recipes
    monkeypatch.setattr(recipes, "USER_DIR", tmp_path)
    assert recipes.ideas("slow motion speed ramp dance")[0]["name"] == "velocity_edit"
    assert recipes.ideas("travel vlog trip")[0]["name"] == "cinematic_travel"
    recipes.save("My Car Edit", {"tags": "car night drift", "style": {"cut_every": 1}})
    top = recipes.ideas("night car drift edit")[0]
    assert top["name"] == "my_car_edit" and top["source"] == "user"


def test_video_prompt_is_timed_and_checked():
    from blade_editor import prompts
    beats = [{"t0": 0, "t1": 3, "camera": "wide 24mm, slow dolly in", "action": "a red car drifts around a corner, tyre smoke",
              "lighting": "low sun from the left, long shadows"},
             {"t0": 3, "t1": 6, "camera": "low-angle 35mm, tracking left", "action": "the car straightens and speeds past"},
             {"t0": 6, "t1": 8, "camera": "static close-up 85mm", "action": "smoke clears around the rear light",
              "dialogue": ["the driver", "Again."]}]
    r = prompts.build(beats, "Cinematic 35mm film, warm grade", subject="a red 1990s sports car",
                      setting="empty mountain road at sunset", audio="engine roar, tyre screech, deep bass music",
                      negative="text, watermark, people")
    assert r["ok"], r["issues"]
    p = r["prompt"]
    assert p.startswith("Single continuous shot. No scene cuts.") and "[0-3s] Wide 24mm" in p
    assert 'the driver says: "Again."' in p and "No text. No watermark. No people." in p
    cuts = prompts.build(beats, "x", takes="cuts", audio="a")["prompt"]
    assert "[3-6s] Cut to:" in cuts and "No scene cuts" not in cuts
    assert any("3-10 s" in i for i in prompts.build(beats, "x", duration=12, audio="a")["issues"])
    veo = prompts.build(beats, "x", model="veo", audio="a", negative="text")["prompt"]
    assert "[00.00-03.00s] Camera: wide 24mm" in veo and "Negative prompt: text." in veo
    bad = prompts.build(beats[:1], "x", model="veo", negative="no text")
    assert any("last beat" in i for i in bad["issues"]) and any("'no'" in i for i in bad["issues"])


def test_versions_and_restore(tmp_path, monkeypatch):
    from blade_editor import server
    monkeypatch.setattr(server, "HOME", tmp_path / "projects")
    out = str(tmp_path / "v.mp4")
    edl = {"output": {"path": out, "width": 320, "height": 240}, "clips": [{"src": "color:red", "duration": 1}]}
    assert server._render_edl(edl=edl, note="first")["version"] == 1
    edl["clips"][0]["src"] = "color:blue"
    assert server._render_edl(edl=edl, note="blue")["version"] == 2
    vs = server.edl_versions(out)["versions"]
    assert [v["note"] for v in vs] == ["first", "blue"]
    r = server.restore_version(out, 1)
    assert r["version"] == 3 and server.edl_versions(out)["versions"][-1]["note"] == "restored v001"


def test_edit_playbook_sections():
    from blade_editor import server
    idx = server.edit_playbook()
    assert {"hook", "rhythm", "speed", "checklist"} <= set(idx["sections"])
    r = server.edit_playbook("hook, checklist")
    assert "first 1-2 s" in r["hook"] and "quality_check" in r["checklist"]


def test_slowmo_modes():
    from blade_editor import render
    assert render._slow(1.0, "auto", 30, 1080, 1920, True) == []
    assert "minterpolate" in render._slow(0.5, "auto", 30, 1080, 1920, True)[-1]  # final render
    assert render._slow(0.5, "auto", 30, 540, 960, False) == ["framerate=fps=30"]  # preview
    assert render._slow(0.9, "auto", 30, 1080, 1920, True) == ["framerate=fps=30"]
    assert render._slow(0.5, "none", 30, 1080, 1920, True) == []


def test_text_behind_subject(tmp_path):
    """Needs onnxruntime and the u2net model already downloaded (skipped otherwise: 176 MB)."""
    import numpy as np
    import pytest
    from PIL import Image, ImageDraw
    from blade_editor import render, subject
    if not subject.available() or not (subject.MODEL_DIR / "u2net.onnx").exists():
        pytest.skip("onnxruntime or the u2net model is not here")
    im = Image.new("RGB", (540, 960), (40, 60, 90))
    ImageDraw.Draw(im).ellipse([170, 300, 370, 660], fill=(230, 60, 40))
    im.save(tmp_path / "s.png")
    edl = {"output": {"path": str(tmp_path / "o.mp4"), "width": 540, "height": 960, "fps": 10},
           "clips": [{"src": str(tmp_path / "s.png"), "duration": 1}],
           "texts": [{"text": "BLADE", "start": 0, "end": 1, "style": "yellow", "size": 520,
                      "pos": [0.5, 0.5], "anim": "none", "behind_subject": True}]}
    out = render.render(edl, tmp_path / "w")["output"]
    f = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", out, "-frames:v", "1", str(f)], check=True)
    a = np.asarray(Image.open(f).convert("RGB")).astype(int)
    centre, side = a[480, 270], a[480, 60]
    assert centre[0] > 180 and centre[1] < 120  # subject (red) stays in front of the text
    assert side[0] > 180 and side[1] > 180       # the yellow text shows beside the subject
