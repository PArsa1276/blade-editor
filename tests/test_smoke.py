"""End-to-end smoke tests on synthetic media (needs ffmpeg)."""

import subprocess
from pathlib import Path

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


def test_long_video_to_shorts(tmp_path, monkeypatch):
    import json
    from blade_editor import server
    monkeypatch.setattr(server, "HOME", tmp_path / "projects")
    src = tmp_path / "long.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=15:d=40",
                    "-f", "lavfi", "-i", "sine=f=220:d=40", "-filter_complex",
                    "[1:a]volume='if(between(t,20,32),0.9,0.1)*if(lt(mod(t,4),3),1,0)':eval=frame[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(src)], check=True)
    segs = [{"start": k * 4.0, "end": k * 4.0 + 3, "text": "Why is this loud?" if k == 5 else f"Line {k}.",
             "words": [{"start": k * 4.0, "end": k * 4.0 + 3, "word": " word", "p": 0.9}]} for k in range(10)]
    tp = tmp_path / "tr.json"
    tp.write_text(json.dumps({"segments": segs}))
    h = server.find_highlights(str(src), count=1, min_seconds=8, max_seconds=12, transcript_path=str(tp))
    best = h["candidates"][0]
    assert 18 <= best["start"] <= 22 and "loud/energetic" in best["why"]
    r = server.make_shorts(str(src), [{"start": best["start"], "end": best["end"], "title": "HOOK"}],
                           str(tmp_path / "out"), transcript_path=str(tp), preview=True)["shorts"][0]
    assert r["pieces"] >= 2 and r["duration"] < best["end"] - best["start"]  # pauses removed


def test_motion_templates_follow_the_rules():
    import os
    import pytest
    from blade_editor import motion
    for name in motion.TEMPLATES:
        src = (motion.TEMPLATES_DIR / name / "index.tsx").read_text()
        assert 'env.BLADE_BG ?? "transparent"' in src  # exact alpha needs the background switch
        assert "exitT(" in src and "clamp" in src      # exit inside the duration, clamped frames
        assert 'dir={' in src                          # Persian/Arabic text is laid out right to left
    with pytest.raises(ValueError):
        motion.template("nope", "x.mov")
    if not os.environ.get("BLADE_TEST_KG"):
        pytest.skip("set BLADE_TEST_KG=1 to render a template with Kinetograph (slow)")
    import tempfile
    out = Path(tempfile.mkdtemp()) / "t.mov"
    r = motion.template("counter", out, {"value": 50, "label": "تست"}, 270, 480, 15, 1.5, draft=True)
    assert r["pix_fmt"].startswith("yuva") and abs(r["duration"] - 1.5) < 0.2


def test_normalize_keeps_the_callers_edl_and_project_names_are_checked(tmp_path, monkeypatch):
    edl = {"output": {"path": str(tmp_path / "o.mp4"), "width": 320, "height": 240},
           "clips": [{"src": "color:red", "duration": 1, "effects": [], "transition": {"type": "flash"}},
                     {"src": "color:blue", "duration": 1, "transition": "whip"}]}
    for _ in range(2):
        n = render.normalize(edl)
    assert edl["clips"][0]["effects"] == [] and "dur" not in edl["clips"][0]["transition"]
    assert [e["type"] for e in n["clips"][0]["effects"]] == ["flash"]
    from blade_editor import server
    monkeypatch.setattr(server, "HOME", tmp_path)
    assert server._project("my edit").name == "my edit"
    for bad in ["../x", "a/b", "..", "c:\\x"]:
        with pytest.raises(ValueError):
            server._project(bad)


def test_velocity_preset_ramps_on_downbeats(media, tmp_path):
    out = tmp_path / "vel.mp4"
    edl = autoedit.build_edl([str(media / "src.mp4")], str(media / "beat.wav"), str(out),
                             "velocity", duration=6, width=360, height=640)
    meta = edl.pop("_meta")
    downs = {round(d, 3) for d in audio.analyze_beats(str(media / "beat.wav"))["downbeats"]}
    t, flashes = 0.0, []
    for c in edl["clips"]:
        assert c["ramp"] and all(sp in (0.35, 2.0) for _, sp in c["ramp"])
        slow = c["ramp"][0][1] == 0.35
        if any(e["type"] == "flash" for e in c["effects"]):
            assert slow and round(t, 3) in downs  # flash only on a strong beat, with the slow part
            flashes.append(t)
        t += sum(o / sp for o, sp in c["ramp"])
    assert flashes and len(flashes) <= meta["duration"] / 2 + 1  # at most one per bar (4 beats = 2 s)
    # The agent gets the slow shots to check by eye (output times match the clips).
    slow = meta["slow_shots"]
    assert [x["clip"] for x in slow] == [k for k, c in enumerate(edl["clips"]) if len(c["ramp"]) > 1]
    assert all(x["end"] > x["start"] for x in slow) and "view_frames" in meta["check"]
    out = render.render(edl, tmp_path / "work", preview=True)["output"]
    assert abs(ff.probe(out)["duration"] - 6) < 0.15
    s = analyze.analyze_video(out)["summary"]
    assert s.get("cuts_on_beat_share", 0) >= 0.5


