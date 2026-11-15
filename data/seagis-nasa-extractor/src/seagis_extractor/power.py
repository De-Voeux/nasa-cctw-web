"""NASA LaRC POWER daily weather at one point per zone (no account needed).

Point: the zone polygon's representative point (shapely), which always lies inside the zone, so
at sea. POWER answers for the grid cell holding that point (meteorology ~0.5 x 0.625 deg MERRA-2,
solar ~1 deg CERES), so values describe the wider area around the zone, not the zone alone.

One request per zone for the whole period. Rows: dataset `nasa_power`, one per parameter and day,
`area_weighted` false, `roi_pixel_count` 1. Fill values (-999, recent days not yet processed) are
kept as rows with an empty mean and valid_pixel_count 0.

WD10M is the meteorological wind direction: degrees clockwise from north the wind blows FROM.
(Copernicus current_direction is the opposite convention: where the water flows TO.)
"""
from __future__ import annotations

import datetime as dt
import time
import urllib.parse

from .fetch import TRANSIENT_ERRORS, TRANSIENT_HTTP, FetchError, FetchGuardError, _backoff, json_transport
from .http import redact

KEY = "power"
DATASET = "nasa_power"
HOST = "power.larc.nasa.gov"
PARAMS_META = f"https://{HOST}/api/system/manager/parameters"
POINT_TOL_DEG = 1e-3


def point_for(geom) -> tuple[float, float]:
    """(lat, lon) inside the zone polygon, rounded to 1e-4 deg."""
    p = geom.representative_point()
    return round(p.y, 4), round(p.x, 4)


# ---------------------------------------------------------------- plan

def check_parameters(client, community: str, parameters: list[str]) -> dict:
    """Each parameter must exist as DAILY for the community (POWER metadata endpoint)."""
    out = {}
    for p in parameters:
        _, d = client.get_json(f"{PARAMS_META}/{p}", {"community": community, "temporal": "daily"})
        daily = ((d.get(p) or {}).get("temporal") or {}).get("DAILY")
        if not daily or community not in (daily.get("communities") or []):
            raise ValueError(f"POWER parameter {p} is not available as DAILY for community {community}")
        out[p] = {"name": daily.get("name"), "definition": daily.get("definition")}
    return out


def plan_section(client, spec: dict, period: dict, rois: list[dict], roi_geoms: dict, meta: dict | None = None) -> dict:
    """`meta` (parameter metadata) may be passed in by tests; otherwise POWER's metadata endpoint is read."""
    if urllib.parse.urlsplit(spec["endpoint"]).hostname != HOST:
        raise ValueError(f"POWER endpoint must be on {HOST}")
    params = list(spec["parameters"])
    meta = meta if meta is not None else check_parameters(client, spec["community"], params)
    start, end = dt.date.fromisoformat(period["start"]), dt.date.fromisoformat(period["end"])
    days = (end - start).days + 1
    rows = []
    for roi in rois:
        key = (roi["region_id"], roi["subregion_id"])
        geom = roi_geoms[key]
        lat, lon = point_for(geom)
        import shapely
        if not geom.covers(shapely.Point(lon, lat)):
            raise ValueError(f"POWER point {lat},{lon} is not inside zone {key}")
        rows.append({"region_id": key[0], "subregion_id": key[1], "geometry_version": roi["geometry_version"],
                     "lat": lat, "lon": lon, "url": point_url(spec, lat, lon, start, end)})
    return {"key": KEY, "dataset": DATASET, "period": period, "endpoint": spec["endpoint"],
            "community": spec["community"], "parameters": params, "parameter_metadata": meta,
            "access": "POWER daily point API, JSON, no account", "requests": len(rows),
            "rois": rows, "final_rows": len(rows) * len(params) * days,
            "point_rule": "zone polygon representative point (inside the zone)",
            "unknowns": ["POWER publishes recent days with a lag; those days come back as fill and are stored empty.",
                         "POWER cells (0.5-1 deg) are much larger than the zones."]}


