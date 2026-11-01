"""Google Flow (labs.google) video generation through YOUR OWN logged-in Chrome.

Flow has no public API, so this drives the web page over the Chrome DevTools Protocol.
Rewritten from the ideas in vynnlee/google-flow-mcp (MIT) with these fixes:
- no hard-coded UI language (the original typed an Italian prompt and clicked "Approva");
- never clicks a credit confirmation dialog: `confirm=true` submits, and any dialog Flow
  shows after that is left for you to approve in the browser;
- uses YOUR running Chrome (remote debugging allowed in chrome://inspect, Chrome asks you to
  Allow each connection); no profile copy, no second browser, no hidden automation flags;
- one port setting; only NEW videos (not in the page before the submit) are downloaded.
"""

from __future__ import annotations

import base64
import os
import re
import sys
import time
from pathlib import Path

FLOW_URL = os.environ.get("BLADE_FLOW_URL", "https://labs.google/fx/tools/flow")
MEDIA_RE = re.compile(r"media\.getMediaUrlRedirect\?name=([A-Za-z0-9_-]+)")
PROMPT_SELECTORS = ['[contenteditable="true"]', "textarea"]
SUBMIT_SELECTORS = [
    'button:has(:text-is("arrow_forward"))', 'button:has(:text-is("send"))',
    'button[aria-label*="generate" i]', 'button[aria-label*="create" i]',
    'button[aria-label*="send" i]', 'button[aria-label*="submit" i]',
]
SCAN_JS = """() => [...document.querySelectorAll('video, img')].map(el => ({
    tag: el.tagName, src: el.currentSrc || el.src || '', poster: el.getAttribute('poster') || '',
    w: el.width || el.clientWidth || 0 }))"""


def _chrome_data_dirs() -> list[Path]:
    if os.environ.get("BLADE_CHROME_DATA"):
        return [Path(os.environ["BLADE_CHROME_DATA"])]
    home = Path.home()
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [local / "Google" / "Chrome" / "User Data", local / "Microsoft" / "Edge" / "User Data"]
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support"
        return [base / "Google" / "Chrome", base / "Microsoft Edge"]
    return [home / ".config" / "google-chrome", home / ".config" / "chromium"]


def _own_chrome_endpoint() -> str | None:
    """WebSocket address of YOUR running Chrome after you allowed remote debugging in
    chrome://inspect/#remote-debugging (Chrome 144+). Chrome writes it to DevToolsActivePort."""
    for d in _chrome_data_dirs():
        f = d / "DevToolsActivePort"
        if f.exists():
            lines = f.read_text().split()
            if len(lines) >= 2:
                return f"ws://127.0.0.1:{lines[0]}{lines[1]}"
    return None


def setup_help(port: int = 0) -> dict:
    return {
        "steps": [
            "1. Use your normal Chrome (version 144 or newer), where you are logged in to Google.",
            "2. In Chrome open chrome://inspect/#remote-debugging and turn ON remote debugging.",
            "3. Open Google Flow (" + FLOW_URL + ") in a tab and open or create a project.",
            "4. When Blade Editor connects, Chrome asks for permission: click Allow.",
        ],
        "notes": [
            "Generation uses your own Flow credits and plan.",
            "Automating the Flow website may be against Google's terms; use it at your own risk.",
            "Blade Editor never solves CAPTCHAs and never approves credit dialogs for you.",
            "Turn remote debugging off again in chrome://inspect when you are done.",
        ],
    }


async def _connect(port: int = 0):
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError("Install the Flow extra: pip install 'blade-editor[flow]'") from e
    endpoint = f"http://127.0.0.1:{port}" if port else _own_chrome_endpoint()
    if not endpoint:
        raise RuntimeError("Your Chrome does not allow remote debugging yet. Open "
                           "chrome://inspect/#remote-debugging in Chrome, turn it on, and try again.")
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(endpoint)
    except Exception as e:
        await pw.stop()
        raise RuntimeError(f"Could not connect to Chrome ({endpoint}). Is Chrome open with remote "
                           f"debugging on, and did you click Allow? ({e})")
    pages = [p for c in browser.contexts for p in c.pages]
    page = next((p for p in pages if "/flow" in p.url), None)
    if page is None:
        # No Flow tab yet: open one in the user's own Chrome (logged in already).
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()
        await page.goto(FLOW_URL, wait_until="domcontentloaded", timeout=60000)
    return pw, page


