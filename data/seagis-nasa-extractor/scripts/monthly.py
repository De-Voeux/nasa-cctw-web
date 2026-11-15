"""Long-term MONTHLY zone values, 2015-01 .. 2024-12 (decided 2026-11-15, docs/Calzy/LONG_TERM_DATA.md).

The window was first 2003-01..2024-12; it was cut to the last 10 full years so the fetch finishes in time.
Files already fetched for the longer window are kept on disk and trimmed to the window at export.

A lean standalone script next to the daily pipeline. Same 48 zones, same membership/area weighting.

    python scripts/monthly.py list                         # metadata only: writes outputs/monthly/requests.json, prints its hash
    python scripts/monthly.py fetch --approve <sha256> [--source mur|imerg|copernicus|power] [--zone REGION/sub]
    python scripts/monthly.py export --confirm-host <db host>

`fetch` sends only the requests listed in requests.json, and only when its hash equals --approve.
Finished zones are skipped (one Parquet per source x zone in data/processed_monthly/).

Sources
- mur_sst_monthly     NOAA ERD ERDDAP jplMURSST41mday (monthly mean of daily NASA JPL MUR v4.1, 0.01 deg)
- gpm_imerg_monthly   GPM_3IMERGM V07 (IMERG Final monthly) via NASA Harmony
- cmems_phy_my        Copernicus GLOBAL_MULTIYEAR_PHY_001_030 P1M: so, uo, vo (+ mean-vector direction/speed)
- cmems_bgc_my        Copernicus GLOBAL_MULTIYEAR_BGC_001_029 P1M: no3, po4, ph
- nasa_power_monthly  NASA POWER monthly point, same 7 parameters as the daily run
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import csv
import json
import re
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seagis_extractor import auth, copernicus, estimate, export, imerg, process, validate  # noqa: E402
from seagis_extractor.fetch import (ByteBudget, FetchError, FetchGuardError, HarmonyClient,  # noqa: E402
                                    json_transport, stream_transport)
from seagis_extractor.http import MetadataClient  # noqa: E402

START, END = dt.date(2015, 1, 1), dt.date(2024, 12, 31)    # default window; list/fetch/export can set another
MONTHS: list[dt.date] = []


def set_window(start: dt.date, end: dt.date) -> None:
    """Month-start dates START..END. Fetch takes the window from the approved request list."""
    global START, END, MONTHS
    if start.day != 1 or end < start:
        raise SystemExit(f"bad window {start}..{end}")
    START, END = start, end
    MONTHS = [dt.date(y, m, 1) for y in range(start.year, end.year + 1) for m in range(1, 13)
              if start <= dt.date(y, m, 1) <= end]


set_window(START, END)
OUT = ROOT / "outputs/monthly"
PROCESSED = ROOT / "data/processed_monthly"
REQUESTS = OUT / "requests.json"
MIGRATION = "20261115020000_seagis_monthly_metrics.sql"

ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41mday.nc"
ERDDAP_HOST = "coastwatch.pfeg.noaa.gov"
IMERGM = {"short_name": "GPM_3IMERGM", "version": "07", "concept_id": "C2723754851-GES_DISC"}
POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
POWER_PARAMS = ["T2M", "RH2M", "WS10M", "WD10M", "ALLSKY_SFC_SW_DWN", "ALLSKY_SFC_PAR_TOT", "CLOUD_AMT"]
CMEMS = [
    {"key": "cmems_phy_my", "product_id": "GLOBAL_MULTIYEAR_PHY_001_030",
     "dataset_id": "cmems_mod_glo_phy_my_0.083deg_P1M-m_202311", "variables": ["so", "uo", "vo"], "depth": "surface",
     "static": "cmems_mod_glo_phy_my_0.083deg_static_202311--ext--bathy", "daily_key": "cmems_phy_so"},
    {"key": "cmems_bgc_my", "product_id": "GLOBAL_MULTIYEAR_BGC_001_029",
     "dataset_id": "cmems_mod_glo_bgc_my_0.25deg_P1M-m_202406", "variables": ["no3", "po4", "ph"], "depth": "surface",
     "static": "cmems_mod_glo_bgc_my_0.25deg_static_202406--ext--mask", "daily_key": "cmems_bgc_nut"},
]
MUR_GRID = estimate.MurGrid()
COPERNICUS_WORKERS = 6       # dataset x region jobs in parallel (one region took ~8 min alone)


# ---------------------------------------------------------------- shared

def daily_plan() -> dict:
    return json.loads((ROOT / "outputs/plan.json").read_text())


def zone_geoms() -> dict:
    import shapely.geometry
    gj = json.loads((ROOT / "data/roi/roi_candidates_v1.geojson").read_text())
    return {(f["properties"]["region_id"], f["properties"]["subregion_id"]): shapely.geometry.shape(f["geometry"])
            for f in gj["features"]}


def zkey(z) -> str:
    return f"{z['region_id']}/{z['subregion_id']}"


def canonical_sha(obj) -> str:
    return estimate.canonical_hash(obj)


def write_rows(rows: list[dict], path: Path) -> int:
    import pandas as pd
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    pd.DataFrame(rows).to_parquet(tmp, index=False)
    tmp.replace(path)
    return len(rows)


def month_row(month: dt.date, zone: dict, dataset, variable, units, stats, n_roi, source, version, qc, weighted=True):
    r = process._row(month, zone, dataset, variable, units, stats, n_roi, source, version, qc)
    r["month"] = r.pop("date")
    r["area_weighted"] = weighted
    return r


EMPTY = {"valid_pixel_count": 0, "mean": None, "min": None, "max": None, "std": None}


def read_membership(path: Path) -> list[dict]:
    return process.read_membership(path)


def write_membership(table: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz, \
            io.TextIOWrapper(gz, newline="") as f:    # mtime=0: same table -> same bytes -> same hash
        w = csv.DictWriter(f, fieldnames=list(table[0]) if table else ["lat_index"])
        w.writeheader()
        w.writerows(table)


# ---------------------------------------------------------------- list (metadata only)

def erddap_url(req: dict) -> str:
    (i0, i1), (j0, j1) = req["grid_index_range"]["lat"], req["grid_index_range"]["lon"]
    lat = lambda i: f"{MUR_GRID.lat(i):.2f}"  # noqa: E731
    lon = lambda j: f"{MUR_GRID.lon(j):.2f}"  # noqa: E731
    t = f"[({START}T00:00:00Z):1:({END}T00:00:00Z)]"
    sp = f"[({lat(i0)}):1:({lat(i1)})][({lon(j0)}):1:({lon(j1)})]"
    return f"{ERDDAP}?sst{t}{sp},mask{t}{sp}"


def erddap_months(client: MetadataClient) -> list[str]:
    r = client.request("GET", ERDDAP.replace(".nc", ".csv0") + "?time")
    if r.status != 200:
        raise RuntimeError(f"ERDDAP time axis: HTTP {r.status}")
    return sorted({line[:7] for line in r.body.decode().split() if line[:4].isdigit()})


def cmems_section(client: MetadataClient, spec: dict, plan: dict, geoms: dict) -> dict:
    ds = copernicus.resolve_dataset(client, spec, START, END)
    months = sorted({d.strftime("%Y-%m") for d in ds["_tdates"].values()})
    daily = next(d for d in plan["copernicus"]["datasets"] if d["key"] == spec["daily_key"])
    boxes = {reg: r["bbox_w_s_e_n"] for reg, r in daily["regions"].items()}
    mask = copernicus.SeaMask(client, spec["product_id"], spec["static"], ds, boxes, ROOT / "data/raw/static/copernicus")
    zones, regions = [], {}
    for z in plan["rois"]:
        k = (z["region_id"], z["subregion_id"])
        rc = copernicus.roi_chunks(ds, z["request"]["bbox_w_s_e_n"])
        m = copernicus.roi_membership(ds, rc, geoms[k])
        sea = copernicus.sea_summary(mask, m["table"])
        path = OUT / "membership" / f"{spec['key']}__{k[0]}__{k[1]}__v1.csv.gz"
        write_membership(m["table"], path)
        zones.append({"region_id": k[0], "subregion_id": k[1], "geometry_version": z["geometry_version"],
                      "bbox_w_s_e_n": z["request"]["bbox_w_s_e_n"], "roi_cells": m["roi_cells"],
                      "sea_cells": sea["sea_cells"], "membership": path.name,
                      "membership_sha256": estimate.file_sha256(path)})
    tsel = ds["_tsel"]
    for reg, box in boxes.items():
        rc = copernicus.roi_chunks(ds, box)
        (i0, i1), (j0, j1) = rc["lat_index"], rc["lon_index"]
        regions[reg] = {"bbox_w_s_e_n": box, "chunks": len(rc["keys"]), "cells": rc["cells"],
                        "chunk_keys": sorted(rc["keys"]), "lat_index": [i0, i1], "lon_index": [j0, j1],
                        "lat": [round(float(x), 6) for x in ds["_lat"][i0:i1 + 1]],
                        "lon": [round(float(x), 6) for x in ds["_lon"][j0:j1 + 1]]}
    zmeta = copernicus.zarr_metadata(client, ds["store"])
    var_meta = {}
    for v in spec["variables"]:
        za, at = zmeta[f"{v}/.zarray"], zmeta.get(f"{v}/.zattrs", {})
        var_meta[v] = {"shape": za["shape"], "chunks": za["chunks"], "dtype": za["dtype"], "compressor": za.get("compressor"),
                       "fill_value": za.get("fill_value"), "units": at.get("units"),
                       **{k: at[k] for k in ("scale_factor", "add_offset", "_FillValue", "missing_value") if k in at}}
    return {"key": spec["key"], "product_id": spec["product_id"], "dataset_id": spec["dataset_id"],
            "store": ds["store"], "depth_index": ds["depth"]["index"], "var_meta": var_meta,
            "time_index": [min(tsel), max(tsel)], "times": [ds["_tdates"][t].isoformat() for t in tsel],
            "variables": spec["variables"], "depth_m": abs(ds["depth"]["elevation_m"]),
            "grid": ds["grid"], "time_extent": ds["time_extent"],
            "months_available": len(months), "missing_months": sorted({m.strftime("%Y-%m") for m in MONTHS} - set(months)),
            "static_mask": spec["static"], "regions": regions, "zones": zones,
            "zones_without_sea": [zkey(z) for z in zones if z["sea_cells"] == 0]}


def cmd_list(args) -> int:
    set_window(dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end))
    requests_path = Path(args.out) if args.out else REQUESTS
    client = MetadataClient()
    plan, geoms = daily_plan(), zone_geoms()
    OUT.mkdir(parents=True, exist_ok=True)
    have = erddap_months(client)
    want = [m.strftime("%Y-%m") for m in MONTHS]
    mur = {"dataset": "mur_sst_monthly", "product": "jplMURSST41mday (NOAA ERD monthly mean of NASA JPL MUR v4.1)",
           "missing_months": [m for m in want if m not in have], "zones": []}
    for z in plan["rois"]:
        k = (z["region_id"], z["subregion_id"])
        mpath = ROOT / "outputs/membership" / f"mur_sst__{k[0]}__{k[1]}__{z['geometry_version']}.csv.gz"
        reqs = [{"url": erddap_url(q), "expected_cells": q["expected_cells"],
                 "expected_extent_w_s_e_n": q["expected_extent_w_s_e_n"], "grid_index_range": q["grid_index_range"]}
                for q in z["mur_requests"]]
        mur["zones"].append({"region_id": k[0], "subregion_id": k[1], "geometry_version": z["geometry_version"],
                             "membership": mpath.name, "membership_sha256": estimate.file_sha256(mpath), "requests": reqs})
    mur["transfer_bytes_est"] = sum(q["expected_cells"] for z in mur["zones"] for q in z["requests"]) * len(want) * 5

    granules = imerg.catalog.list_granules(client, IMERGM["short_name"], "3B-MO.MS.MRG.3IMERG.*.V07*", START, END,
                                           concept_id=IMERGM["concept_id"])
    gdates = sorted({m.group(1) for g in granules
                     if (m := re.search(r"\.(\d{8})-S", g.get("granule_ur") or g.get("file_name") or ""))})
    im = {"dataset": "gpm_imerg_monthly", "collection": IMERGM, "variables": ["precipitation"], "harmony_variables": ["Grid/precipitation"],
          "units_expected": "mm/hr (CMR UMM-Var), stored as mm/day = x24",
          "granules": len(gdates), "missing_months": [m for m in want if m.replace("-", "") + "01" not in gdates],
          "zones": []}
    irows = {(r["region_id"], r["subregion_id"]): r for r in plan["imerg"]["rois"]}
    for z in plan["rois"]:
        k = (z["region_id"], z["subregion_id"])
        r = irows[k]
        im["zones"].append({"region_id": k[0], "subregion_id": k[1], "geometry_version": z["geometry_version"],
                            "membership": r["membership_table"],
                            "membership_sha256": estimate.file_sha256(ROOT / "outputs/membership" / r["membership_table"]),
                            "requests": [{"bbox_w_s_e_n": q["bbox_w_s_e_n"], "expected_cells": q["expected_cells"],
                                          "expected_extent_w_s_e_n": q["expected_extent_w_s_e_n"]} for q in r["requests"]]})
    im["transfer_bytes_est"] = sum(q["expected_cells"] for z in im["zones"] for q in z["requests"]) * 4 * len(want) \
        + 30_000 * len(want) * sum(len(z["requests"]) for z in im["zones"])

    pw = {"dataset": "nasa_power_monthly", "parameters": POWER_PARAMS, "zones": []}
    for r in plan["power"]["rois"]:
        q = {"parameters": ",".join(POWER_PARAMS), "community": "AG", "longitude": f"{r['lon']:.4f}",
             "latitude": f"{r['lat']:.4f}", "start": str(START.year), "end": str(END.year), "format": "JSON"}
        pw["zones"].append({k: r[k] for k in ("region_id", "subregion_id", "geometry_version", "lat", "lon")}
                           | {"url": f"{POWER_URL}?{urllib.parse.urlencode(q)}"})

    cm = [cmems_section(client, s, plan, geoms) for s in CMEMS]

    body = {"period": {"start": START.isoformat(), "end": END.isoformat(), "months": len(MONTHS)},
            "mur": mur, "imerg": im, "copernicus": cm, "power": pw,
            "decisions": [f"window {START:%Y-%m}..{END:%Y-%m} for every source in this list",
                          "missing months kept as empty rows flagged missing_at_source",
                          "currents: monthly mean vector only (uo, vo, current_direction, current_vector_speed)",
                          "storage: public.seagis_monthly_metrics"]}
    doc = {"sha256": canonical_sha(body), "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), **body}
    requests_path.write_text(json.dumps(doc, indent=1))
    n_req = sum(len(z["requests"]) for z in mur["zones"]) + sum(len(z["requests"]) for z in im["zones"]) \
        + len(pw["zones"]) + sum(len(c["regions"]) for c in cm)
    print(f"wrote {requests_path.resolve().relative_to(ROOT)}")
    print(f"period {START}..{END}, {len(MONTHS)} months, {len(plan['rois'])} zones, {n_req} requests")
    print(f"  MUR (ERDDAP)    {sum(len(z['requests']) for z in mur['zones'])} requests, ~{mur['transfer_bytes_est'] / 1e6:.0f} MB, "
          f"missing months {mur['missing_months']}")
    print(f"  IMERG monthly   {sum(len(z['requests']) for z in im['zones'])} Harmony jobs, {im['granules']} granules, "
          f"~{im['transfer_bytes_est'] / 1e6:.0f} MB, missing months {im['missing_months']}")
    for c in cm:
        print(f"  {c['key']:<15} {len(c['regions'])} region boxes, {sum(r['chunks'] for r in c['regions'].values())} chunks, "
              f"{c['months_available']}/{len(MONTHS)} months, depth {c['depth_m']:.3f} m, zones without sea {c['zones_without_sea']}")
    print(f"  POWER monthly   {len(pw['zones'])} requests")
    print(f"sha256 {doc['sha256']}")
    return 0


# ---------------------------------------------------------------- fetch

def load_approved(sha: str, path: Path) -> dict:
    doc = json.loads(path.read_text())
    body = {k: v for k, v in doc.items() if k not in ("sha256", "generated_at")}
    if canonical_sha(body) != doc["sha256"] or doc["sha256"] != sha:
        raise SystemExit(f"{path.name} hash {canonical_sha(body)} is not the approved {sha}; nothing fetched")
    set_window(dt.date.fromisoformat(doc["period"]["start"]), dt.date.fromisoformat(doc["period"]["end"]))
    return doc


def zone_out(dataset: str, region: str, sub: str) -> Path | None:
    """Where this zone's rows for the current window go, or None when files on disk already hold
    every month of the window. Files: `<sub>.parquet` (first runs) and `<sub>__<YYYY-MM>_<YYYY-MM>.parquet`."""
    import pandas as pd
    d = PROCESSED / dataset / region
    want = {m.isoformat() for m in MONTHS}
    have: set[str] = set()
    for f in [d / f"{sub}.parquet", *sorted(d.glob(f"{sub}__*.parquet"))]:
        if f.exists() and f.stat().st_size > 0:
            have |= set(pd.read_parquet(f, columns=["month"])["month"].astype(str).str[:10])
    if want <= have:
        return None
    return d / f"{sub}__{START:%Y-%m}_{END:%Y-%m}.parquet"


def _download(url: str, dest: Path, budget: ByteBudget, host: str, retries: int = 5) -> int:
    if urllib.parse.urlsplit(url).hostname != host:
        raise FetchGuardError(f"{url} is not on {host}")
    for attempt in range(1, retries + 1):
        n = 0
        with dest.open("wb") as f:
            def sink(b):
                nonlocal n
                budget.add(len(b))
                n += len(b)
                f.write(b)
            try:
                r = stream_transport(url, {}, 600, sink)
            except Exception as e:  # noqa: BLE001
                r, err = None, e
        if r is not None and r.status == 200:
            return n
        if attempt == retries:
            raise FetchError(f"GET {url[:120]} -> {r.status if r else err}")
        time.sleep(5 * attempt)
    raise AssertionError


def run_zones(name: str, fn, zones: list[dict], workers: int) -> None:
    """Run `fn(zone)` for each zone, `workers` at a time. A failed zone is logged and left without a
    Parquet file, so the next run retries it; guard and credential errors stop everything."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    failed = []
    with ThreadPoolExecutor(max(1, workers)) as pool:
        futs = {pool.submit(fn, z): zkey(z) for z in zones}
        for f in as_completed(futs):
            try:
                f.result()
            except (FetchGuardError, auth.AuthError):
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            except Exception as e:  # noqa: BLE001 - logged; retried on the next run
                failed.append(futs[f])
                print(f"{name} {futs[f]}: FAILED {type(e).__name__}: {str(e)[:300]}", flush=True)
    if failed:
        raise FetchError(f"{name}: {len(failed)} zone(s) failed, run the same command again to retry: {', '.join(sorted(failed))}")


