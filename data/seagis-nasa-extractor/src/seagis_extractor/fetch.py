"""Science-data access. Only called by `pilot` (and later `fetch`) after the plan-hash gate.

MUR SST via NASA Harmony (HOSS bbox + temporal + variable subset, NetCDF-4):
- the request box must be one of the plan's `mur_requests` (checked by the caller and here);
- the Earthdata token is sent only to Harmony / Earthdata hosts, never to a redirect target
  elsewhere (signed S3 links reject it, and it must not leak);
- every byte downloaded counts against a hard ByteBudget; exceeding it aborts the run;
- files land as `.part` and are renamed only when complete.

Copernicus Marine via the official toolbox (`copernicusmarine.open_dataset`, ARCO geo-series),
bbox + time + surface depth only.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .http import USER_AGENT, Response, redact

HARMONY = "https://harmony.earthdata.nasa.gov"
AUTH_HOSTS = {"harmony.earthdata.nasa.gov", "urs.earthdata.nasa.gov"}
DONE = {"successful", "complete_with_errors"}
FAILED = {"failed", "canceled"}


class FetchError(RuntimeError):
    pass


class FetchGuardError(FetchError):
    """A request or response is not tied to the approved plan. Never retried."""


@dataclass
class ByteBudget:
    limit: int
    used: int = 0

    def add(self, n: int) -> None:
        self.used += n
        if self.used > self.limit:
            raise FetchGuardError(f"download budget exceeded: {self.used} > {self.limit} bytes")


# ---------------------------------------------------------------- transports (injectable for tests)

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def json_transport(method: str, url: str, headers: dict, timeout: float) -> Response:
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with _opener.open(req, timeout=timeout) as r:
            return Response(r.status, dict(r.headers.items()), r.read())
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b""
        return Response(e.code, dict(e.headers.items()) if e.headers else {}, body)


def stream_transport(url: str, headers: dict, timeout: float, sink: Callable[[bytes], None]) -> Response:
    """GET without following redirects; body chunks go to `sink` (which enforces the budget)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with _opener.open(req, timeout=timeout) as r:
            while chunk := r.read(1 << 16):
                sink(chunk)
            return Response(r.status, dict(r.headers.items()))
    except urllib.error.HTTPError as e:
        return Response(e.code, dict(e.headers.items()) if e.headers else {}, e.read() if e.fp else b"")


def _auth_for(url: str, token: str) -> dict:
    return {"Authorization": f"Bearer {token}"} if urllib.parse.urlsplit(url).hostname in AUTH_HOSTS else {}


# ---------------------------------------------------------------- Harmony

def harmony_url(collection_id: str, variables: list[str], bbox: list[float], start: dt.date, end: dt.date) -> str:
    """MUR granules span 21:00 UTC (day-1) .. 21:00 UTC (day); [start 00:00, end 20:59:59] selects
    exactly the granules dated start..end."""
    w, s, e, n = bbox
    # Harmony wants one `variable=` per variable with `parameter_vars` (a comma list is rejected: HTTP 400,
    # "Coverages were not found for the provided variables", seen live in the 2026-11-15 pilot).
    q = [("variable", v) for v in variables] + [
         ("subset", f"lat({s}:{n})"), ("subset", f"lon({w}:{e})"),
         ("subset", f'time("{start.isoformat()}T00:00:00Z":"{end.isoformat()}T20:59:59Z")'),
         ("format", "application/x-netcdf4"), ("forceAsync", "true")]
    return (f"{HARMONY}/{collection_id}/ogc-api-coverages/1.0.0/collections/parameter_vars/coverage/rangeset?"
            + urllib.parse.urlencode(q, quote_via=urllib.parse.quote))


