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
            "1. One time: install the Blade Bridge extension in your normal Chrome. " + EXTENSION_HELP,
            "2. Be logged in to Google in that Chrome. Blade opens Google Flow in a tab by itself.",
            "3. The first time, open or create a project in that Flow tab.",
        ],
        "fallback": "Without the extension: turn on chrome://inspect/#remote-debugging (Chrome 144+) "
                    "and click Allow when Chrome asks.",
        "notes": [
            "Generation uses your own Flow credits and plan.",
            "Automating the Flow website may be against Google's terms; use it at your own risk.",
            "Blade Editor never solves CAPTCHAs and never approves credit dialogs for you.",
            "Turn remote debugging off again in chrome://inspect when you are done.",
        ],
    }


async def _connect(port: int = 0):  # Chrome DevTools route
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


def _index(items: list[dict]) -> dict[str, dict]:
    """Media elements keyed by Flow media id (or by URL when there is no id)."""
    found: dict[str, dict] = {}
    for it in items:
        for url in (it["src"], it["poster"]):
            m = MEDIA_RE.search(url)
            key = m.group(1) if m else (url if it["tag"] == "VIDEO" and url else None)
            if key:
                prev = found.get(key, {})
                found[key] = {"is_video": prev.get("is_video") or (it["tag"] == "VIDEO" and url == it["src"]),
                              "url": url if it["tag"] == "VIDEO" and url == it["src"] else prev.get("url")}
    return found


async def _media(page) -> dict[str, dict]:
    items: list[dict] = []
    for frame in page.frames:
        try:
            items += await frame.evaluate(SCAN_JS)
        except Exception:
            continue
    return _index(items)


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


class _CDP:
    """Chrome DevTools route (remote debugging on, or a Chrome started with a port)."""
    name = "chrome-remote-debugging"

    def __init__(self, pw, page):
        self.pw, self.page = pw, page

    @property
    def url(self) -> str:
        return self.page.url

    async def type(self, text: str) -> bool:
        box = await _first_visible(self.page, PROMPT_SELECTORS)
        if box is None:
            return False
        await box.click()
        await box.fill(text)
        return True

    async def submit(self) -> bool:
        btn = await _first_visible(self.page, SUBMIT_SELECTORS)
        if btn is None:
            return False
        await btn.click()
        return True

    async def media(self) -> dict:
        return await _media(self.page)

    async def dialog(self) -> bool:
        return await _first_visible(self.page, ['[role="dialog"]', '[role="alertdialog"]']) is not None

    async def download(self, key: str, info: dict, out: Path) -> bool:
        return await _download(self.page, key, info, out)

    async def shot(self) -> bytes:
        return await self.page.screenshot(type="jpeg", quality=60)

    async def wait(self, s: float) -> None:
        await self.page.wait_for_timeout(int(s * 1000))

    async def close(self) -> None:
        await self.pw.stop()


class _Ext:
    """Blade Bridge extension route: works in your own Chrome, no debugging switch, no prompts."""
    name = "blade-bridge-extension"

    def __init__(self, url: str):
        from .bridge import BRIDGE
        self.b, self.url = BRIDGE, url

    async def type(self, text: str) -> bool:
        return (await self.b.call("type_prompt", text=text))["typed"]

    async def submit(self) -> bool:
        return (await self.b.call("submit"))["clicked"]

    async def media(self) -> dict:
        return _index((await self.b.call("scan"))["items"])

    async def dialog(self) -> bool:
        return (await self.b.call("dialog"))["open"]

    async def download(self, key: str, info: dict, out: Path) -> bool:
        url = info.get("url") or ""
        if not url or MEDIA_RE.search(url):
            origin = re.match(r"https?://[^/]+", self.url).group(0)
            url = f"{origin}/fx/api/trpc/media.getMediaUrlRedirect?name={key}"
        r = await self.b.call("fetch_media", timeout=300, url=url)
        if not r.get("type", "").startswith("video/"):
            return False
        out.write_bytes(base64.b64decode(r["b64"]))
        return True

    async def shot(self) -> bytes | None:
        try:
            return base64.b64decode((await self.b.call("screenshot"))["b64"])
        except RuntimeError:
            return None  # e.g. the Chrome window is minimised

    async def wait(self, s: float) -> None:
        import asyncio
        await asyncio.sleep(s)

    async def close(self) -> None:
        pass