def fetch_mur(doc: dict, zone_filter, budget, workers: int = 1) -> None:
    import xarray as xr
    src = doc["mur"]
    missing = set(src["missing_months"])

    def one(z):
        out = zone_out("mur_sst_monthly", z["region_id"], z["subregion_id"])
        if out is None:
            return
        mpath = ROOT / "outputs/membership" / z["membership"]
        if estimate.file_sha256(mpath) != z["membership_sha256"]:
            raise FetchGuardError(f"{mpath.name} changed since the request list was approved")
        mem = read_membership(mpath)
        tiles = []
        with tempfile.TemporaryDirectory() as td:
            for i, q in enumerate(z["requests"]):
                p = Path(td) / f"t{i}.nc"
                _download(q["url"], p, budget, ERDDAP_HOST)
                ds = xr.open_dataset(p, engine="scipy").load()
                ds = ds.rename({"latitude": "lat", "longitude": "lon"})
                validate.mur_guard(ds, q)
                if ds["sst"].attrs.get("units") != "degree_C":
                    raise FetchError(f"ERDDAP sst units {ds['sst'].attrs.get('units')!r}")
                f = ds["sst"].values[np.isfinite(ds["sst"].values)]
                if f.size and (f.min() < -2.5 or f.max() > 40):
                    raise FetchError(f"ERDDAP sst out of range {f.min()}..{f.max()}")
                tiles.append(ds)
            rows = []
            zone = {"region_id": z["region_id"], "subregion_id": z["subregion_id"], "geometry_version": z["geometry_version"]}
            for month in MONTHS:
                ym = month.strftime("%Y-%m")
                day = []
                for ds in tiles:
                    t = [i for i, v in enumerate(ds["time"].values.astype("datetime64[M]").astype(str)) if v == ym]
                    if t:
                        d = ds.isel(time=t[0])
                        day.append(d.assign(analysed_sst=d["sst"] + 273.15))   # aggregate_mur subtracts 273.15
                if ym not in missing and len(day) != len(tiles):
                    raise FetchError(f"ERDDAP returned {len(day)}/{len(tiles)} tiles for {ym}, which its time axis lists")
                if ym in missing:
                    rows.append(month_row(month, zone, "mur_sst_monthly", "analysed_sst", "degree_C", EMPTY, len(mem),
                                          "jplMURSST41mday", "MUR v4.1 monthly (NOAA ERD)", "missing_at_source"))
                    continue
                for d in day:
                    d.attrs.pop("_dummy", None)
                daily_rows, _ = process.aggregate_mur([d.drop_vars("sst") for d in day], mem, MUR_GRID, zone, month,
                                                      f"jplMURSST41mday {ym}")
                for r in daily_rows:
                    r.update({"dataset": "mur_sst_monthly", "product_version": "MUR v4.1 monthly (NOAA ERD)"})
                    r["month"] = r.pop("date")
                    rows.append(r)
        print(f"mur {zkey(z)}: {write_rows(rows, out)} rows", flush=True)

    run_zones("mur", one, [z for z in src["zones"] if not zone_filter or zkey(z) == zone_filter], workers)