async def _media(page) -> dict[str, dict]:
    """Media elements in all frames, keyed by Flow media id (or by URL when there is no id)."""
    found: dict[str, dict] = {}
    for frame in page.frames:
        try:
            items = await frame.evaluate(SCAN_JS)
        except Exception:
            continue
        for it in items:
            for url in (it["src"], it["poster"]):
                m = MEDIA_RE.search(url)
                key = m.group(1) if m else (url if it["tag"] == "VIDEO" and url else None)
                if key:
                    prev = found.get(key, {})
                    found[key] = {"is_video": prev.get("is_video") or (it["tag"] == "VIDEO" and url == it["src"]),
                                  "url": url if it["tag"] == "VIDEO" and url == it["src"] else prev.get("url")}
    return found


async def _first_visible(page, selectors: list[str]):
    for frame in page.frames:
        for sel in selectors:
            loc = frame.locator(sel).first
            try:
                if await loc.is_visible():
                    return loc
            except Exception:
                continue
    return None


async def _download(page, key: str, info: dict, out: Path) -> bool:
    url = info.get("url") or ""
    if url.startswith("blob:"):
        b64 = await page.evaluate("""async (u) => { const b = await (await fetch(u)).blob();
            const r = new FileReader(); return await new Promise(ok => { r.onload = () => ok(r.result);
            r.readAsDataURL(b); }); }""", url)
        out.write_bytes(base64.b64decode(b64.split(",", 1)[1]))
        return True
    if not url or MEDIA_RE.search(url):
        origin = re.match(r"https?://[^/]+", page.url).group(0)
        url = f"{origin}/fx/api/trpc/media.getMediaUrlRedirect?name={key}"
    resp = await page.request.get(url, timeout=120000)
    if resp.ok and resp.headers.get("content-type", "").startswith("video/"):
        out.write_bytes(await resp.body())
        return True
    return False


async def status(port: int = 0) -> dict:
    pw, page = await _connect(port)
    try:
        shot = await page.screenshot(type="jpeg", quality=60)
        return {"connected": True, "url": page.url, "title": await page.title(), "_screenshot": shot}
    finally:
        await pw.stop()


async def generate_video(prompt: str, out_dir: str | Path, confirm: bool = False, port: int = 0,
                         direct: bool = True, timeout: float = 600, poll: float = 5) -> dict:
    """Type the prompt in Flow. With confirm=True also submit and download the new video(s)."""
    pw, page = await _connect(port)
    try:
        box = await _first_visible(page, PROMPT_SELECTORS)
        if box is None:
            raise RuntimeError("No prompt box found on the Flow page. Open a Flow project.")
        text = ("Generate this video now, with no questions, exactly as described: " + prompt) if direct else prompt
        await box.click()
        await box.fill(text)
        if not confirm:
            return {"status": "ready_for_confirmation", "credits_spent": False, "prompt": text,
                    "message": "The prompt is typed in Flow. Call again with confirm=true to generate "
                               "(this spends your Flow credits).",
                    "_screenshot": await page.screenshot(type="jpeg", quality=60)}
        before = set(await _media(page))
        submit = await _first_visible(page, SUBMIT_SELECTORS)
        if submit is None:
            raise RuntimeError("No generate button found. The Flow page may have changed.")
        await submit.click()
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        start, files, dialog_seen = time.time(), [], False
        while time.time() - start < timeout:
            await page.wait_for_timeout(int(poll * 1000))
            dialog = await _first_visible(page, ['[role="dialog"]', '[role="alertdialog"]'])
            dialog_seen = dialog_seen or dialog is not None
            new = {k: v for k, v in (await _media(page)).items() if k not in before and v["is_video"]}
            for key, info in new.items():
                out = out_dir / f"flow_{re.sub(r'[^A-Za-z0-9]', '', key)[-12:]}_{int(start)}.mp4"
                if not out.exists() and await _download(page, key, info, out):
                    files.append(str(out))
            if files:
                return {"status": "done", "credits_spent": True, "files": files,
                        "seconds": round(time.time() - start)}
        return {"status": "timeout", "credits_spent": True, "files": [],
                "message": ("Flow is showing a dialog; approve it in the browser, then call "
                            "flow_collect." if dialog_seen else "No new video appeared in time; "
                            "call flow_collect later."),
                "_screenshot": await page.screenshot(type="jpeg", quality=60)}
    finally:
        await pw.stop()


async def collect(out_dir: str | Path, port: int = 0, limit: int = 4) -> dict:
    """Download the newest videos visible on the Flow page (after a timeout or for old results)."""
    pw, page = await _connect(port)
    try:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        vids = [(k, v) for k, v in (await _media(page)).items() if v["is_video"]][:limit]
        for key, info in vids:
            out = out_dir / f"flow_{re.sub(r'[^A-Za-z0-9]', '', key)[-12:]}.mp4"
            if out.exists() or await _download(page, key, info, out):
                files.append(str(out))
        return {"files": files}
    finally:
        await pw.stop()