EXTENSION_HELP = ("Install the Blade Bridge extension once: in Chrome open chrome://extensions, turn on "
                  "Developer mode, click 'Load unpacked' and choose the folder "
                  f"{Path.home() / '.blade-editor' / 'chrome-extension'} (the installer puts it there). "
                  "Keep Chrome open; the extension connects by itself (click its icon to connect at once).")


async def _driver(port: int = 0, wait: float = 35):
    """Prefer the Blade Bridge extension; else Chrome remote debugging; else explain the setup."""
    from .bridge import BRIDGE
    if not port:
        quick = 3 if _own_chrome_endpoint() else wait
        if await BRIDGE.wait(quick):
            match = FLOW_URL.split("/flow")[0] + "/flow"
            r = await BRIDGE.call("ensure_tab", url=FLOW_URL, match=match)
            return _Ext(r["url"])
        if not _own_chrome_endpoint():
            raise RuntimeError("Blade Bridge is not connected. " + EXTENSION_HELP)
    pw, page = await _connect(port)
    return _CDP(pw, page)


async def status(port: int = 0) -> dict:
    d = await _driver(port)
    try:
        return {"connected": True, "via": d.name, "url": d.url, "_screenshot": await d.shot()}
    finally:
        await d.close()


async def generate_video(prompt: str, out_dir: str | Path, confirm: bool = False, port: int = 0,
                         direct: bool = True, timeout: float = 600, poll: float = 5) -> dict:
    """Type the prompt in Flow. With confirm=True also submit and download the new video(s)."""
    d = await _driver(port)
    try:
        text = ("Generate this video now, with no questions, exactly as described: " + prompt) if direct else prompt
        if not await d.type(text):
            raise RuntimeError("No prompt box found on the Flow page. Open or create a Flow project "
                               "in the Flow tab.")
        if not confirm:
            return {"status": "ready_for_confirmation", "credits_spent": False, "prompt": text, "via": d.name,
                    "message": "The prompt is typed in Flow. Call again with confirm=true to generate "
                               "(this spends your Flow credits).", "_screenshot": await d.shot()}
        before = set(await d.media())
        if not await d.submit():
            raise RuntimeError("No generate button found. The Flow page may have changed.")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        start, files, dialog_seen = time.time(), [], False
        while time.time() - start < timeout:
            await d.wait(poll)
            dialog_seen = dialog_seen or await d.dialog()
            new = {k: v for k, v in (await d.media()).items() if k not in before and v["is_video"]}
            for key, info in new.items():
                out = out_dir / f"flow_{re.sub(r'[^A-Za-z0-9]', '', key)[-12:]}_{int(start)}.mp4"
                if not out.exists() and await d.download(key, info, out):
                    files.append(str(out))
            if files:
                return {"status": "done", "credits_spent": True, "files": files, "via": d.name,
                        "seconds": round(time.time() - start)}
        return {"status": "timeout", "credits_spent": True, "files": [],
                "message": ("Flow is showing a dialog; approve it in the browser, then call "
                            "flow_collect." if dialog_seen else "No new video appeared in time; "
                            "call flow_collect later."), "_screenshot": await d.shot()}
    finally:
        await d.close()


async def collect(out_dir: str | Path, port: int = 0, limit: int = 4) -> dict:
    """Download the newest videos visible on the Flow page (after a timeout or for old results)."""
    d = await _driver(port)
    try:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        vids = [(k, v) for k, v in (await d.media()).items() if v["is_video"]][:limit]
        for key, info in vids:
            out = out_dir / f"flow_{re.sub(r'[^A-Za-z0-9]', '', key)[-12:]}.mp4"
            if out.exists() or await d.download(key, info, out):
                files.append(str(out))
        return {"files": files}
    finally:
        await d.close()