def _granule_month(name: str) -> dt.date | None:
    m = re.search(r"\.(\d{4})(\d{2})01-S", name)
    return dt.date(int(m.group(1)), int(m.group(2)), 1) if m else None


def _open_imerg(p: Path):
    """HOSS keeps the HDF5 group layout: variables under /Grid (or at the root for flattened output)."""
    import xarray as xr
    for group in ("Grid", None):
        try:
            ds = xr.open_dataset(p, engine="h5netcdf", group=group, decode_times=False).load()
        except (OSError, KeyError, ValueError):
            continue
        if "precipitation" in ds:
            return ds
    raise FetchError(f"{p.name}: no precipitation variable")


def fetch_imerg(doc: dict, zone_filter, budget, workers: int = 1) -> None:
    import xarray as xr
    src = doc["imerg"]
    grid = imerg.ImergGrid()
    allowed = {tuple(q["bbox_w_s_e_n"]) for z in src["zones"] for q in z["requests"]}
    hc = HarmonyClient(auth.earthdata_token(), allowed, budget, max_polls=720)
    listed_missing = set(src["missing_months"])

    def one(z):
        out = zone_out("gpm_imerg_monthly", z["region_id"], z["subregion_id"])
        if out is None:
            return
        mpath = ROOT / "outputs/membership" / z["membership"]
        if estimate.file_sha256(mpath) != z["membership_sha256"]:
            raise FetchGuardError(f"{mpath.name} changed since the request list was approved")
        mem = read_membership(mpath)
        per_month: dict = {}
        with tempfile.TemporaryDirectory() as td:
            for i, q in enumerate(z["requests"]):
                job = hc.wait(hc.submit(IMERGM["concept_id"], src["harmony_variables"], q["bbox_w_s_e_n"], START, END))
                for link in hc.data_links(job):
                    name = Path(urllib.parse.urlsplit(link["href"]).path).name
                    month = _granule_month(name)
                    if month is None or month not in MONTHS:
                        raise FetchGuardError(f"unexpected granule {name}")
                    p = Path(td) / f"t{i}_{name}"
                    hc.download(link["href"], p)
                    ds = _open_imerg(p)
                    p.unlink()
                    validate.mur_guard(ds, q, step=grid.step, lat0=grid.lat0, lon0=grid.lon0)
                    units = ds["precipitation"].attrs.get("units") or ds["precipitation"].encoding.get("units")
                    if units in ("mm/hr", "mm hr-1", "mm/h"):
                        factor, note = 24.0, "converted=mm/hr*24"
                    elif units in imerg.UNITS_OK:
                        factor, note = 1.0, ""
                    else:
                        raise FetchError(f"{name}: precipitation units {units!r}")
                    a = imerg.grid_array(ds, "precipitation")
                    f = a[np.isfinite(a)]
                    if f.size and (f.min() < 0 or f.max() * factor > 300):
                        raise FetchError(f"{name}: monthly mean rate out of range {f.min()}..{f.max()} {units}")
                    per_month.setdefault(month, []).append((ds.assign(precipitation=ds["precipitation"] * factor), name, note))
        zone = {"region_id": z["region_id"], "subregion_id": z["subregion_id"], "geometry_version": z["geometry_version"]}
        rows = []
        for month in MONTHS:
            got = per_month.get(month, [])
            if len(got) != len(z["requests"]) and month.strftime("%Y-%m") not in listed_missing:
                raise FetchError(f"Harmony returned {len(got)}/{len(z['requests'])} files for {month:%Y-%m}, which CMR lists")
            if len(got) != len(z["requests"]):
                rows.append(month_row(month, zone, "gpm_imerg_monthly", "precipitation", "mm/day", EMPTY, len(mem),
                                      "GPM_3IMERGM", "GPM_3IMERGM V07", "missing_at_source"))
                continue
            for r in imerg.aggregate([d for d, _, _ in got], mem, grid, zone, month, ";".join(n for _, n, _ in got),
                                     ["precipitation"], "GPM_3IMERGM V07"):
                note = got[0][2]
                r.update({"dataset": "gpm_imerg_monthly", "qc_flags": f"{r['qc_flags']};{note}" if note else r["qc_flags"]})
                r["month"] = r.pop("date")
                rows.append(r)
        print(f"imerg {zkey(z)}: {write_rows(rows, out)} rows", flush=True)

    run_zones("imerg", one, [z for z in src["zones"] if not zone_filter or zkey(z) == zone_filter], workers)


