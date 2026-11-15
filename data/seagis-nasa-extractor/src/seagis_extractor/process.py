"""Daily per-ROI aggregates (estimate.FINAL_SCHEMA) from validated subsets.

Only cells in the ROI membership table are used, weighted by their overlap with the zone
(MUR: overlap fraction x cell area in km²; Copernicus: overlap fraction). MUR cells flagged as
land/lake by MUR's own `mask`, and Copernicus cells marked land in the static mask, are dropped.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
from pathlib import Path

import numpy as np

# MUR v4.1 mask bits: 1 open sea, 2 land, 4 lake, 8 sea ice, 16 possible ice
MUR_SEA_BIT, MUR_LAND_BIT, MUR_LAKE_BIT = 1, 2, 4

MUR_OUTPUT = {"analysed_sst": ("degree_C", -273.15), "analysis_error": ("kelvin", 0.0),
              "sea_ice_fraction": ("1", 0.0)}


def read_membership(path: Path) -> list[dict]:
    with gzip.open(path, "rt", newline="") as f:
        return list(csv.DictReader(f))


def _stats(vals: np.ndarray, w: np.ndarray) -> dict:
    ok = np.isfinite(vals) & (w > 0)
    if not ok.any():
        return {"valid_pixel_count": 0, "mean": None, "min": None, "max": None, "std": None}
    v, ww = vals[ok], w[ok]
    mean = float(np.sum(v * ww) / np.sum(ww))
    std = float(np.sqrt(np.sum(ww * (v - mean) ** 2) / np.sum(ww)))
    return {"valid_pixel_count": int(ok.sum()), "mean": round(mean, 6), "min": round(float(v.min()), 6),
            "max": round(float(v.max()), 6), "std": round(std, 6)}


def _row(date, roi, dataset, variable, units, stats, n_roi, source, version, qc):
    return {"date": date.isoformat(), "region_id": roi["region_id"], "subregion_id": roi["subregion_id"],
            "dataset": dataset, "variable": variable, "units": units,
            "valid_pixel_count": stats["valid_pixel_count"], "roi_pixel_count": n_roi,
            "coverage_fraction": round(stats["valid_pixel_count"] / n_roi, 4) if n_roi else 0.0,
            "mean": stats["mean"], "min": stats["min"], "max": stats["max"], "std": stats["std"],
            "area_weighted": True, "source_granule": source, "product_version": version,
            "geometry_version": roi.get("geometry_version", "v1"), "qc_flags": qc}


def aggregate_mur(dss: list, membership: list[dict], grid, roi: dict, date: dt.date, source: str) -> tuple[list[dict], dict]:
    """One day of one ROI. `dss` are the day's tiles (one per approved request box)."""
    lookups = []
    for ds in dss:
        lat = np.asarray(ds["lat"].values, dtype=float)
        lon = np.asarray(ds["lon"].values, dtype=float)
        lookups.append((ds, {grid.lat_index(float(x)): i for i, x in enumerate(lat)},
                        {grid.lon_index(float(x)): j for j, x in enumerate(lon)}, lat.size, lon.size))
    n = len(membership)
    w = np.array([float(c["weight_km2"]) for c in membership])
    have = np.zeros(n, bool)
    sea = np.ones(n, bool)
    vals = {v: np.full(n, np.nan) for v in MUR_OUTPUT}
    for k, c in enumerate(membership):
        ci, cj = int(c["lat_index"]), int(c["lon_index"])
        for ds, li, lj, nl, nm in lookups:
            if ci in li and cj in lj:
                i, j = li[ci], lj[cj]
                have[k] = True
                if "mask" in ds:
                    m = np.asarray(ds["mask"].values, dtype=float).reshape(nl, nm)[i, j]
                    m = 0 if not np.isfinite(m) else int(m)
                    sea[k] = bool(m & MUR_SEA_BIT) and not (m & (MUR_LAND_BIT | MUR_LAKE_BIT))
                for var, (_, offset) in MUR_OUTPUT.items():
                    if var in ds:
                        vals[var][k] = float(np.asarray(ds[var].values, dtype=float).reshape(nl, nm)[i, j]) + offset
                break
    n_land = int((have & ~sea).sum())
    info = {"membership_cells": n, "cells_in_response": int(have.sum()), "cells_mur_land_or_lake": n_land}
    qc = f"mur_land_or_lake_cells={n_land};missing_in_response={int((~have).sum())}"
    rows = []
    for var, (units, _) in MUR_OUTPUT.items():
        if not any(var in ds for ds in dss):
            continue
        a = np.where(have & sea, vals[var], np.nan)
        rows.append(_row(date, roi, "mur_sst", var, units, _stats(a, w), n, source, "MUR v4.1", qc))
    return rows, info