def test_ramp_with_optical_flow_and_fast_part_renders(media, tmp_path):
    # Flow slow motion scales its piece; the fast piece must get the same size for concat.
    edl = {"output": {"path": str(tmp_path / "r.mp4"), "width": 160, "height": 90, "fps": 30},
           "clips": [{"src": str(media / "src.mp4"), "in": 0.5, "ramp": [[0.2, 0.35], [1.2, 2.0]]}]}
    out = render.render(edl, tmp_path / "work")["output"]
    assert abs(ff.probe(out)["duration"] - (0.2 / 0.35 + 0.6)) < 0.1
    assert not list((tmp_path / "work").rglob("*.part.mkv"))


def test_cut_to_bright_shot_is_not_a_flash_but_a_real_flash_is(tmp_path):
    # dark 1 s -> bright 0.6 s (getting darker, like a fast camera move) -> dark 1 s: two cuts and
    # no flash. The old detector called it a flash (brightness fell by > 25 within 0.3 s).
    dark = "testsrc2=s=320x180:r=30:d={d},eq=brightness=-0.35"
    _ff("-f", "lavfi", "-i", dark.format(d=1), "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=0.6,eq=brightness='0.4-0.5*t':eval=frame",
        "-f", "lavfi", "-i", dark.format(d=1) + ",hflip",
        "-filter_complex", "[0][1][2]concat=n=3:v=1[v]", "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
        str(tmp_path / "bright_cut.mp4"))
    r = analyze.analyze_video(str(tmp_path / "bright_cut.mp4"), include_audio=False)
    assert r["flashes"] == []
    assert any(abs(c - 1.0) < 0.07 for c in r["cuts"]) and any(abs(c - 1.6) < 0.07 for c in r["cuts"])
    # A real 3-frame flash (Blade's flash effect) on one dark shot is still found.
    _ff("-f", "lavfi", "-i", dark.format(d=2), "-c:v", "libx264", "-preset", "ultrafast", str(tmp_path / "dark.mp4"))
    edl = {"output": {"path": str(tmp_path / "flash.mp4"), "width": 320, "height": 180, "fps": 30},
           "clips": [{"src": str(tmp_path / "dark.mp4"), "in": 0, "out": 2,
                      "effects": [{"type": "flash", "at": 1.0, "dur": 0.1, "amount": 0.85}]}]}
    out = render.render(edl, tmp_path / "work")["output"]
    r = analyze.analyze_video(out, include_audio=False)
    assert len(r["flashes"]) == 1 and abs(r["flashes"][0] - 1.0) < 0.07


def _fast_pan_then_cut(tmp_path):
    # A very fast back-and-forth pan (the picture changes a lot every frame, no jump), then a
    # real cut at 2.0 s.
    _ff("-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=2,crop=320:180:x='800+800*sin(t*12)':y='450+450*sin(t*7)'",
        "-f", "lavfi", "-i", "mandelbrot=s=320x180:r=30,trim=duration=1",
        "-filter_complex", "[0]format=yuv420p,setsar=1[a];[1]format=yuv420p,setsar=1[b];[a][b]concat=n=2:v=1[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", str(tmp_path / "fast.mp4"))
    return analyze.analyze_video(str(tmp_path / "fast.mp4"), include_audio=False)["cuts"]


def test_real_cut_after_fast_motion_is_found(tmp_path):
    assert any(abs(c - 2.0) < 0.07 for c in _fast_pan_then_cut(tmp_path))


