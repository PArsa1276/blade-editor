"""Flow automation against a local mock page (needs Playwright and a Chromium binary)."""

import asyncio
import glob
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright")
CHROME = os.environ.get("BLADE_TEST_CHROME") or next(
    iter(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")), None)
pytestmark = pytest.mark.skipif(not CHROME, reason="no Chromium binary")


def _port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_flow_downloads_only_the_new_video(tmp_path, monkeypatch):
    """Uses the 'own Chrome' path: Chrome writes DevToolsActivePort; Blade Editor finds it."""
    from blade_editor import flow
    from blade_editor.bridge import BRIDGE
    monkeypatch.setattr(flow, "PENDING", tmp_path / "pending.json")

    for name, pat in (("old.mp4", "testsrc"), ("new.mp4", "smptebars")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{pat}=d=1",
                        str(tmp_path / name)], check=True)
    web = _port()
    prof = tmp_path / "prof"
    monkeypatch.setenv("BLADE_CHROME_DATA", str(prof))
    procs = [
        subprocess.Popen([sys.executable, "-I", str(Path(__file__).parent / "flow_mock_server.py"),
                          str(tmp_path), str(web)]),
        subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--remote-debugging-port=0",
                          f"--user-data-dir={prof}",
                          f"http://127.0.0.1:{web}/fx/tools/flow/project/x"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    ]
    try:
        for _ in range(60):
            if (prof / "DevToolsActivePort").exists():
                break
            time.sleep(0.25)
        time.sleep(1.5)
        dry = asyncio.run(flow.generate_video("a cat", tmp_path / "out", confirm=False))
        assert dry["status"] == "ready_for_confirmation" and not dry["credits_spent"]
        r = asyncio.run(flow.generate_video("a cat", tmp_path / "out", confirm=True,
                                            timeout=30, poll=1))
        assert r["status"] == "done" and len(r["files"]) == 1
        assert Path(r["files"][0]).read_bytes() == (tmp_path / "new.mp4").read_bytes()
    finally:
        for p in procs:
            p.kill()
        shutil.rmtree(tmp_path / "prof", ignore_errors=True)


def test_flow_through_blade_bridge_extension(tmp_path, monkeypatch):
    """The extension route: Chrome with Blade Bridge loaded, no remote debugging at all."""
    import json
    import shutil as sh
    ext = tmp_path / "ext"
    sh.copytree(Path(__file__).parent.parent / "extension", ext)
    m = json.loads((ext / "manifest.json").read_text())
    m["host_permissions"].append("http://127.0.0.1/*")  # the mock Flow page runs on localhost
    (ext / "manifest.json").write_text(json.dumps(m))
    for name, pat in (("old.mp4", "testsrc"), ("new.mp4", "smptebars")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{pat}=d=1",
                        str(tmp_path / name)], check=True)
    web = _port()
    monkeypatch.setenv("BLADE_CHROME_DATA", str(tmp_path / "none"))  # no DevTools route
    from blade_editor import flow
    from blade_editor.bridge import BRIDGE
    monkeypatch.setattr(flow, "PENDING", tmp_path / "pending.json")
    monkeypatch.setattr(flow, "FLOW_URL", f"http://127.0.0.1:{web}/fx/tools/flow/project/x")
    procs = [
        subprocess.Popen([sys.executable, "-I", str(Path(__file__).parent / "flow_mock_server.py"),
                          str(tmp_path), str(web)]),
        subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", f"--user-data-dir={tmp_path / 'prof'}",
                          f"--disable-extensions-except={ext}", f"--load-extension={ext}", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    ]
    try:
        async def run():
            home = f"http://127.0.0.1:{web}/fx/tools/flow/home"
            monkeypatch.setattr(flow, "FLOW_URL", home)
            monkeypatch.setattr(flow, "FLOW_MATCH", [home])
            st = await flow.status()
            assert st["project_open"] is False and "no project is open" in st["message"]
            project = home.replace("/home", "/project/x")
            monkeypatch.setattr(flow, "FLOW_URL", project)
            monkeypatch.setattr(flow, "FLOW_MATCH", [project])
            st = await flow.status()
            assert st["project_open"] is True and "message" not in st
            frames = {"first_frame": f"{tmp_path / 'old.mp4'}@0.5", "last_frame": f"{tmp_path / 'new.mp4'}@0.5"}
            dry = await flow.generate_video("a cat", tmp_path / "out", confirm=False, **frames)
            assert dry["via"] == "blade-bridge-extension" and not dry["credits_spent"]
            assert dry["attached_by"] == "file-input" and dry["frames_visible"] and len(dry["frames"]) == 2
            assert dry["prompt"].startswith("Generate this video now") and "FIRST FRAME" in dry["prompt"]
            # The mock needs 3 s: a 1 s wait returns "generating" and the clip is remembered.
            g = await flow.generate_video("a cat", tmp_path / "out", confirm=True, timeout=1, poll=1, **frames)
            imgs = sum(1 for it in (await BRIDGE.call("scan"))["items"] if it["tag"] == "IMG")
            assert imgs == 2  # the confirm call did not attach the frames a second time
            assert g["status"] == "generating" and (tmp_path / "pending.json").exists()
            with pytest.raises(RuntimeError, match="not collected yet"):  # no second spend
                await flow.generate_video("a cat", tmp_path / "out", confirm=True)
            r = await flow.collect(tmp_path / "out", wait=40, poll=1)
            assert not (tmp_path / "pending.json").exists()
            return r
        r = asyncio.run(run())
        assert r["status"] == "done" and len(r["files"]) == 1
        assert Path(r["files"][0]).read_bytes() == (tmp_path / "new.mp4").read_bytes()
    finally:
        for p in procs:
            p.kill()
        shutil.rmtree(tmp_path / "prof", ignore_errors=True)
