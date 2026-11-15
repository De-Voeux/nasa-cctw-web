"""Response guards and pilot checks.

Guards (raise FetchGuardError, the file is deleted by the caller): the response must lie inside
the approved request's expected extent. Everything else is a *check* with PASS / WARN / FAIL,
recorded in the pilot report so the plan can be recalibrated.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from .fetch import FetchGuardError

TOL = 1e-6


def _coord(ds, *names):
    for n in names:
        if n in ds.coords or n in ds.variables:
            return np.asarray(ds[n].values, dtype=float)
    raise KeyError(f"none of {names} in dataset")


def check(name: str, ok: bool | None, detail: str, warn: bool = False) -> dict:
    status = "PASS" if ok else ("WARN" if warn or ok is None else "FAIL")
    return {"check": name, "status": status, "detail": detail}


# ---------------------------------------------------------------- MUR

def mur_guard(ds, req: dict, step: float = 0.01, lat0: float = -89.99, lon0: float = -179.99) -> None:
    """Fail closed if any returned cell is not one of the approved request's grid cells.

    Compared as grid indices: MUR coordinates are float32 (~1e-5 deg precision near 120 deg), so a
    plain float comparison against the extent rejects exact matches.
    """
    lat, lon = _coord(ds, "lat", "latitude"), _coord(ds, "lon", "longitude")
    if lat.size == 0 or lon.size == 0:
        raise FetchGuardError("response has no lat/lon cells")
    h = step / 2
    w, s, e, n = req["expected_extent_w_s_e_n"]
    i0, i1 = round((s + h - lat0) / step), round((n - h - lat0) / step)
    j0, j1 = round((w + h - lon0) / step), round((e - h - lon0) / step)
    li = np.rint((lat - lat0) / step).astype(int)
    lj = np.rint((lon - lon0) / step).astype(int)
    off = max(float(np.abs(lat - (lat0 + step * li)).max()), float(np.abs(lon - (lon0 + step * lj)).max()))
    if off > step / 4:
        raise FetchGuardError(f"response cells are not on the {step} deg grid (offset {off:.4f} deg)")
    if li.min() < i0 or li.max() > i1 or lj.min() < j0 or lj.max() > j1:
        raise FetchGuardError(
            f"response extent lon {lon.min() - h:.4f}..{lon.max() + h:.4f}, lat {lat.min() - h:.4f}..{lat.max() + h:.4f} "
            f"outside approved extent {req['expected_extent_w_s_e_n']}")


def mur_checks(ds, req: dict, grid, expected_date: dt.date) -> list[dict]:
    out = []
    lat, lon = _coord(ds, "lat", "latitude"), _coord(ds, "lon", "longitude")
    cells = lat.size * lon.size
    out.append(check("mur.cell_count", cells == req["expected_cells"],
                     f"{lat.size}x{lon.size}={cells} cells, plan expected {req['expected_cells']}", warn=True))
    out.append(check("mur.lat_order", None if lat.size < 2 else True,
                     "ascending" if lat.size < 2 or lat[1] > lat[0] else "descending", warn=True))
    gi = req["grid_index_range"]
    li = [grid.lat_index(float(lat.min())), grid.lat_index(float(lat.max()))]
    lj = [grid.lon_index(float(lon.min())), grid.lon_index(float(lon.max()))]
    off = max(float(np.abs(lat - grid.lat(np.array([grid.lat_index(x) for x in lat]))).max()),
              float(np.abs(lon - grid.lon(np.array([grid.lon_index(x) for x in lon]))).max()))
    out.append(check("mur.grid_origin", off < 1e-4,
                     f"max offset from assumed grid {off:.2e} deg; index range lat {li} lon {lj} vs plan {gi['lat']} {gi['lon']}"))
    out.append(check("mur.grid_index_range", li == gi["lat"] and lj == gi["lon"],
                     f"lat {li} vs {gi['lat']}, lon {lj} vs {gi['lon']}", warn=True))
    t = np.asarray(ds["time"].values).ravel()
    stamps = [np.datetime_as_string(x, unit="m") for x in t.astype("datetime64[m]")]
    out.append(check("mur.timestamp", len(t) == 1 and stamps[0].startswith(expected_date.isoformat()),
                     f"time {stamps}, expected date {expected_date}"))
    sst = ds["analysed_sst"]
    units = sst.attrs.get("units") or sst.encoding.get("units")
    out.append(check("mur.units", units == "kelvin", f"analysed_sst units {units!r}"))
    v = np.asarray(sst.values, dtype=float)
    finite = v[np.isfinite(v)]
    out.append(check("mur.value_range", finite.size == 0 or (finite.min() > 270 and finite.max() < 310),
                     f"analysed_sst {finite.min() if finite.size else 'n/a'}..{finite.max() if finite.size else 'n/a'} K"))
    out.append(check("mur.fill_fraction", True, f"{1 - finite.size / max(v.size, 1):.3f} of box cells are fill (land)"))
    return out


# ---------------------------------------------------------------- Copernicus

def copernicus_guard(ds, bbox: list[float], step_lat: float, step_lon: float) -> None:
    lat, lon = _coord(ds, "latitude", "lat"), _coord(ds, "longitude", "lon")
    if lat.size == 0 or lon.size == 0:
        raise FetchGuardError("Copernicus subset has no cells")
    w, s, e, n = bbox
    if (lat.min() < s - step_lat - TOL or lat.max() > n + step_lat + TOL
            or lon.min() < w - step_lon - TOL or lon.max() > e + step_lon + TOL):
        raise FetchGuardError(f"Copernicus subset lat {lat.min()}..{lat.max()} lon {lon.min()}..{lon.max()} "
                              f"outside request box {bbox} (+1 cell)")


def copernicus_checks(ds, key: str, roi_row: dict, dates: list[dt.date], membership: list[dict]) -> list[dict]:
    out = []
    lat, lon = _coord(ds, "latitude", "lat"), _coord(ds, "longitude", "lon")
    li, lj = roi_row["lat_index"], roi_row["lon_index"]
    exp = (li[1] - li[0] + 1, lj[1] - lj[0] + 1)
    out.append(check(f"{key}.cell_count", (lat.size, lon.size) == exp,
                     f"{lat.size}x{lon.size} vs plan {exp[0]}x{exp[1]}", warn=True))
    t = np.asarray(ds["time"].values).astype("datetime64[D]").astype(str).tolist()
    out.append(check(f"{key}.dates", t == [d.isoformat() for d in dates], f"{t[0] if t else '-'}..{t[-1] if t else '-'} ({len(t)} days)"))
    if "depth" in ds.coords or "depth" in ds.variables:
        d = np.asarray(ds["depth"].values, dtype=float).ravel()
        out.append(check(f"{key}.depth", d.size == 1 and abs(d[0] - 0.494) < 0.01, f"depth {d.tolist()} m"))
    lat_ix = {round(float(x), 4): i for i, x in enumerate(lat)}
    lon_ix = {round(float(x), 4): j for j, x in enumerate(lon)}
    for v in ds.data_vars:
        a = np.asarray(ds[v].values, dtype=float).reshape(len(t), lat.size, lon.size) if len(t) else None
        sea_ok = land_nan = 0
        sea_n = land_n = 0
        for c in membership:
            i, j = lat_ix.get(round(float(c["lat"]), 4)), lon_ix.get(round(float(c["lon"]), 4))
            if i is None or j is None or a is None:
                continue
            col = a[:, i, j]
            if c["sea"] in (True, "True", "true", 1, "1"):
                sea_n += 1
                sea_ok += int(np.isfinite(col).all())
            else:
                land_n += 1
                land_nan += int(np.isnan(col).all())
        units = ds[v].attrs.get("units")
        out.append(check(f"{key}.{v}.sea_cells_valid", sea_n > 0 and sea_ok == sea_n,
                         f"{sea_ok}/{sea_n} sea cells finite on every day; units {units!r}"))
        out.append(check(f"{key}.{v}.land_cells_empty", land_nan == land_n,
                         f"{land_nan}/{land_n} mask-land cells are empty", warn=True))
    return out