def point_url(spec: dict, lat: float, lon: float, start: dt.date, end: dt.date) -> str:
    q = {"parameters": ",".join(spec["parameters"]), "community": spec["community"],
         "longitude": f"{lon:.4f}", "latitude": f"{lat:.4f}",
         "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"), "format": "JSON"}
    return f"{spec['endpoint']}?{urllib.parse.urlencode(q)}"


# ---------------------------------------------------------------- fetch

class PowerClient:
    """GET of plan-listed URLs only; retried on resets, timeouts, 429 and 5xx. No credentials sent."""

    def __init__(self, allowed_urls: set[str], transport=json_transport, sleep=time.sleep, retries: int = 6,
                 timeout: float = 120.0):
        self.allowed, self.transport, self.sleep = allowed_urls, transport, sleep
        self.retries, self.timeout, self.bytes = retries, timeout, 0

    def get(self, url: str) -> dict:
        if url not in self.allowed or urllib.parse.urlsplit(url).hostname != HOST:
            raise FetchGuardError(f"POWER request {redact(url)} is not in the approved plan")
        for attempt in range(1, self.retries + 1):
            try:
                r = self.transport("GET", url, {"Accept": "application/json"}, self.timeout)
            except TRANSIENT_ERRORS as e:
                if attempt == self.retries:
                    raise FetchError(f"GET {redact(url)} failed {attempt}x: {type(e).__name__}: {e}") from e
                self.sleep(_backoff(attempt))
                continue
            if r.status in TRANSIENT_HTTP and attempt < self.retries:
                self.sleep(_backoff(attempt, r.header("Retry-After")))
                continue
            if r.status != 200:
                raise FetchError(f"GET {redact(url)} -> HTTP {r.status}: {r.body[:300]!r}")
            self.bytes += len(r.body)
            return r.json()
        raise AssertionError("unreachable")


def guard(resp: dict, row: dict, params: list[str], dates: list[dt.date]) -> None:
    """The answer must be for the requested point, parameters and days."""
    coords = ((resp.get("geometry") or {}).get("coordinates") or [])[:2]
    if len(coords) != 2 or abs(coords[0] - row["lon"]) > POINT_TOL_DEG or abs(coords[1] - row["lat"]) > POINT_TOL_DEG:
        raise FetchGuardError(f"POWER answered for point {coords}, requested lon {row['lon']} lat {row['lat']}")
    got = (resp.get("properties") or {}).get("parameter") or {}
    if set(got) != set(params):
        raise FetchGuardError(f"POWER parameters {sorted(got)} != requested {sorted(params)}")
    want = {d.strftime("%Y%m%d") for d in dates}
    for p, series in got.items():
        if set(series) != want:
            raise FetchGuardError(f"POWER {p}: {len(set(series) & want)}/{len(want)} requested days, "
                                  f"{len(set(series) - want)} unrequested")


def rows_from(resp: dict, roi: dict, row: dict, params: list[str]) -> list[dict]:
    from .process import _row

    hdr = resp.get("header") or {}
    fill = float(hdr.get("fill_value", -999.0))
    units = {p: ((resp.get("parameters") or {}).get(p) or {}).get("units") or "" for p in params}
    version = "POWER " + str((hdr.get("api") or {}).get("version") or "").strip()
    src = f"POWER daily point {row['lat']},{row['lon']}"
    qc = f"point={row['lat']},{row['lon']};sources={','.join(hdr.get('sources') or [])}"
    out = []
    for p in params:
        if not units[p]:
            raise FetchError(f"POWER returned no units for {p}")
        for day, v in sorted(resp["properties"]["parameter"][p].items()):
            ok = v is not None and float(v) != fill
            val = round(float(v), 6) if ok else None
            st = {"valid_pixel_count": int(ok), "mean": val, "min": val, "max": val, "std": None}
            r = _row(dt.datetime.strptime(day, "%Y%m%d").date(), roi, DATASET, p, units[p], st, 1, src,
                     version.strip(), qc + ("" if ok else ";fill"))
            r["area_weighted"] = False
            out.append(r)
    return out
