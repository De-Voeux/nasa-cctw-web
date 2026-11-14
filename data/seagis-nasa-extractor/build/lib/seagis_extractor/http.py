"""Minimal metadata HTTP client with an injectable transport (so tests never hit the network).

Only GET of metadata documents and HEAD without following redirects are supported here;
science downloads live in fetch.py behind the approval gate.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Protocol

USER_AGENT = "seagis-nasa-extractor/0.0 (metadata-only)"


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes = b""

    def header(self, name: str) -> str | None:
        name = name.lower()
        for k, v in self.headers.items():
            if k.lower() == name:
                return v
        return None

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class Transport(Protocol):
    def __call__(self, method: str, url: str, timeout: float, headers: dict) -> Response: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401 - never follow; caller inspects Location
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def urllib_transport(method: str, url: str, timeout: float, headers: dict) -> Response:
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with _opener.open(req, timeout=timeout) as r:
            body = r.read() if method == "GET" else b""
            return Response(r.status, dict(r.headers.items()), body)
    except urllib.error.HTTPError as e:  # includes 3xx because redirects are disabled
        return Response(e.code, dict(e.headers.items()) if e.headers else {}, b"")


class TransientError(RuntimeError):
    pass


@dataclass
class MetadataClient:
    transport: Callable[[str, str, float, dict], Response] = urllib_transport
    timeout: float = 30.0
    retries: int = 4
    backoff: float = 1.0
    sleep: Callable[[float], None] = time.sleep
    calls: int = field(default=0, init=False)

    def request(self, method: str, url: str, headers: dict | None = None) -> Response:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            self.calls += 1
            try:
                resp = self.transport(method, url, self.timeout, headers or {})
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = TransientError(f"{type(e).__name__}: {e}")
            else:
                if resp.status in (429, 500, 502, 503, 504):
                    last = TransientError(f"HTTP {resp.status}")
                else:
                    return resp
            if attempt < self.retries:
                self.sleep(self.backoff * 2**attempt)
        raise last  # type: ignore[misc]

    def get_json(self, url: str, params: dict | list | None = None, headers: dict | None = None):
        if params:
            url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
        resp = self.request("GET", url, headers)
        if resp.status != 200:
            raise RuntimeError(f"GET {redact(url)} -> HTTP {resp.status}")
        return resp, resp.json()


def redact(url: str) -> str:
    """Drop query strings (signed URLs, tokens) before anything is logged or cached."""
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, "", ""))