def test_fast_motion_makes_at_most_one_false_cut(tmp_path):
    # Was 4: the same picture moved by a fast pan is not a cut. One is left (0.1 s): there the
    # pan moves ~70 px of a 160 px frame in one frame and the shift match is weak, like a cut.
    assert len([c for c in _fast_pan_then_cut(tmp_path) if abs(c - 2.0) >= 0.07]) <= 1


def test_motion_next_to_a_frozen_tail_is_not_a_cut(tmp_path):
    # Changing picture (noise that grows stronger, like faster and faster motion), then the last
    # frame held for 0.15 s (as at the end of r2): the frozen frames must not make the normal
    # change just before them look like a cut.
    _ff("-f", "lavfi", "-i", "nullsrc=s=320x180:r=30:d=2,geq=lum='128+(10+190*T*T/4)*(random(0)-0.5)':cb=128:cr=128,"
        "tpad=stop_mode=clone:stop_duration=0.15",
        "-c:v", "ffv1", str(tmp_path / "tail.mkv"))  # lossless: the held frames are exactly equal
    assert analyze.analyze_video(str(tmp_path / "tail.mkv"), include_audio=False)["cuts"] == []


def test_slow_ramp_and_slow_speed_do_not_freeze_at_the_end(tmp_path):
    # A slowed stream used to end one source frame early (x 1/speed); the gap was a frozen frame.
    _ff("-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=4,crop=320:180:x='t*200':y=300",
        "-c:v", "libx264", "-preset", "ultrafast", str(tmp_path / "pan.mp4"))
    for i, clip in enumerate([{"ramp": [[0.3, 0.35], [0.6, 2.0]], "slowmo": "flow"},
                              {"speed": 0.25, "out": 1.0, "slowmo": "blend"}]):
        edl = {"output": {"path": str(tmp_path / f"o{i}.mp4"), "width": 320, "height": 180, "fps": 30},
               "clips": [{"src": str(tmp_path / "pan.mp4"), "in": 0.5, **clip}]}
        out = render.render(edl, tmp_path / "work")["output"]
        frames, _ = ff.read_gray_frames(out, width=160, fps=30)
        d = np.abs(np.diff(frames.astype(np.float32), axis=0)).mean(axis=(1, 2))
        assert d[-3:].min() > 0.3, (clip, d[-6:])


def test_auto_edit_windows_do_not_cross_a_source_cut(media, tmp_path):
    # src.mp4 has cuts at 3 s and 6 s. Velocity reads more source than the shot length (2x
    # parts), and no clip may run across a cut inside the source.
    edl = autoedit.build_edl([str(media / "src.mp4")], str(media / "beat.wav"), str(tmp_path / "v.mp4"),
                             "velocity", duration=6, width=360, height=640)
    for c in edl["clips"]:
        a = c["in"]
        b = a + sum(o for o, _ in c["ramp"])
        assert not any(a + 0.02 < x < b - 0.02 for x in (3.0, 6.0)), (a, b)


def test_crossfade_is_found_but_a_blur_pulse_is_not(tmp_path):
    # 0.4 s crossfade (1.2-1.6 s) between two views of the same kind of picture: no single
    # frame changes much, so the frame-to-frame rules found no cut here.
    _ff("-f", "lavfi", "-i", "mandelbrot=s=320x180:r=30:start_x=-0.743643887:start_y=0.131825904,trim=duration=3",
        "-f", "lavfi", "-i", "mandelbrot=s=320x180:r=30:start_x=-1.25066:start_y=0.02012,trim=duration=3",
        "-filter_complex", "[0]format=yuv420p,settb=AVTB[a];[1]format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[b];"
                           "[a][b]xfade=transition=fade:duration=0.4:offset=1.2[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", str(tmp_path / "fade.mp4"))
    cuts = analyze.analyze_video(str(tmp_path / "fade.mp4"), include_audio=False)["cuts"]
    assert len(cuts) == 1 and 1.2 <= cuts[0] <= 1.6, cuts
    # A blur pulse on one shot (a velocity effect) mixes frames too, but the content stays.
    k = "if(between(T\\,1.2\\,1.8)\\,1-abs(T-1.5)/0.3\\,0)"
    _ff("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=3",
        "-filter_complex", f"[0]split[a][b];[b]boxblur=12[bb];[a][bb]blend=all_expr='A*(1-{k})+B*{k}'[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", str(tmp_path / "blur.mp4"))
    assert analyze.analyze_video(str(tmp_path / "blur.mp4"), include_audio=False)["cuts"] == []


