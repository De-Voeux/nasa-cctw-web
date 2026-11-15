"""GPM IMERG Late Run daily precipitation (GES DISC, GPM_3IMERGDL V07) via NASA Harmony.

Same pattern as MUR: one Harmony job per ROI request box x month, bbox + temporal + variable
subset, every file guarded against the approved grid cells, aggregated over the ROI membership
cells (weighted by overlap x cell area), raw files discarded.

Grid: 0.1 deg, cell centres lat = -89.95 + 0.1*i (i < 1800), lon = -179.95 + 0.1*j (j < 3600).
Variables are stored (time, lon, lat); they are transposed to (lat, lon) on read.
IMERG covers land and sea, so no land mask is applied. A 0.1 deg cell (~11 km) is larger than a
5 km coastal zone: values describe the cells around the zone, not the zone alone.

Plan inputs are metadata only: the CMR granule list (which days exist) and local geometry.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np

from . import catalog, estimate
from .validate import check

KEY = "gpm_imerg"
UNITS_OK = {"mm/day", "mm day-1", "mm d-1", "mm/d"}
MAX_MM_DAY = 3000.0          # well above any recorded daily rainfall
OVERHEAD_BYTES = 30_000      # NetCDF-4 header + coordinates per subset file


class ImergGrid(estimate.MurGrid):
    lat0, lon0, step, nlat, nlon = -89.95, -179.95, 0.1, 1800, 3600


def membership_path(membership_dir: Path, roi: dict) -> Path:
    return membership_dir / f"{KEY}__{roi['region_id']}__{roi['subregion_id']}__{roi['geometry_version']}.csv.gz"


# ---------------------------------------------------------------- plan

def plan_section(client, spec: dict, period: dict, rois: list[dict], roi_geoms: dict, membership_dir: Path,
                 max_cells: int, granules: list[dict] | None = None) -> dict:
    """`granules` (CMR records) may be passed in by tests; otherwise CMR is searched (metadata only)."""
    grid = ImergGrid()
    start, end = dt.date.fromisoformat(period["start"]), dt.date.fromisoformat(period["end"])
    if granules is None:
        granules = catalog.list_granules(client, spec["short_name"], spec["granule_pattern"], start, end,
                                         concept_id=spec["concept_id"])
    kept, dups = catalog.dedupe_by_date(granules, start, end)
    want = [start + dt.timedelta(n) for n in range((end - start).days + 1)]
    missing = [d.isoformat() for d in want if d not in kept]
    variables = list(spec["variables"])
    rows = []
    for roi in rois:
        key = (roi["region_id"], roi["subregion_id"])
        geom = roi_geoms[key]
        m = estimate.membership(grid, geom)
        reqs = estimate.request_tiles(grid, geom, m, variables, max_cells)
        estimate.check_tiles(geom, reqs, m, max_cells, step=grid.step)
        path = membership_path(membership_dir, roi)
        estimate.write_membership(m, path)
        days = len(want) - len(missing)
        cells = sum(q["expected_cells"] for q in reqs)
        rows.append({"region_id": key[0], "subregion_id": key[1], "geometry_version": roi["geometry_version"],
                     "requests": reqs, "bbox_cells": m["bbox_cells"], "roi_cells": m["roi_cells"],
                     "roi_area_weighted_km2": round(m["roi_area_weighted_km2"], 2),
                     "daily_files": days * len(reqs),
                     "transfer_bytes_upper": days * (cells * 4 * len(variables) + OVERHEAD_BYTES * len(reqs)),
                     "final_rows": days * len(variables), "membership_table": path.name})
    return {
        "key": KEY, "period": period,
        "collection": {"short_name": spec["short_name"], "version": spec.get("version"),
                       "concept_id": spec["concept_id"]},
        "variables": variables,
        "grid": {"lat0": grid.lat0, "lon0": grid.lon0, "step": grid.step, "nlat": grid.nlat, "nlon": grid.nlon},
        "access": "Harmony sds/HOSS-geographic (bbox + temporal + variable subset, NetCDF-4); Earthdata Login",
        "requested_days": len(want), "available_days": len(want) - len(missing), "missing_dates": missing,
        "duplicate_granules": len(dups),
        "rois": rows,
        "daily_files": sum(r["daily_files"] for r in rows),
        "transfer_bytes_upper": sum(r["transfer_bytes_upper"] for r in rows),
        "final_rows": sum(r["final_rows"] for r in rows),
        "fetch_guards": [
            "Only the boxes in imerg.rois[].requests may be sent to Harmony.",
            "Reject any file whose cells are not the approved request's 0.1 deg grid cells.",
            "Only cells in the ROI membership table enter the daily aggregate.",
        ],
        "unknowns": [
            "Late Run values are replaced by the Final Run ~3.5 months later; Late is the only run covering this period.",
            "0.1 deg cells are larger than the 5 km zones: zone values are those of the surrounding cells.",
        ],
    }


# ---------------------------------------------------------------- read + check + aggregate

def grid_array(ds, var: str) -> np.ndarray:
    """One day of `var` as (lat, lon), whatever the stored dimension order."""
    da = ds[var]
    for d in [d for d in da.dims if d not in ("lat", "lon")]:
        if da.sizes[d] != 1:
            raise ValueError(f"{var}: dimension {d} has {da.sizes[d]} entries, expected 1")
        da = da.isel({d: 0})
    return np.asarray(da.transpose("lat", "lon").values, dtype=float)


def _file_date(ds) -> dt.date | None:
    try:
        t = np.asarray(ds["time"].values).ravel()
        return dt.date.fromisoformat(str(np.datetime_as_string(t[0].astype("datetime64[D]"))))
    except Exception:  # noqa: BLE001 - undecodable calendar: date comes from the file name instead
        return None


def checks(ds, req: dict, grid: ImergGrid, expected_date: dt.date, variables: list[str]) -> list[dict]:
    out = []
    lat, lon = np.asarray(ds["lat"].values, float), np.asarray(ds["lon"].values, float)
    out.append(check("imerg.cell_count", lat.size * lon.size == req["expected_cells"],
                     f"{lat.size}x{lon.size} cells, plan expected {req['expected_cells']}", warn=True))
    d = _file_date(ds)
    out.append(check("imerg.timestamp", None if d is None else d == expected_date,
                     f"time {d if d else 'not decodable'}, expected {expected_date} (from file name)"))
    for v in variables:
        if v not in ds:
            out.append(check(f"imerg.{v}.present", False, f"{v} missing from response"))
            continue
        units = ds[v].attrs.get("units") or ds[v].encoding.get("units")
        out.append(check(f"imerg.{v}.units", units in UNITS_OK, f"{v} units {units!r}"))
        a = grid_array(ds, v)
        f = a[np.isfinite(a)]
        out.append(check(f"imerg.{v}.value_range", f.size == 0 or (f.min() >= 0 and f.max() < MAX_MM_DAY),
                         f"{v} {f.min() if f.size else 'n/a'}..{f.max() if f.size else 'n/a'}"))
    return out


def aggregate(dss: list, membership: list[dict], grid: ImergGrid, roi: dict, date: dt.date, source: str,
              variables: list[str], version: str) -> list[dict]:
    """One day of one ROI from its tiles: weighted (overlap x cell area) over membership cells."""
    from .process import _row, _stats

    looks = []
    for ds in dss:
        lat, lon = np.asarray(ds["lat"].values, float), np.asarray(ds["lon"].values, float)
        looks.append(({grid.lat_index(float(x)): i for i, x in enumerate(lat)},
                      {grid.lon_index(float(x)): j for j, x in enumerate(lon)},
                      {v: grid_array(ds, v) for v in variables if v in ds}))
    n = len(membership)
    w = np.array([float(c["weight_km2"]) for c in membership])
    vals = {v: np.full(n, np.nan) for v in variables}
    have = np.zeros(n, bool)
    for k, c in enumerate(membership):
        ci, cj = int(c["lat_index"]), int(c["lon_index"])
        for li, lj, arrs in looks:
            if ci in li and cj in lj:
                have[k] = True
                for v, a in arrs.items():
                    vals[v][k] = a[li[ci], lj[cj]]
                break
    qc = f"missing_in_response={int((~have).sum())}"
    rows = []
    for v in variables:
        units = "mm/day"
        rows.append(_row(date, roi, KEY, v, units, _stats(vals[v], w), n, source, version, qc))
    return rows