def aggregate_copernicus(ds, membership: list[dict], roi: dict, key: str, version: str) -> list[dict]:
    lat = np.asarray(ds["latitude"].values, dtype=float)
    lon = np.asarray(ds["longitude"].values, dtype=float)
    lat_ix = {round(float(x), 4): i for i, x in enumerate(lat)}
    lon_ix = {round(float(x), 4): j for j, x in enumerate(lon)}
    sea = [c for c in membership if c.get("sea") in (True, "True", "true", 1, "1")]
    pos = [(lat_ix.get(round(float(c["lat"]), 4)), lon_ix.get(round(float(c["lon"]), 4))) for c in sea]
    keep = [(i, j, float(c["overlap_fraction"])) for (i, j), c in zip(pos, sea) if i is not None and j is not None]
    times = np.asarray(ds["time"].values).astype("datetime64[D]").astype(str)
    rows = []
    for var in ds.data_vars:
        a = np.asarray(ds[var].values, dtype=float).reshape(len(times), lat.size, lon.size)
        units = ds[var].attrs.get("units", "")
        for t, day in enumerate(times):
            vals = np.array([a[t, i, j] for i, j, _ in keep]) if keep else np.array([])
            w = np.array([f for _, _, f in keep]) if keep else np.array([])
            qc = f"sea_cells={len(keep)};land_cells_dropped={len(membership) - len(sea)}"
            rows.append(_row(dt.date.fromisoformat(day), roi, key, var, units, _stats(vals, w), len(membership),
                             key, version, qc))
    if "uo" in ds.data_vars and "vo" in ds.data_vars:
        u = np.asarray(ds["uo"].values, dtype=float).reshape(len(times), lat.size, lon.size)
        v = np.asarray(ds["vo"].values, dtype=float).reshape(len(times), lat.size, lon.size)
        units = ds["uo"].attrs.get("units", "m s-1")
        qc = f"sea_cells={len(keep)};land_cells_dropped={len(membership) - len(sea)};derived_from=uo,vo"
        for t, day in enumerate(times):
            uu = np.array([u[t, i, j] for i, j, _ in keep]) if keep else np.array([])
            vv = np.array([v[t, i, j] for i, j, _ in keep]) if keep else np.array([])
            w = np.array([f for _, _, f in keep]) if keep else np.array([])
            for var, un, st in current_stats(uu, vv, w, units):
                rows.append(_row(dt.date.fromisoformat(day), roi, key, var, un, st, len(membership), key, version, qc))
    return rows


def current_stats(u: np.ndarray, v: np.ndarray, w: np.ndarray, units: str) -> list[tuple[str, str, dict]]:
    """Derived current variables from eastward (u) and northward (v) components of the same cells.

    - current_speed: weighted mean of per-cell speed hypot(u, v); min/max/std over cells.
    - current_direction: direction of the weighted mean vector, degrees clockwise from north, the
      way the water flows TO (oceanographic convention). A circular quantity, so min/max/std are null.
    - current_steadiness: |mean vector| / mean speed, 0..1. Near 1 = cells flow the same way;
      near 0 = directions cancel out and current_direction is not meaningful.
    """
    ok = np.isfinite(u) & np.isfinite(v) & (w > 0) if len(u) else np.array([], bool)
    speed = np.hypot(u, v) if len(u) else np.array([])
    sp = _stats(np.where(ok, speed, np.nan), w) if len(u) else _stats(np.array([]), np.array([]))
    empty = {"valid_pixel_count": 0, "mean": None, "min": None, "max": None, "std": None}
    if not ok.any():
        return [("current_speed", units, sp), ("current_direction", "degree", empty), ("current_steadiness", "1", empty)]
    ww = w[ok]
    um, vm = float(np.sum(u[ok] * ww) / np.sum(ww)), float(np.sum(v[ok] * ww) / np.sum(ww))
    mag = float(np.hypot(um, vm))
    n = int(ok.sum())
    direction = round(float(np.degrees(np.arctan2(um, vm)) % 360.0), 3)
    steady = round(mag / sp["mean"], 6) if sp["mean"] else None
    return [("current_speed", units, sp),
            ("current_direction", "degree", {"valid_pixel_count": n, "mean": direction, "min": None, "max": None, "std": None}),
            ("current_steadiness", "1", {"valid_pixel_count": n, "mean": steady, "min": None, "max": None, "std": None})]