def fetch_copernicus(doc: dict, zone_filter, _budget) -> None:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from seagis_extractor.fetch import crop_to_cells

    def one_region(c, reg, rbox, todo, outs):
            t0 = time.monotonic()
            step_lat, step_lon = c["grid"]["lat_step"], c["grid"]["lon_step"]
            ds, n_missing = read_region(c, rbox)
            print(f"{c['key']} {reg}: {len(rbox['chunk_keys'])} chunks read ({n_missing} absent = all fill) "
                  f"in {time.monotonic() - t0:.0f} s", flush=True)
            months = sorted(set(np.asarray(ds["time"].values).astype("datetime64[M]").astype(str)))
            if not set(months) <= {m.strftime("%Y-%m") for m in MONTHS}:
                raise FetchGuardError(f"{c['key']} {reg}: months outside the window returned")
            for z in todo:
                mpath = OUT / "membership" / z["membership"]
                if estimate.file_sha256(mpath) != z["membership_sha256"]:
                    raise FetchGuardError(f"{mpath.name} changed since the request list was approved")
                mem = read_membership(mpath)
                sub = crop_to_cells(ds, z["bbox_w_s_e_n"], step_lat, step_lon)
                zone = {"region_id": z["region_id"], "subregion_id": z["subregion_id"], "geometry_version": z["geometry_version"]}
                rows = []
                for r in process.aggregate_copernicus(sub, mem, zone, c["key"], c["dataset_id"]):
                    if r["variable"] in ("current_speed", "current_steadiness"):
                        continue                    # decided: monthly mean vector only
                    r["month"] = r.pop("date")[:7] + "-01"
                    rows.append(r)
                rows += vector_speed(sub, mem, zone, c)
                got = {r["month"] for r in rows}
                for month in MONTHS:                # months the product lacks: empty, flagged
                    if month.isoformat() not in got:
                        for v in c["variables"]:
                            rows.append(month_row(month, zone, c["key"], v, "", EMPTY, len(mem), c["key"],
                                                  c["dataset_id"], "missing_at_source"))
                print(f"{c['key']} {zkey(z)}: {write_rows(rows, outs[zkey(z)])} rows",
                      flush=True)
            return f"{c['key']} {reg} done in {time.monotonic() - t0:.0f} s"

    jobs = []
    for c in doc["copernicus"]:
        for reg, rbox in c["regions"].items():
            zones = [z for z in c["zones"] if z["region_id"] == reg and (not zone_filter or zkey(z) == zone_filter)]
            outs = {zkey(z): zone_out(c["key"], reg, z["subregion_id"]) for z in zones}
            todo = [z for z in zones if outs[zkey(z)] is not None]
            if todo:
                jobs.append((c, reg, rbox, todo, outs))
    print(f"copernicus: {len(jobs)} dataset x region jobs, {COPERNICUS_WORKERS} at a time", flush=True)
    with ThreadPoolExecutor(COPERNICUS_WORKERS) as pool:
        for f in as_completed([pool.submit(one_region, *j) for j in jobs]):
            print(f.result(), flush=True)


