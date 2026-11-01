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
