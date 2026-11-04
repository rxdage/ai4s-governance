"""Reference Feishu/Lark adapter for the bot core.

This is deliberately a *thin* adapter: transport and payload shapes only. All
policy lives in ``ai4s_governance.bot``. If your team uses Slack, Teams, Matrix
or a local webhook, copy this file and keep the ``handle(sender, text)`` call.

Production notes
----------------
* Put credentials in environment variables, never in the repo.
* Feishu can encrypt event bodies with an Encrypt Key. This adapter handles
  plaintext callbacks and signature verification; if your tenant enforces
  encryption, add AES-CBC decryption before ``parse_event``.
* The HTTP server is single-process and for a small lab. Put it behind your
  normal reverse proxy / process supervisor.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..bot import BotCore

FEISHU_BASE = "https://open.feishu.cn"


class FeishuError(RuntimeError):
    pass


class FeishuAdapter:
    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        verification_token: Optional[str] = None,
        encrypt_key: Optional[str] = None,
        dry_run: bool = True,
    ):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
        self.verification_token = verification_token or os.environ.get(
            "FEISHU_VERIFICATION_TOKEN", ""
        )
        self.encrypt_key = encrypt_key or os.environ.get("FEISHU_ENCRYPT_KEY", "")
        self.dry_run = dry_run
        self._token: Optional[str] = None
        self._token_expiry = 0.0
        self._lock = threading.Lock()
        self._seen: set = set()

    # -- auth -------------------------------------------------------------
    def _tenant_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expiry - 60:
                return self._token
            if not self.app_id or not self.app_secret:
                raise FeishuError("FEISHU_APP_ID / FEISHU_APP_SECRET not set")
            req = urllib.request.Request(
                FEISHU_BASE + "/open-apis/auth/v3/tenant_access_token/internal",
                data=json.dumps(
                    {"app_id": self.app_id, "app_secret": self.app_secret}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("code") != 0:
                raise FeishuError(f"tenant_access_token failed: {data}")
            self._token = data["tenant_access_token"]
            self._token_expiry = time.time() + int(data.get("expire", 7200))
            return self._token

    # -- send -------------------------------------------------------------
    def send_text(self, chat_id: str, text: str) -> Dict[str, Any]:
        return self._send(chat_id, "text", {"text": text})

    def send_card(self, chat_id: str, card: Dict[str, Any]) -> Dict[str, Any]:
        return self._send(chat_id, "interactive", card)

    def _send(self, chat_id: str, msg_type: str, content: Dict[str, Any]) -> Dict[str, Any]:
        if self.dry_run:
            print(f"[feishu:dry-run] chat={chat_id} type={msg_type}\n{content}")
            return {"dry_run": True}
        token = self._tenant_token()
        body = {
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False),
        }
        req = urllib.request.Request(
            FEISHU_BASE + "/open-apis/im/v1/messages?receive_id_type=chat_id",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise FeishuError(f"send failed: HTTP {exc.code}") from exc
        if data.get("code") != 0:
            raise FeishuError(f"send failed: {data}")
        return data

    # -- receive ----------------------------------------------------------
    def verify_header(self, timestamp: str, nonce: str, body: bytes, signature: str) -> bool:
        if not self.encrypt_key:
            return True
        raw = (timestamp + nonce + self.encrypt_key).encode("utf-8") + body
        return hashlib.sha256(raw).hexdigest() == signature

    def parse_event(self, payload: Dict[str, Any]) -> Tuple[str, str, str]:
        """Return ``(sender_open_id, text, chat_id)``."""
        event = payload.get("event") or {}
        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        open_id = str(sender_id.get("open_id", ""))
        message = event.get("message") or {}
        chat_id = str(message.get("chat_id", ""))
        content = message.get("content") or "{}"
        try:
            text = str(json.loads(content).get("text", ""))
        except json.JSONDecodeError:
            text = ""
        return open_id, text.strip(), chat_id

    def handle_payload(self, payload: Dict[str, Any], core: BotCore) -> Optional[str]:
        if payload.get("type") == "url_verification":
            return "challenge"
        header = payload.get("header") or {}
        event_id = str(header.get("event_id", ""))
        if event_id:
            if event_id in self._seen:
                return None
            self._seen.add(event_id)
            if len(self._seen) > 5000:
                self._seen.clear()
        if header.get("event_type") != "im.message.receive_v1":
            return None
        sender, text, chat_id = self.parse_event(payload)
        if not sender or not text:
            return None
        reply = core.handle(sender, text)
        if reply.text:
            self.send_text(chat_id, reply.text)
        return reply.text

    # -- server -----------------------------------------------------------
    def serve(self, core: BotCore, host: str = "127.0.0.1", port: int = 8080) -> None:
        adapter = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                print(f"[feishu] {fmt % args}")

            def _json(self, code: int, data: Dict[str, Any]) -> None:
                raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._json(200, {"ok": True})
                else:
                    self._json(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/webhook":
                    self._json(404, {"error": "not found"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                ts = self.headers.get("X-Lark-Request-Timestamp", "")
                nonce = self.headers.get("X-Lark-Request-Nonce", "")
                sig = self.headers.get("X-Lark-Signature", "")
                if not adapter.verify_header(ts, nonce, body, sig):
                    self._json(401, {"error": "bad signature"})
                    return
                try:
                    payload = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError:
                    self._json(400, {"error": "bad json"})
                    return

                if payload.get("type") == "url_verification":
                    if adapter.verification_token and payload.get("token") != adapter.verification_token:
                        self._json(401, {"error": "bad token"})
                    else:
                        self._json(200, {"challenge": payload.get("challenge", "")})
                    return

                if adapter.verification_token:
                    token = (payload.get("header") or {}).get("token") or payload.get("token")
                    if token != adapter.verification_token:
                        self._json(401, {"error": "bad token"})
                        return

                try:
                    adapter.handle_payload(payload, core)
                except Exception as exc:  # noqa: BLE001 - keep the webhook alive
                    print(f"[feishu] handler error: {exc}")
                self._json(200, {"code": 0})

        server = ThreadingHTTPServer((host, port), Handler)
        print(f"[feishu] listening on http://{host}:{port}/webhook (dry_run={self.dry_run})")
        server.serve_forever()
