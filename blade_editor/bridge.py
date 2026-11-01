"""Local link to the Blade Bridge Chrome extension (ws://127.0.0.1:17321).

Only the Blade Bridge extension may connect: the browser sets the Origin header of an
extension to chrome-extension://<its id>, and web pages cannot fake it.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
from pathlib import Path

PORT = int(os.environ.get("BLADE_BRIDGE_PORT", "17321"))
EXTENSION_IDS = {Path(__file__).with_name("extension_id.txt").read_text().strip(),
                 *filter(None, os.environ.get("BLADE_EXTENSION_IDS", "").split(","))}


class Bridge:
    def __init__(self) -> None:
        self.loop = None
        self.ids = itertools.count(1)

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        if self.loop is loop:
            return
        # A new event loop (e.g. a new asyncio.run) needs its own server and state; free the port first.
        if getattr(self, "sock", None):
            self.sock.close()
        self.loop, self.ws, self.pending, self.connected = loop, None, {}, asyncio.Event()
        import socket

        import websockets

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", PORT))
        self.server = await websockets.serve(
            self._handler, sock=self.sock, max_size=None,
            origins=[f"chrome-extension://{i}" for i in EXTENSION_IDS])

    async def _handler(self, ws) -> None:
        self.ws = ws
        self.connected.set()
        try:
            async for raw in ws:
                msg = json.loads(raw)
                fut = self.pending.pop(msg.get("id"), None)
                if fut and not fut.done():
                    if msg.get("ok"):
                        fut.set_result(msg.get("result"))
                    else:
                        fut.set_exception(RuntimeError(f"Blade Bridge: {msg.get('error')}"))
        finally:
            if self.ws is ws:
                self.ws = None
                self.connected.clear()

    async def wait(self, timeout: float) -> bool:
        await self.start()
        if self.ws:
            return True
        try:
            await asyncio.wait_for(self.connected.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def call(self, cmd: str, timeout: float = 120, **args):
        if not getattr(self, "ws", None):
            raise RuntimeError("Blade Bridge is not connected.")
        i = next(self.ids)
        fut = asyncio.get_running_loop().create_future()
        self.pending[i] = fut
        await self.ws.send(json.dumps({"id": i, "cmd": cmd, "args": args}))
        return await asyncio.wait_for(fut, timeout)


BRIDGE = Bridge()