_cm_client = MetadataClient(timeout=120.0, retries=6)


def read_region(c: dict, rbox: dict):
    """Copernicus ARCO geoChunked Zarr, read directly: only the chunk keys listed in requests.json.
    Absent keys (HTTP 403/404 on the public bucket) are chunks Zarr never wrote because they are all fill."""
    import numcodecs
    import xarray as xr
    host = urllib.parse.urlsplit(c["store"]).hostname
    (i0, i1), (j0, j1) = rbox["lat_index"], rbox["lon_index"]
    t0, t1 = c["time_index"]
    z = c["depth_index"]
    nt, ny, nx = t1 - t0 + 1, i1 - i0 + 1, j1 - j0 + 1
    out, missing = {}, 0
    for v, vm in c["var_meta"].items():
        ct, cz, cy, cx = vm["chunks"]
        codec = numcodecs.get_codec(vm["compressor"]) if vm["compressor"] else None
        raw_arr = np.full((nt, ny, nx), np.nan)
        for key in (k for k in rbox["chunk_keys"] if k.startswith(v + "/")):
            if urllib.parse.urlsplit(f"{c['store']}/{key}").hostname != host:
                raise FetchGuardError(key)
            ti, zi, yi, xi = (int(x) for x in key.split("/")[1].split("."))
            if zi != z // cz:
                raise FetchGuardError(f"{key}: not the surface depth chunk")
            r = _cm_client.request("GET", f"{c['store']}/{key}")
            if r.status in (403, 404):
                missing += 1
                continue
            if r.status != 200:
                raise FetchError(f"{key}: HTTP {r.status}")
            body = codec.decode(r.body) if codec else r.body
            a = np.frombuffer(body, dtype=np.dtype(vm["dtype"])).reshape(vm["chunks"])[:, z % cz].astype(float)
            fills = [x for x in (vm.get("fill_value"), vm.get("_FillValue"), vm.get("missing_value")) if x is not None]
            for fv in fills:
                a[np.isclose(a, float(fv), rtol=0, atol=abs(float(fv)) * 1e-6 + 1e-12)] = np.nan
            a = a * float(vm.get("scale_factor", 1.0)) + float(vm.get("add_offset", 0.0))
            # global index ranges of this chunk, intersected with the wanted window
            gt, gy, gx = ti * ct, yi * cy, xi * cx
            ts, te = max(gt, t0), min(gt + ct, t1 + 1)
            ys, ye = max(gy, i0), min(gy + cy, i1 + 1)
            xs, xe = max(gx, j0), min(gx + cx, j1 + 1)
            if ts < te and ys < ye and xs < xe:
                raw_arr[ts - t0:te - t0, ys - i0:ye - i0, xs - j0:xe - j0] = a[ts - gt:te - gt, ys - gy:ye - gy, xs - gx:xe - gx]
        out[v] = (("time", "latitude", "longitude"), raw_arr, {"units": vm["units"]})
    times = np.array([np.datetime64(t[:10]) for t in c["times"]])
    ds = xr.Dataset(out, coords={"time": times, "latitude": np.array(rbox["lat"]), "longitude": np.array(rbox["lon"])})
    return ds, missing