def test_transcribe_keeps_speech_edges(tmp_path, monkeypatch):
    # The VAD must keep 1 s around speech: with the default 0.4 s whole Persian sentences were
    # dropped (benchmarks/HISTORY_FA.md, captions). Checked with a fake faster-whisper.
    import sys
    import types
    from blade_editor import captions
    seen = {}

    class M:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, samples, **kw):
            seen.update(kw)
            return [], types.SimpleNamespace(language="fa", duration=1.0)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=M))
    _ff("-f", "lavfi", "-i", "sine=f=300:d=1", str(tmp_path / "a.wav"))
    captions.transcribe(str(tmp_path / "a.wav"), language="fa", model="large-v3-turbo", device="cpu")
    assert seen["vad_filter"] and seen["vad_parameters"]["speech_pad_ms"] == 1000


def test_speech_without_text_is_decoded_again(monkeypatch):
    # Whisper sometimes returns nothing for a whole sentence; speech holes >= 1 s are decoded
    # again alone, and a hole that only gives the music label is dropped.
    pytest.importorskip("faster_whisper")
    import faster_whisper.vad as fvad
    from blade_editor import captions
    sr = 16000
    monkeypatch.setattr(fvad, "get_speech_timestamps", lambda x, opts: [
        {"start": 0, "end": 2 * sr}, {"start": 5 * sr, "end": 8 * sr}, {"start": 12 * sr, "end": 14 * sr}])
    calls = []

    def decode(x, off):
        calls.append(round(off, 1))
        if off < 10:
            return [{"start": off + 0.3, "end": off + 1.5, "text": "یک جمله که جا افتاده بود", "words": []}]
        return [{"start": off + 0.3, "end": off + 0.9, "text": "موسیقی", "words": []},
                {"start": off + 1.0, "end": off + 1.5, "text": "PYM JBZ", "words": []}]

    first = [{"start": 0.2, "end": 1.9, "text": "جمله اول", "words": []}]
    out = captions._fill_holes(np.zeros(15 * sr, dtype=np.float32), first, decode, "fa")
    assert calls == [4.7, 11.7]                     # only the two holes, not the covered speech
    assert [s["text"] for s in out] == ["جمله اول", "یک جمله که جا افتاده بود"]


def test_remake_assemble_cuts_each_shot_from_its_own_segment(tmp_path):
    # A "generated" clip whose cuts are 0.3 s away from the plan (models do not cut on time):
    # every shot must be taken from inside its own segment, at the reference length.
    from blade_editor import remake
    _ff("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=1.8", "-f", "lavfi", "-i", "smptehdbars=s=320x180:r=30:d=0.9",
        "-f", "lavfi", "-i", "mandelbrot=s=320x180:r=30,trim=duration=1.8",
        "-filter_complex", "[0]format=yuv420p,setsar=1[a];[1]format=yuv420p,setsar=1[b];[2]format=yuv420p,setsar=1[c];"
                           "[a][b][c]concat=n=3:v=1[v]", "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
        str(tmp_path / "g1.mp4"))
    true_cuts = [1.8, 2.7]
    plan = {"reference": {"aspect": "16:9"},
            "shots": [{"index": k, "duration": 0.5, "transition_in": "cut"} for k in range(3)],
            "units": [{"id": "G1", "kind": "generate", "calls": 1, "shots": [0, 1, 2], "generate_s": 4.5,
                       "beats": [{"t0": 0.0, "keep": 0.5}, {"t0": 1.5, "keep": 0.5}, {"t0": 3.0, "keep": 0.5}]}]}
    res = remake.assemble(plan, {"G1": str(tmp_path / "g1.mp4")}, str(tmp_path / "out.mp4"))
    assert res["units"][0]["used"] == "measured"
    bounds = [0.0, *true_cuts, 4.5]
    for k, c in enumerate(res["edl"]["clips"]):
        assert bounds[k] < c["in"] < c["out"] < bounds[k + 1], (k, c)
        assert abs((c["out"] - c["in"]) / c.get("speed", 1.0) - 0.5) < 0.01


