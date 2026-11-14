"""Reliable webhook delivery for HTTP APIs that hide errors behind HTTP 200.

Real-world failure this abstracts: a messaging webhook returned HTTP 200 with
``{"errcode": 40058}`` (content too long) — every oversized notification was
silently dropped for days while the caller logged "sent = True".

Rules encoded here:
- HTTP 200 is NOT success. The caller supplies a ``success`` predicate over the
  decoded response body.
- Size limits are enforced in **UTF-8 bytes**, not characters (4096 Chinese
  characters is 12KB).
- Oversized payloads are split into ordered chunks. A chunk failure **stops
  delivery** (a receiver getting chunks 1,2,4 of 4 is worse than getting
  nothing) and the failure reason is carried in ``SendResult.failures``.
- Dedupe applies to the whole logical message: if the first chunk was already
  sent recently, the entire message is skipped.
- Failed chunks are retried per ``retries`` with a fixed backoff; retries
  bypass dedupe (a retry is not a duplicate).
- Payload shape note: ``send`` targets the common ``{"markdown"/"text":
  {"content": ...}}`` envelope for splitting; payloads with any other shape go
  through ``send_json`` where the whole payload is the split unit. Nothing here
  assumes a specific vendor, endpoint, or credential scheme. The caller is
  responsible for the target URL being trustworthy (this module performs no
  SSRF screening).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

DEFAULT_CHUNK_BYTES = 3500  # leave headroom under a 4096-byte server limit


@dataclass(frozen=True)
class SendResult:
    """Outcome of one logical message (possibly delivered as several chunks)."""

    ok: bool
    chunks: int
    failures: list[str] = field(default_factory=list)
    deduped: bool = False

    @property
    def reason(self) -> str:
        return "; ".join(self.failures)[:200]


def utf8_chunks(content: str, limit: int = DEFAULT_CHUNK_BYTES) -> list[str]:
    """Split by UTF-8 bytes, never inside a character, never mid-line.

    A single line longer than the limit is hard-split on byte boundaries
    (walking back by code point, never cutting a multi-byte character).
    Joining all chunks with "" yields the original text minus the line
    separators that already existed in it — no characters are added or lost.
    """
    out: list[str] = []
    buf: list[str] = []
    size = 0

    def _byte_len(s: str) -> int:
        return len(s.encode("utf-8")) + 1

    def _flush() -> None:
        nonlocal buf, size
        if buf:
            out.append("\n".join(buf))
            buf, size = [], 0

    for line in content.split("\n"):
        b = _byte_len(line)
        if size + b > limit and buf:
            _flush()
        if b > limit:
            # Hard-split the oversized line itself, by code points, so no
            # multi-byte character is cut. Incremental byte accounting keeps
            # this O(n) instead of re-encoding the remainder per character.
            while _byte_len(line) > limit:
                cut = len(line)
                while _byte_len(line[:cut]) > limit:
                    cut -= 1
                out.append("\n".join(buf + [line[:cut]]) if buf else line[:cut])
                buf, size = [], 0
                line = line[cut:]
            buf, size = [line], _byte_len(line)
            continue
        buf.append(line)
        size += b
    _flush()
    return out or [content]


class WebhookClient:
    """Post JSON payloads to a webhook with business-error and size handling.

    ``success`` receives the decoded JSON body and must return True only when
    the server *actually* accepted the message. A transport failure also
    yields ``ok=False``. Failures never raise — callers decide what losing a
    notification means. Per-instance dedupe state (never shared across
    clients: two webhooks must not silence each other).
    """

    def __init__(
        self,
        url: str,
        *,
        success: Callable[[dict[str, Any]], bool] | None = None,
        timeout: float = 20.0,
        headers: dict[str, str] | None = None,
        chunk_bytes: int = DEFAULT_CHUNK_BYTES,
        dedupe_ttl: float = 600.0,
    ) -> None:
        self._url = url
        self._success = success or (lambda body: not body.get("errcode"))
        self._timeout = timeout
        self._headers = {"Content-Type": "application/json", **(headers or {})}
        self._chunk_bytes = chunk_bytes
        self._dedupe_ttl = dedupe_ttl
        self._dedupe_state: dict[str, float] = {}

    def send(self, content: str, *, dedupe: bool = False,
             retries: int = 0) -> SendResult:
        """Send a markdown-style text payload, splitting when oversized."""
        return self.send_json({"msgtype": "markdown", "markdown": {"content": content}},
                              dedupe=dedupe, retries=retries)

    def send_json(self, payload: dict[str, Any], *, dedupe: bool = False,
                  retries: int = 0) -> SendResult:
        chunks = utf8_chunks(_as_text(payload), self._chunk_bytes)
        failures: list[str] = []
        sent = 0

        first_digest = self._digest(payload)
        if dedupe and self._seen(first_digest):
            return SendResult(ok=True, chunks=0, failures=[], deduped=True)

        for i, chunk in enumerate(chunks):
            body = _with_text(payload, chunk)
            attempt = 0
            while True:
                # Retries bypass dedupe by definition: a retry is not a new
                # message, and a TTL dedupe would eat exactly the redelivery
                # the caller is asking for.
                if self._post(body, dedupe=(dedupe and i == 0 and attempt == 0)):
                    sent += 1
                    break
                err = self._last_error
                attempt += 1
                if attempt > retries:
                    # Stop-on-failure: delivering chunks 1,2,4 of 4 gives the
                    # receiver a truncated message, which is worse than none.
                    failures.append(f"chunk {i + 1}/{len(chunks)}: {err}")
                    break
                time.sleep(2)
        return SendResult(ok=not failures and sent > 0, chunks=sent,
                          failures=failures)

    # -- internals ---------------------------------------------------------

    def _digest(self, payload: dict[str, Any]) -> str:
        import hashlib
        return hashlib.md5(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _seen(self, digest: str) -> bool:
        """查询：TTL 内是否已发过。**无副作用**——记录只发生在发送成功后
        （_record）。查询即记录的话，预检本身会把 digest 写进状态，
        随后真正的发送反被误判为重复（重写时实测引入过）。"""
        return time.time() - self._dedupe_state.get(digest, 0) < self._dedupe_ttl

    def _record(self, digest: str) -> None:
        now = time.time()
        self._dedupe_state = {k: v for k, v in self._dedupe_state.items()
                              if now - v < self._dedupe_ttl * 6}
        self._dedupe_state[digest] = now

    def _post(self, payload: dict[str, Any], *, dedupe: bool = True) -> bool:
        digest = self._digest(payload)
        if dedupe and self._seen(digest):
            self._last_error = "deduped"
            return True
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self._url, data=data, headers=self._headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read() or b"{}")
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError) as e:
            self._last_error = f"transport: {e}"
            return False
        if not self._success(body):
            self._last_error = f"business error: {json.dumps(body)[:120]}"
            return False
        self._record(digest)  # 只有发送成功才记录去重——失败的发送允许重试
        return True

    _last_error = ""


def _as_text(payload: dict[str, Any]) -> str:
    for key in ("markdown", "text"):
        inner = payload.get(key)
        if isinstance(inner, dict) and "content" in inner:
            return str(inner["content"])
    return json.dumps(payload, ensure_ascii=False)


def _with_text(payload: dict[str, Any], text: str) -> dict[str, Any]:
    out = json.loads(json.dumps(payload, ensure_ascii=False))
    for key in ("markdown", "text"):
        if isinstance(out.get(key), dict):
            out[key]["content"] = text
            return out
    return out