def vector_speed(sub, mem, zone, c) -> list[dict]:
    """|weighted mean (u, v)| per month: magnitude of the mean flow, NOT the mean speed."""
    if "uo" not in sub.data_vars:
        return []
    lat_ix = {round(float(x), 4): i for i, x in enumerate(sub["latitude"].values)}
    lon_ix = {round(float(x), 4): j for j, x in enumerate(sub["longitude"].values)}
    sea = [m for m in mem if m.get("sea") in (True, "True", "true", 1, "1")]
    keep = [(lat_ix.get(round(float(m["lat"]), 4)), lon_ix.get(round(float(m["lon"]), 4)), float(m["overlap_fraction"]))
            for m in sea]
    keep = [k for k in keep if k[0] is not None and k[1] is not None]
    times = np.asarray(sub["time"].values).astype("datetime64[M]").astype(str)
    u = np.asarray(sub["uo"].values, float).reshape(len(times), sub.sizes["latitude"], sub.sizes["longitude"])
    v = np.asarray(sub["vo"].values, float).reshape(len(times), sub.sizes["latitude"], sub.sizes["longitude"])
    rows = []
    for t, ym in enumerate(times):
        uu = np.array([u[t, i, j] for i, j, _ in keep])
        vv = np.array([v[t, i, j] for i, j, _ in keep])
        w = np.array([f for _, _, f in keep])
        ok = np.isfinite(uu) & np.isfinite(vv) & (w > 0) if keep else np.array([], bool)
        st = dict(EMPTY)
        if ok.any():
            mu, mv = np.sum(uu[ok] * w[ok]) / w[ok].sum(), np.sum(vv[ok] * w[ok]) / w[ok].sum()
            st = {"valid_pixel_count": int(ok.sum()), "mean": round(float(np.hypot(mu, mv)), 6),
                  "min": None, "max": None, "std": None}
        rows.append(month_row(dt.date.fromisoformat(ym + "-01"), zone, c["key"], "current_vector_speed",
                              sub["uo"].attrs.get("units", "m s-1"), st, len(mem), c["key"], c["dataset_id"],
                              f"sea_cells={len(keep)};derived_from=uo,vo;magnitude_of_monthly_mean_vector"))
    return rows