def test_remake_plan_groups_shots_and_measures_the_camera(media, tmp_path):
    from blade_editor import remake
    p = remake.plan(str(media / "src.mp4"), tmp_path / "w")
    n = len(analyze.analyze_video(str(media / "src.mp4"), include_audio=False)["shots"])
    assert p["reference"]["shots"] == len(p["shots"]) == n >= 2
    assert all(s["camera"] for s in p["shots"])
    assert sum(len(u["shots"]) for u in p["units"]) == n
    # the colour bars (3-6 s) do not move: one still image, no Flow call
    assert [u["kind"] for u in p["units"] if 1 in u["shots"]] == ["still"]
    assert p["flow_calls"] <= p["one_call_per_shot"] == n - 1
    for u in p["units"]:
        assert u["kind"] in ("generate", "still")
        if u["kind"] == "generate":
            assert 3 <= u["generate_s"] <= 10 and u["beats"][-1]["t1"] == u["generate_s"]


def test_reference_style_repeats_shot_pattern_and_flashes_inside_shots(media, tmp_path):
    # A reference with short and long shots (1 and 3 beats) and flashes on beats INSIDE shots.
    assert autoedit._beat_pattern([0.5, 2.0, 2.5], 4.0, 0.5) == [1, 3, 1, 3]
    style = {"cut_every": 2, "punch": 0, "flash": 0.8, "shake": 0, "glitch": 0, "grade": None,
             "transition": "cut", "pattern": [1, 3], "flash_rate": 0.5, "flash_on_cut": 0.0}
    edl = autoedit.build_edl([str(media / "src.mp4")], str(media / "beat.wav"), str(tmp_path / "p.mp4"),
                             style, duration=6, width=360, height=640)
    lens = [round((c["out"] - c["in"]) / 0.5) for c in edl["clips"]]
    assert lens[:4] in ([1, 3, 1, 3], [3, 1, 3, 1]), lens  # the grid may start on the first beat
    t, flashes = 0.0, []
    for c in edl["clips"]:
        flashes += [(t, f["at"]) for f in c["effects"] if f["type"] == "flash"]
        t += c["out"] - c["in"]
    assert len(flashes) == 3
    for start, at in flashes:
        assert at >= 0.1, "inside the shot, not on the cut"
        assert abs((start + at) / 0.5 - round((start + at) / 0.5)) < 0.1, "on a beat"


def test_shots_follow_the_reference_moving_camera_share(media, tmp_path):
    # A slow pan (1.6 px per frame in a 640 px source) rounds to 0 px in the full frame at 160 px,
    # but a 9:16 crop magnifies it 2.4x: the output sees a moving camera.
    _ff("-f", "lavfi", "-i", "mandelbrot=s=1280x480,trim=duration=0.04", "-frames:v", "1", str(tmp_path / "big.png"))
    _ff("-loop", "1", "-i", str(tmp_path / "big.png"), "-vf", "crop=640:480:x='t*48':y=0,format=yuv420p",
        "-t", "8", "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", str(tmp_path / "pan.mp4"))
    _ff("-loop", "1", "-i", str(tmp_path / "big.png"), "-vf", "crop=640:480:x=300:y=0,format=yuv420p",
        "-t", "8", "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", str(tmp_path / "still.mp4"))
    full = analyze.analyze_video(str(tmp_path / "pan.mp4"), include_audio=False)["summary"]["moving_camera_share"]
    crop = analyze.output_camera_moving(str(tmp_path / "pan.mp4"), 540, 960)[0].mean()
    assert full < 0.5 < crop, (full, crop)
    srcs = [str(tmp_path / "pan.mp4"), str(tmp_path / "still.mp4")]
    base = {"cut_every": 2, "punch": 0, "flash": 0, "shake": 0, "glitch": 0, "grade": None, "transition": "cut"}
    # Without a target the two sources alternate (3 of 6); a target moves the majority its way.
    # (Variety rules - no source twice in a row, a cost per reuse - keep it from being 6 of 6.)
    for target, want in ((0.0, "still"), (1.0, "pan")):
        edl = autoedit.build_edl(srcs, str(media / "beat.wav"), str(tmp_path / "c.mp4"),
                                 {**base, "camera_moving": target}, duration=6, width=540, height=960)
        picked = [c["src"] for c in edl["clips"]]
        assert sum(want in p for p in picked) > len(picked) / 2, (target, picked)