@dataclass
class HarmonyClient:
    token: str
    allowed_boxes: set[tuple]
    budget: ByteBudget
    transport: Callable = json_transport
    stream: Callable = stream_transport
    sleep: Callable = time.sleep
    poll_seconds: float = 5.0
    max_polls: int = 360
    timeout: float = 120.0
    calls: int = field(default=0)

    def _json(self, url: str) -> dict:
        self.calls += 1
        r = self.transport("GET", url, _auth_for(url, self.token), self.timeout)
        if r.status in (401, 403):
            raise FetchError(f"Harmony refused credentials (HTTP {r.status}) for {redact(url)}")
        if r.status != 200:
            raise FetchError(f"GET {redact(url)} -> HTTP {r.status}: {r.body[:300]!r}")
        return r.json()

    def submit(self, collection_id: str, variables: list[str], bbox: list[float], start: dt.date, end: dt.date) -> str:
        if tuple(bbox) not in self.allowed_boxes:
            raise FetchGuardError(f"request box {bbox} is not in the approved plan")
        job = self._json(harmony_url(collection_id, variables, bbox, start, end))
        if "jobID" not in job:
            raise FetchError(f"Harmony did not return a job: keys {sorted(job)}")
        return job["jobID"]

    def wait(self, job_id: str) -> dict:
        url = f"{HARMONY}/jobs/{urllib.parse.quote(job_id)}"
        for _ in range(self.max_polls):
            job = self._json(url)
            status = job.get("status")
            if status in DONE:
                return job
            if status in FAILED:
                raise FetchError(f"Harmony job {job_id} {status}: {job.get('message', '')[:300]}")
            self.sleep(self.poll_seconds)
        raise FetchError(f"Harmony job {job_id} did not finish after {self.max_polls} polls")

    def data_links(self, job: dict) -> list[dict]:
        links, page = [], job
        while True:
            links += [l for l in page.get("links", []) if l.get("rel") == "data"]
            nxt = next((l["href"] for l in page.get("links", []) if l.get("rel") == "next"), None)
            if not nxt:
                return links
            page = self._json(nxt)

    def download(self, url: str, dest: Path, max_hops: int = 5) -> dict:
        """Follow redirects by hand so the token is only ever sent to Earthdata hosts."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        h = hashlib.sha256()
        for _ in range(max_hops + 1):
            self.calls += 1
            written = 0
            try:
                with part.open("wb") as f:
                    def sink(chunk: bytes):
                        nonlocal written
                        self.budget.add(len(chunk))
                        written += len(chunk)
                        h.update(chunk)
                        f.write(chunk)
                    r = self.stream(url, _auth_for(url, self.token), self.timeout, sink)
            except BaseException:
                part.unlink(missing_ok=True)
                raise
            if r.status in (301, 302, 303, 307, 308):
                loc = r.header("Location")
                if not loc:
                    raise FetchError(f"redirect without Location from {redact(url)}")
                url = urllib.parse.urljoin(url, loc)
                h = hashlib.sha256()
                continue
            if r.status != 200:
                part.unlink(missing_ok=True)
                raise FetchError(f"download {redact(url)} -> HTTP {r.status}")
            part.replace(dest)
            return {"path": str(dest), "bytes": written, "sha256": h.hexdigest()}
        part.unlink(missing_ok=True)
        raise FetchError(f"too many redirects for {redact(url)}")


# ---------------------------------------------------------------- Copernicus Marine

def copernicus_open(spec: dict, bbox: list[float], start: dt.date, end: dt.date, opener: Callable | None = None):
    """Lazy dataset for one ROI box, surface level only. Data are read when the caller loads it."""
    if opener is None:
        import copernicusmarine
        opener = copernicusmarine.open_dataset
    w, s, e, n = bbox
    return opener(dataset_id=spec["dataset_id"], variables=list(spec["variables"]),
                  minimum_longitude=w, maximum_longitude=e, minimum_latitude=s, maximum_latitude=n,
                  minimum_depth=0.0, maximum_depth=1.0,   # selects only the 0.494 m surface level
                  start_datetime=f"{start.isoformat()}T00:00:00", end_datetime=f"{end.isoformat()}T00:00:00",
                  coordinates_selection_method="outside", service="arco-geo-series")