def fetch_power(doc: dict, zone_filter, budget) -> None:
    from seagis_extractor import power
    urls = {z["url"] for z in doc["power"]["zones"]}
    pc = power.PowerClient(urls)
    for z in doc["power"]["zones"]:
        if zone_filter and zkey(z) != zone_filter:
            continue
        out = zone_out("nasa_power_monthly", z["region_id"], z["subregion_id"])
        if out is None:
            continue
        resp = pc.get(z["url"])
        coords = ((resp.get("geometry") or {}).get("coordinates") or [])[:2]
        if len(coords) != 2 or abs(coords[0] - z["lon"]) > 1e-3 or abs(coords[1] - z["lat"]) > 1e-3:
            raise FetchGuardError(f"POWER answered for {coords}, requested {z['lon']},{z['lat']}")
        got = (resp.get("properties") or {}).get("parameter") or {}
        if set(got) != set(POWER_PARAMS):
            raise FetchGuardError(f"POWER parameters {sorted(got)}")
        hdr = resp.get("header") or {}
        fill = float(hdr.get("fill_value", -999.0))
        units = {p: ((resp.get("parameters") or {}).get(p) or {}).get("units") or "" for p in POWER_PARAMS}
        version = "POWER " + str((hdr.get("api") or {}).get("version") or "").strip()
        zone = {k: z[k] for k in ("region_id", "subregion_id", "geometry_version")}
        qc = f"point={z['lat']},{z['lon']};sources={','.join(hdr.get('sources') or [])}"
        rows = []
        for p in POWER_PARAMS:
            series = got[p]
            for month in MONTHS:
                v = series.get(month.strftime("%Y%m"))
                ok = v is not None and float(v) != fill
                val = round(float(v), 6) if ok else None
                st = {"valid_pixel_count": int(ok), "mean": val, "min": val, "max": val, "std": None}
                rows.append(month_row(month, zone, "nasa_power_monthly", p, units[p], st, 1,
                                      f"POWER monthly point {z['lat']},{z['lon']}", version,
                                      qc + ("" if ok else (";fill" if v is not None else ";missing_at_source")),
                                      weighted=False))
        print(f"power {zkey(z)}: {write_rows(rows, out)} rows")


def cmd_fetch(args) -> int:
    doc = load_approved(args.approve, Path(args.requests))
    print(f"window {START}..{END} ({len(MONTHS)} months) from {Path(args.requests).name}", flush=True)
    auth.apply_env(ROOT / ".env")
    budget = ByteBudget(int(2e9))
    fns = {"power": fetch_power, "copernicus": fetch_copernicus, "mur": fetch_mur, "imerg": fetch_imerg}
    workers = {"mur": args.workers or 3, "imerg": args.workers or 4}
    for name in ([args.source] if args.source else ["power", "copernicus", "mur", "imerg"]):
        t0 = time.monotonic()
        if name in workers:
            fns[name](doc, args.zone, budget, workers[name])
        else:
            fns[name](doc, args.zone, budget)
        print(f"== {name} done in {time.monotonic() - t0:.0f} s; downloaded so far {budget.used / 1e6:.1f} MB")
    return 0


# ---------------------------------------------------------------- export

