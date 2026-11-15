"""Long-term MONTHLY zone values, 2003-01 .. 2024-12 (decided 2026-11-15, docs/Calzy/LONG_TERM_DATA.md).

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

START, END = dt.date(2003, 1, 1), dt.date(2024, 12, 31)
MONTHS = [dt.date(y, m, 1) for y in range(START.year, END.year + 1) for m in range(1, 13)]
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
    with gzip.open(path, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]) if table else ["lat_index"])
        w.writeheader()
        w.writerows(table)


# ---------------------------------------------------------------- list (metadata only)

def erddap_url(req: dict) -> str:
    (i0, i1), (j0, j1) = req["grid_index_range"]["lat"], req["grid_index_range"]["lon"]
    lat = lambda i: f"{MUR_GRID.lat(i):.2f}"  # noqa: E731
    lon = lambda j: f"{MUR_GRID.lon(j):.2f}"  # noqa: E731
    t = "[(2003-01-01T00:00:00Z):1:(2024-12-31T00:00:00Z)]"
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
    for reg, box in boxes.items():
        rc = copernicus.roi_chunks(ds, box)
        regions[reg] = {"bbox_w_s_e_n": box, "chunks": len(rc["keys"]), "cells": rc["cells"]}
    return {"key": spec["key"], "product_id": spec["product_id"], "dataset_id": spec["dataset_id"],
            "variables": spec["variables"], "depth_m": abs(ds["depth"]["elevation_m"]),
            "grid": ds["grid"], "time_extent": ds["time_extent"],
            "months_available": len(months), "missing_months": sorted({m.strftime("%Y-%m") for m in MONTHS} - set(months)),
            "static_mask": spec["static"], "regions": regions, "zones": zones,
            "zones_without_sea": [zkey(z) for z in zones if z["sea_cells"] == 0]}


def cmd_list(_args) -> int:
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
    im = {"dataset": "gpm_imerg_monthly", "collection": IMERGM, "variables": ["precipitation"],
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
            "decisions": ["window 2003-01..2024-12 for every source",
                          "missing months kept as empty rows flagged missing_at_source",
                          "currents: monthly mean vector only (uo, vo, current_direction, current_vector_speed)",
                          "storage: public.seagis_monthly_metrics"]}
    doc = {"sha256": canonical_sha(body), "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), **body}
    REQUESTS.write_text(json.dumps(doc, indent=1))
    n_req = sum(len(z["requests"]) for z in mur["zones"]) + sum(len(z["requests"]) for z in im["zones"]) \
        + len(pw["zones"]) + sum(len(c["regions"]) for c in cm)
    print(f"wrote {REQUESTS.relative_to(ROOT)}")
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

def load_approved(sha: str) -> dict:
    doc = json.loads(REQUESTS.read_text())
    body = {k: v for k, v in doc.items() if k not in ("sha256", "generated_at")}
    if canonical_sha(body) != doc["sha256"] or doc["sha256"] != sha:
        raise SystemExit(f"requests.json hash {canonical_sha(body)} is not the approved {sha}; nothing fetched")
    return doc


def _done(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


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


def fetch_mur(doc: dict, zone_filter, budget) -> None:
    import xarray as xr
    src = doc["mur"]
    missing = set(src["missing_months"])
    for z in src["zones"]:
        if zone_filter and zkey(z) != zone_filter:
            continue
        out = PROCESSED / "mur_sst_monthly" / z["region_id"] / f"{z['subregion_id']}.parquet"
        if _done(out):
            continue
        mpath = ROOT / "outputs/membership" / z["membership"]
        if estimate.file_sha256(mpath) != z["membership_sha256"]:
            raise FetchGuardError(f"{mpath.name} changed since the request list was approved")
        mem = read_membership(mpath)
        tiles = []
        with tempfile.TemporaryDirectory() as td:
            for i, q in enumerate(z["requests"]):
                p = Path(td) / f"t{i}.nc"
                _download(q["url"], p, budget, ERDDAP_HOST)
                ds = xr.open_dataset(p).load()
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
                if ym in missing or len(day) != len(tiles):
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
        print(f"mur {zkey(z)}: {write_rows(rows, out)} rows")


def _granule_month(name: str) -> dt.date | None:
    m = re.search(r"\.(\d{4})(\d{2})01-S", name)
    return dt.date(int(m.group(1)), int(m.group(2)), 1) if m else None


def fetch_imerg(doc: dict, zone_filter, budget) -> None:
    import xarray as xr
    src = doc["imerg"]
    grid = imerg.ImergGrid()
    allowed = {tuple(q["bbox_w_s_e_n"]) for z in src["zones"] for q in z["requests"]}
    hc = HarmonyClient(auth.earthdata_token(), allowed, budget, max_polls=720)
    for z in src["zones"]:
        if zone_filter and zkey(z) != zone_filter:
            continue
        out = PROCESSED / "gpm_imerg_monthly" / z["region_id"] / f"{z['subregion_id']}.parquet"
        if _done(out):
            continue
        mpath = ROOT / "outputs/membership" / z["membership"]
        if estimate.file_sha256(mpath) != z["membership_sha256"]:
            raise FetchGuardError(f"{mpath.name} changed since the request list was approved")
        mem = read_membership(mpath)
        per_month: dict = {}
        with tempfile.TemporaryDirectory() as td:
            for i, q in enumerate(z["requests"]):
                job = hc.wait(hc.submit(IMERGM["concept_id"], ["precipitation"], q["bbox_w_s_e_n"], START, END))
                for link in hc.data_links(job):
                    name = Path(urllib.parse.urlsplit(link["href"]).path).name
                    month = _granule_month(name)
                    if month is None or month not in MONTHS:
                        raise FetchGuardError(f"unexpected granule {name}")
                    p = Path(td) / f"t{i}_{name}"
                    hc.download(link["href"], p)
                    ds = xr.open_dataset(p, decode_times=False).load()
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
        print(f"imerg {zkey(z)}: {write_rows(rows, out)} rows")


def fetch_copernicus(doc: dict, zone_filter, _budget) -> None:
    import copernicusmarine
    if not auth.copernicus_configured():
        raise auth.AuthError("Copernicus Marine credentials not found")
    for c in doc["copernicus"]:
        step_lat, step_lon = c["grid"]["lat_step"], c["grid"]["lon_step"]
        base, _, ver = c["dataset_id"].rpartition("_")
        for reg, rbox in c["regions"].items():
            zones = [z for z in c["zones"] if z["region_id"] == reg and (not zone_filter or zkey(z) == zone_filter)]
            todo = [z for z in zones if not _done(PROCESSED / c["key"] / reg / f"{z['subregion_id']}.parquet")]
            if not todo:
                continue
            from seagis_extractor.fetch import crop_to_cells
            w, s, e, n = rbox["bbox_w_s_e_n"]
            ds = copernicusmarine.open_dataset(
                dataset_id=base, dataset_version=ver, variables=c["variables"],
                minimum_longitude=w, maximum_longitude=e, minimum_latitude=s, maximum_latitude=n,
                minimum_depth=c["depth_m"] - 0.01, maximum_depth=c["depth_m"] + 0.01,
                start_datetime=f"{START}T00:00:00", end_datetime=f"{END}T23:59:59",
                coordinates_selection_method="outside", service="arco-geo-series")
            validate.copernicus_guard(ds, rbox["bbox_w_s_e_n"], step_lat, step_lon)
            ds = crop_to_cells(ds, rbox["bbox_w_s_e_n"], step_lat, step_lon).load()
            if "depth" in ds.dims:
                if ds.sizes["depth"] != 1:
                    raise FetchError(f"{c['key']} {reg}: {ds.sizes['depth']} depth levels returned")
                ds = ds.isel(depth=0)
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
                print(f"{c['key']} {zkey(z)}: {write_rows(rows, PROCESSED / c['key'] / reg / (z['subregion_id'] + '.parquet'))} rows")


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
        out = PROCESSED / "nasa_power_monthly" / z["region_id"] / f"{z['subregion_id']}.parquet"
        if _done(out):
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
    doc = load_approved(args.approve)
    auth.apply_env(ROOT / ".env")
    budget = ByteBudget(int(2e9))
    fns = {"power": fetch_power, "copernicus": fetch_copernicus, "mur": fetch_mur, "imerg": fetch_imerg}
    for name in ([args.source] if args.source else ["power", "copernicus", "mur", "imerg"]):
        t0 = time.monotonic()
        fns[name](doc, args.zone, budget)
        print(f"== {name} done in {time.monotonic() - t0:.0f} s; downloaded so far {budget.used / 1e6:.1f} MB")
    return 0


# ---------------------------------------------------------------- export

def cmd_export(args) -> int:
    import pandas as pd
    import psycopg
    doc = json.loads(REQUESTS.read_text())
    files = sorted(PROCESSED.rglob("*.parquet"))
    if not files:
        raise SystemExit("nothing in data/processed_monthly")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["units"] = [export.display_unit(v, u) if u else "" for v, u in zip(df["variable"], df["units"])]
    cols = [c if c != "date" else "month" for c in export.METRIC_COLUMNS]
    df = df[cols]
    dup = df.duplicated([c if c != "date" else "month" for c in export.METRIC_KEY]).sum()
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
    key = [c if c != "date" else "month" for c in export.METRIC_KEY]
    with psycopg.connect(dsn) as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute(f"select 1 from public.{export.MIGRATIONS_TABLE} where name = %s", (MIGRATION,))
        if not cur.fetchone():
            cur.execute(mig.read_text())
            cur.execute(f"insert into public.{export.MIGRATIONS_TABLE} (name) values (%s)", (MIGRATION,))
            print(f"applied migration {MIGRATION}")
        cur.execute("insert into public.seagis_load_runs (plan_sha256, period_start, period_end, files, tool_version, notes) "
                    "values (%s, %s, %s, %s, %s, %s) returning run_id",
                    (doc["sha256"], START, END, len(files), "scripts/monthly.py", "monthly long-term load"))
        run_id = cur.fetchone()[0]
        cur.execute("create temp table _m (like public.seagis_monthly_metrics including defaults) on commit drop")
        allc = cols + ["plan_sha256", "load_run_id"]
        with cur.copy(f"copy _m ({', '.join(allc)}) from stdin") as cp:
            for rec in df.itertuples(index=False):
                cp.write_row([None if (x is None or (isinstance(x, float) and np.isnan(x))) else
                              (x.item() if hasattr(x, "item") else x) for x in rec] + [doc["sha256"], run_id])
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
    sub.add_parser("list")
    f = sub.add_parser("fetch")
    f.add_argument("--approve", required=True)
    f.add_argument("--source", choices=["mur", "imerg", "copernicus", "power"])
    f.add_argument("--zone", help="REGION/subregion, e.g. PH-TAWI/bongao")
    e = sub.add_parser("export")
    e.add_argument("--confirm-host", required=True)
    e.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    return {"list": cmd_list, "fetch": cmd_fetch, "export": cmd_export}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