def test_reference_colour_is_matched_per_shot(media, tmp_path):
    # A bright, low-contrast source and a dark, contrasty reference colour: each shot gets its own
    # measured grade that moves it toward the reference, inside the safe limits.
    _ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=6", "-vf", "eq=brightness=0.25:contrast=0.6,format=yuv420p",
        "-c:v", "libx264", "-preset", "ultrafast", str(tmp_path / "bright.mp4"))
    # source in the 9:16 crop: saturation 0.71, warmth 0.14, brightness 0.71, contrast 0.22
    target = {"saturation": 0.4, "warmth": 0.0, "brightness": 0.3, "contrast": 0.4}
    style = {"cut_every": 2, "punch": 0, "flash": 0, "shake": 0, "glitch": 0, "grade": "teal_orange",
             "transition": "cut", "color": target}
    out = tmp_path / "graded.mp4"
    edl = autoedit.build_edl([str(tmp_path / "bright.mp4")], str(media / "beat.wav"), str(out), style,
                             duration=4, width=360, height=640)
    assert all(isinstance(c.get("grade"), dict) for c in edl["clips"])
    g = edl["clips"][0]["grade"]
    assert -0.15 <= g["brightness"] < 0 and 1.0 < g["contrast"] <= 1.35 and 0.6 <= g["saturation"] < 1, g
    edl.pop("_meta")
    render.render(edl, tmp_path / "work")
    before = autoedit.color_profile(str(tmp_path / "bright.mp4"), size=(360, 640))
    after = autoedit.color_profile(str(out))
    for k in ("saturation", "brightness", "contrast"):
        assert abs(after[k] - target[k]) < abs(before[k] - target[k]), (k, before, after)
    with pytest.raises(ValueError):
        from blade_editor import effects
        effects.grade({"exposure": 1})


def test_probe_reads_persian_metadata_with_a_windows_locale(tmp_path, monkeypatch):
    # Windows: text=True decodes ffprobe's UTF-8 output with the locale code page. A Persian
    # title tag then failed (stdout None -> "the JSON object must be str ... not NoneType").
    out = tmp_path / "تست.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=160x90:r=10:d=1", "-metadata", "title=افزایش سرعت تدوین",
        "-metadata", "comment=پک خام", "-c:v", "libx264", "-preset", "ultrafast", str(out))
    real = subprocess.Popen.__init__

    def windows_default(self, *a, **k):  # what text=True does on a Windows machine with code page 1252
        if (k.get("text") or k.get("universal_newlines")) and not k.get("encoding"):
            k["encoding"] = "cp1252"
        real(self, *a, **k)

    monkeypatch.setattr(subprocess.Popen, "__init__", windows_default)
    info = ff.probe(out)
    assert info["video"]["width"] == 160 and info["duration"] > 0.5


def test_gpu_finds_cuda_dlls_from_pip_and_explains_a_missing_one(tmp_path, monkeypatch):
    # Windows: "cublas64_12.dll is not found" -> Blade went to the CPU and did not say how to fix it.
    # The CUDA 12 DLLs come from pip (nvidia-cublas-cu12, nvidia-cudnn-cu12) into
    # site-packages/nvidia/<name>/bin; Blade must put those folders on the DLL path.
    import sys
    import types
    from blade_editor import captions
    for name, sub, f in (("cublas", "bin", "cublas64_12.dll"), ("cudnn", "bin", "cudnn64_9.dll"),
                         ("cublas", "lib", "libcublas.so.12")):
        (tmp_path / "site" / "nvidia" / name / sub).mkdir(parents=True, exist_ok=True)
        (tmp_path / "site" / "nvidia" / name / sub / f).write_bytes(b"")
    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    monkeypatch.delitem(sys.modules, "nvidia", raising=False)
    win = captions._cuda_lib_dirs(windows=True)
    assert [Path(d).parts[-2:] for d in win] == [("cublas", "bin"), ("cudnn", "bin")]
    assert [Path(d).parts[-2:] for d in captions._cuda_lib_dirs(windows=False)] == [("cublas", "lib")]

    class M:
        def __init__(self, model, device, compute_type):
            self.device = device

        def transcribe(self, samples, **kw):
            if self.device != "cpu":
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
            return [], types.SimpleNamespace(language="fa", duration=1.0)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=M))
    monkeypatch.setattr(captions, "_load_cuda_libs", lambda: [])
    _ff("-f", "lavfi", "-i", "sine=f=300:d=1", str(tmp_path / "a.wav"))
    r = captions.transcribe(str(tmp_path / "a.wav"), language="fa", model="large-v3-turbo", device="auto")
    assert r["device"].startswith("cpu (GPU failed")
    assert "nvidia-cublas-cu12" in r["gpu_fix"] and "nvidia-cudnn-cu12" in r["gpu_fix"]