def cmd_export(args) -> int:
    import pandas as pd
    import psycopg
    set_window(dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end))
    docs = [json.loads(Path(p).read_text()) for p in args.requests]
    shas = sorted(d["sha256"] for d in docs)
    run_sha = shas[0] if len(shas) == 1 else canonical_sha(shas)   # several approved lists -> hash of their hashes
    files = sorted(PROCESSED.rglob("*.parquet"))
    if not files:
        raise SystemExit("nothing in data/processed_monthly")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    before = len(df)
    df["month"] = df["month"].astype(str).str[:10]
    df = df[(df["month"] >= START.isoformat()) & (df["month"] <= END.isoformat())].copy()   # files fetched for 2003-2024 too
    print(f"window {START}..{END}: kept {len(df)} of {before} rows")
    key0 = ["region_id", "subregion_id", "geometry_version", "dataset", "variable", "month"]
    nd = int(df.duplicated(key0).sum())
    if nd:      # the same month in two files (e.g. a 2003-2024 file and a later 2003-2014 one): keep the first
        df = df.drop_duplicates(key0, keep="first")
        print(f"dropped {nd} rows present in two files")
    per = df.groupby(["dataset", "variable", "region_id", "subregion_id"])["month"].nunique()
    short = per[per < len(MONTHS)].groupby(["dataset", "variable"]).size()
    if len(short):
        print(f"WARNING: zones with fewer than {len(MONTHS)} months (dataset, variable: zones):\n{short.to_string()}")
        if not args.allow_gaps and not args.dry_run:
            raise SystemExit("not exporting a window some zones do not fully cover; fetch the rest, or pass --allow-gaps")
    zones = df.groupby("dataset")[["region_id", "subregion_id"]].apply(lambda g: len(g.drop_duplicates()))
    print("zones per dataset: " + ", ".join(f"{k} {v}" for k, v in zones.items()))
    n_zones = len(daily_plan()["rois"])
    few = {k: v for k, v in zones.items() if v < n_zones}
    if few:
        print(f"WARNING: datasets with fewer than {n_zones} zones: {few}")
        if not args.allow_gaps and not args.dry_run:
            raise SystemExit("not exporting while zones are missing; fetch the rest, or pass --allow-gaps")
    if args.dataset:    # load one dataset at a time on a slow link; the checks above still ran on all of them
        df = df[df["dataset"].isin(args.dataset)].copy()
        print(f"--dataset {' '.join(args.dataset)}: {len(df)} rows")
    df["units"] = [export.display_unit(v, u) if u else "" for v, u in zip(df["variable"], df["units"])]
    # monthly table has no data_type column: every monthly row is observation/reanalysis, never forecast
    cols = [c if c != "date" else "month" for c in export.METRIC_COLUMNS if c != "data_type"]
    df = df[cols]
    key = [c if c != "date" else "month" for c in export.METRIC_KEY if c != "data_type"]
    dup = df.duplicated(key).sum()
    if dup:
        raise SystemExit(f"{dup} duplicate keys")
    print(f"{len(df)} rows from {len(files)} files; datasets:")
    print(df.groupby(["dataset", "variable", "units"]).size().to_string())
    auth.apply_env(ROOT / ".env")
    dsn = export.dsn_from_env()
    if export.dsn_host(dsn) != args.confirm_host:
        raise SystemExit(f"--confirm-host {args.confirm_host} does not match the DSN host; nothing written")
    if args.dry_run:
        print("dry run: nothing written")
        return 0
    mig = ROOT.parents[1] / "supabase/migrations" / MIGRATION
    with psycopg.connect(dsn) as conn, conn.transaction(), conn.cursor() as cur:
        # Supabase's role default timeout stops a ~100k-row COPY over the pooler; this transaction only
        cur.execute("set local statement_timeout = '60min'")
        cur.execute(f"select 1 from public.{export.MIGRATIONS_TABLE} where name = %s", (MIGRATION,))
        if not cur.fetchone():
            cur.execute(mig.read_text())
            cur.execute(f"insert into public.{export.MIGRATIONS_TABLE} (name) values (%s)", (MIGRATION,))
            print(f"applied migration {MIGRATION}")
        cur.execute("insert into public.seagis_load_runs (plan_sha256, period_start, period_end, files, tool_version, notes) "
                    "values (%s, %s, %s, %s, %s, %s) returning run_id",
                    (run_sha, START, END, len(files), "scripts/monthly.py",
                     "monthly long-term load; approved request lists: " + ", ".join(shas)))
        run_id = cur.fetchone()[0]
        cur.execute("create temp table _m (like public.seagis_monthly_metrics including defaults) on commit drop")
        allc = cols + ["plan_sha256", "load_run_id"]
        with cur.copy(f"copy _m ({', '.join(allc)}) from stdin") as cp:
            for rec in df.itertuples(index=False):
                cp.write_row([None if (x is None or (isinstance(x, float) and np.isnan(x))) else
                              (x.item() if hasattr(x, "item") else x) for x in rec] + [run_sha, run_id])
        upd = [c for c in allc if c not in key]
        cur.execute(f"insert into public.seagis_monthly_metrics ({', '.join(allc)}) select {', '.join(allc)} from _m "
                    f"on conflict ({', '.join(key)}) do update set " + ", ".join(f"{c} = excluded.{c}" for c in upd)
                    + ", loaded_at = now()")
        cur.execute("update public.seagis_load_runs set finished_at = now(), rows_upserted = %s where run_id = %s",
                    (len(df), run_id))
        cur.execute("select count(*) from public.seagis_monthly_metrics")
        print(f"run {run_id}: {len(df)} rows upserted, {cur.fetchone()[0]} in seagis_monthly_metrics")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    li = sub.add_parser("list")
    li.add_argument("--start", default=START.isoformat(), help="first month, YYYY-MM-01 (default %(default)s)")
    li.add_argument("--end", default=END.isoformat(), help="last day, YYYY-MM-DD (default %(default)s)")
    li.add_argument("--out", help=f"request list path (default {REQUESTS.relative_to(ROOT)})")
    f = sub.add_parser("fetch")
    f.add_argument("--approve", required=True)
    f.add_argument("--requests", default=str(REQUESTS), help="approved request list (default %(default)s)")
    f.add_argument("--source", choices=["mur", "imerg", "copernicus", "power"])
    f.add_argument("--zone", help="REGION/subregion, e.g. PH-TAWI/bongao")
    f.add_argument("--workers", type=int, help="zones in parallel for mur (default 3) and imerg (default 4)")
    e = sub.add_parser("export")
    e.add_argument("--confirm-host", required=True)
    e.add_argument("--dry-run", action="store_true")
    e.add_argument("--allow-gaps", action="store_true", help="export even if some zones miss months of the window")
    e.add_argument("--dataset", nargs="+", help="load only these datasets (each run is its own transaction)")
    e.add_argument("--start", default=START.isoformat(), help="window start written to the DB (default %(default)s)")
    e.add_argument("--end", default=END.isoformat(), help="window end (default %(default)s)")
    e.add_argument("--requests", nargs="+", default=[str(REQUESTS)], help="approved request list(s) behind the files")
    a = ap.parse_args(argv)
    return {"list": cmd_list, "fetch": cmd_fetch, "export": cmd_export}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
