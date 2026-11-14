"""Copernicus Marine (CMEMS) ANFC datasets: catalog + exact transfer size from ARCO Zarr chunks.

Metadata only:
- STAC dataset descriptions (public) give dimensions, variables, and the ARCO asset URLs.
- Zarr `.zmetadata` gives shape, chunking, dtype, compressor.
- Coordinate arrays (latitude/longitude/time/elevation; a few KB) map ROI boxes to indices.
- One HEAD per data chunk returns its compressed size (Content-Length). No chunk body is read.

A subset read through the ARCO "geoChunked" store downloads every chunk that intersects the
request, so the sum of those chunks' Content-Length is the true transfer size.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import numcodecs
import numpy as np

from .http import MetadataClient

STAC = "https://stac.marine.copernicus.eu/metadata"
EPOCH_1950 = dt.datetime(1950, 1, 1)


def dataset_stac(client: MetadataClient, product_id: str, dataset_id: str) -> dict:
    _, d = client.get_json(f"{STAC}/{product_id}/{dataset_id}/dataset.stac.json")
    return d


def zarr_metadata(client: MetadataClient, store: str) -> dict:
    _, d = client.get_json(f"{store}/.zmetadata")
    return d["metadata"]


def read_coord(client: MetadataClient, store: str, name: str, meta: dict) -> np.ndarray:
    """Decode a 1-chunk coordinate array (small; this is metadata, not science data)."""
    za = meta[f"{name}/.zarray"]
    if len(za["chunks"]) != 1:
        raise ValueError(f"{name} is not 1-D")
    n, c = za["shape"][0], za["chunks"][0]
    parts = []
    for k in range(math.ceil(n / c)):
        resp = client.request("GET", f"{store}/{name}/{k}")
        if resp.status != 200:
            raise RuntimeError(f"coordinate {name}/{k}: HTTP {resp.status}")
        raw = numcodecs.get_codec(za["compressor"]).decode(resp.body) if za.get("compressor") else resp.body
        parts.append(np.frombuffer(raw, dtype=np.dtype(za["dtype"])))
    return np.concatenate(parts)[:n]


def index_range(coord: np.ndarray, lo: float, hi: float) -> tuple[int, int]:
    """Indices of cells whose extent (centre ± half step) intersects [lo, hi]; coord ascending."""
    step = float(np.median(np.diff(coord)))
    sel = np.nonzero((coord + step / 2 >= lo) & (coord - step / 2 <= hi))[0]
    if not len(sel):
        raise ValueError(f"no grid cells in [{lo}, {hi}]")
    return int(sel[0]), int(sel[-1])


def resolve_dataset(client: MetadataClient, spec: dict, start: dt.date, end: dt.date) -> dict:
    stac = dataset_stac(client, spec["product_id"], spec["dataset_id"])
    props = stac["properties"]
    store = stac["assets"]["geoChunked"]["href"]
    meta = zarr_metadata(client, store)
    lat = read_coord(client, store, "latitude", meta)
    lon = read_coord(client, store, "longitude", meta)
    time = read_coord(client, store, "time", meta)
    elev = read_coord(client, store, "elevation", meta)
    tunits = meta["time/.zattrs"]["units"]
    if tunits != "hours since 1950-01-01":
        raise ValueError(f"unexpected time units {tunits}")
    dates = [(EPOCH_1950 + dt.timedelta(hours=float(h))) for h in time]
    tsel = [i for i, d in enumerate(dates) if start <= d.date() <= end]
    if not np.all(np.diff(lat) > 0) or not np.all(np.diff(lon) > 0):
        raise ValueError("latitude/longitude not ascending")
    z = int(np.argmax(elev)) if spec.get("depth", "surface") == "surface" else None
    variables = {}
    for v in spec["variables"]:
        za, at = meta[f"{v}/.zarray"], meta.get(f"{v}/.zattrs", {})
        variables[v] = {"shape": za["shape"], "chunks": za["chunks"], "dtype": za["dtype"],
                        "compressor": za.get("compressor"), "fill_value": za.get("fill_value"),
                        "units": at.get("units"), "standard_name": at.get("standard_name"),
                        "valid_min": at.get("valid_min"), "valid_max": at.get("valid_max")}
    present = {d.date() for d in dates}
    want = [start + dt.timedelta(n) for n in range((end - start).days + 1)]
    return {
        "key": spec["key"], "product_id": spec["product_id"], "dataset_id": spec["dataset_id"],
        "title": stac.get("properties", {}).get("title") or stac.get("title"),
        "store": store, "time_extent": [props.get("start_datetime"), props.get("end_datetime")],
        "time_hour_utc": sorted({d.hour for d in dates}),
        "grid": {"lat": [float(lat[0]), float(lat[-1]), len(lat)], "lon": [float(lon[0]), float(lon[-1]), len(lon)],
                 "lat_step": float(np.median(np.diff(lat))), "lon_step": float(np.median(np.diff(lon)))},
        "depth": {"mode": spec.get("depth", "surface"), "index": z, "elevation_m": float(elev[z]) if z is not None else None,
                  "levels": len(elev)},
        "variables": variables,
        "requested_days": len(want), "available_days": sum(1 for d in want if d in present),
        "missing_dates": [d.isoformat() for d in want if d not in present],
        "_lat": lat, "_lon": lon, "_tsel": tsel, "_tdates": {i: dates[i].date() for i in tsel},
    }


def roi_chunks(ds: dict, bbox: list[float]) -> dict:
    """Chunk keys (per variable) a geoChunked subset of `bbox` at the chosen depth must download."""
    w, s, e, n = bbox
    i0, i1 = index_range(ds["_lat"], s, n)
    j0, j1 = index_range(ds["_lon"], w, e)
    keys = set()
    tsel = ds["_tsel"]
    for v, meta in ds["variables"].items():
        ct, cz, cy, cx = meta["chunks"]
        tch = sorted({t // ct for t in tsel})
        zch = [ds["depth"]["index"] // cz] if ds["depth"]["index"] is not None else range(math.ceil(meta["shape"][1] / cz))
        for t in tch:
            for zc in zch:
                for y in range(i0 // cy, i1 // cy + 1):
                    for x in range(j0 // cx, j1 // cx + 1):
                        keys.add(f"{v}/{t}.{zc}.{y}.{x}")
    cells = (i1 - i0 + 1) * (j1 - j0 + 1)
    return {"lat_index": [i0, i1], "lon_index": [j0, j1], "cells": cells, "keys": keys,
            "uncompressed_bytes": cells * len(tsel) * 4 * len(ds["variables"])}


def head_sizes(client: MetadataClient, store: str, keys: set[str], workers: int = 8) -> dict[str, int | None]:
    def one(k):
        r = client.request("HEAD", f"{store}/{k}")
        if r.status == 200 and r.header("Content-Length"):
            return k, int(r.header("Content-Length"))
        if r.status == 404:  # Zarr: missing chunk = all fill, nothing to transfer
            return k, 0
        return k, None
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return dict(ex.map(one, sorted(keys)))


def size_report(client: MetadataClient, datasets: list[dict], rois: list[dict]) -> dict:
    """Exact transfer per dataset x ROI (naive) and per dataset (unique chunks)."""
    out = {"datasets": [], "head_requests": 0}
    for ds in datasets:
        per_roi, all_keys = [], set()
        for roi in rois:
            rc = roi_chunks(ds, roi["request"]["bbox_w_s_e_n"])
            per_roi.append((roi, rc))
            all_keys |= rc["keys"]
        sizes = head_sizes(client, ds["store"], all_keys)
        out["head_requests"] += len(sizes)
        unknown = [k for k, v in sizes.items() if v is None]
        rows = []
        for roi, rc in per_roi:
            b = [sizes[k] for k in rc["keys"]]
            rows.append({"region_id": roi["region_id"], "subregion_id": roi["subregion_id"],
                         "lat_index": rc["lat_index"], "lon_index": rc["lon_index"], "cells": rc["cells"],
                         "chunks": len(rc["keys"]),
                         "transfer_bytes": None if any(x is None for x in b) else sum(b),
                         "uncompressed_subset_bytes": rc["uncompressed_bytes"]})
        known = [v for v in sizes.values() if v is not None]
        by_region = defaultdict(set)
        for roi, rc in per_roi:
            by_region[roi["region_id"]] |= rc["keys"]
        out["datasets"].append({
            "key": ds["key"], "dataset_id": ds["dataset_id"], "variables": list(ds["variables"]),
            "depth": ds["depth"], "grid": ds["grid"], "available_days": ds["available_days"],
            "requested_days": ds["requested_days"], "missing_dates": ds["missing_dates"],
            "unique_chunks": len(sizes), "unknown_chunks": unknown,
            "transfer_bytes_unique": None if unknown else sum(known),
            "transfer_bytes_by_region_unique": {r: (None if any(sizes[k] is None for k in ks) else sum(sizes[k] for k in ks))
                                                for r, ks in by_region.items()},
            "per_roi": rows,
        })
    return out


def public(ds: dict) -> dict:
    """Drop the private numpy helpers before serialising."""
    return {k: v for k, v in ds.items() if not k.startswith("_")}


# ---------------------------------------------------------------- static land/sea mask

class SeaMask:
    """Surface land/sea mask (1 = sea, 0 = land) of a model grid, from its public static Zarr store.

    Only the chunks covering the region boxes are fetched (tens of KB), cached on disk with SHA-256.
    The mask grid must equal the data grid exactly, otherwise indices would not line up.
    """

    def __init__(self, client: MetadataClient, product_id: str, dataset_id: str, ds: dict,
                 boxes: dict[str, list[float]], cache_dir: Path):
        stac = dataset_stac(client, product_id, dataset_id)
        store = stac["assets"]["static"]["href"]
        meta = zarr_metadata(client, store)
        lat, lon = read_coord(client, store, "latitude", meta), read_coord(client, store, "longitude", meta)
        elev = read_coord(client, store, "elevation", meta)
        if lat.shape != ds["_lat"].shape or lon.shape != ds["_lon"].shape or not (
                np.allclose(lat, ds["_lat"], atol=1e-4) and np.allclose(lon, ds["_lon"], atol=1e-4)):
            raise ValueError(f"{dataset_id}: mask grid differs from data grid {ds['dataset_id']}")
        z = int(np.argmax(elev))
        if ds["depth"]["index"] is not None and z != ds["depth"]["index"]:
            raise ValueError(f"{dataset_id}: surface level {z} != data surface {ds['depth']['index']}")
        za = meta["mask/.zarray"]
        self.chunks_shape = za["chunks"]
        self.codec = numcodecs.get_codec(za["compressor"]) if za.get("compressor") else None
        self.dtype = np.dtype(za["dtype"])
        self.z = z
        cz, cy, cx = self.chunks_shape
        keys = set()
        for w, s, e, n in boxes.values():
            i0, i1 = index_range(lat, s, n)
            j0, j1 = index_range(lon, w, e)
            keys |= {f"mask/{z // cz}.{y}.{x}" for y in range(i0 // cy, i1 // cy + 1)
                     for x in range(j0 // cx, j1 // cx + 1)}
        self.arrays, self.files = {}, []
        for k in sorted(keys):
            path = Path(cache_dir) / dataset_id / k.replace("/", "__")
            if not path.exists():
                r = client.request("GET", f"{store}/{k}")
                if r.status != 200:
                    raise RuntimeError(f"mask chunk {k}: HTTP {r.status}")
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".part")
                tmp.write_bytes(r.body)
                tmp.replace(path)
            raw = path.read_bytes()
            body = self.codec.decode(raw) if self.codec else raw
            self.arrays[k] = np.frombuffer(body, dtype=self.dtype).reshape(self.chunks_shape)
            self.files.append({"key": k, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        self.info = {"product_id": product_id, "dataset_id": dataset_id, "store": store,
                     "long_name": meta.get("mask/.zattrs", {}).get("long_name"), "surface_index": z,
                     "grid_matches_data": True, "chunks": self.files,
                     "bytes_downloaded": sum(f["bytes"] for f in self.files)}

    def is_sea(self, i: int, j: int) -> bool:
        cz, cy, cx = self.chunks_shape
        a = self.arrays[f"mask/{self.z // cz}.{i // cy}.{j // cx}"]
        return int(a[self.z % cz, i % cy, j % cx]) == 1


def sea_summary(mask: SeaMask, table: list[dict]) -> dict:
    """Marks each membership cell sea/land and sums what is left inside the ROI."""
    for c in table:
        c["sea"] = mask.is_sea(c["lat_index"], c["lon_index"])
    sea = [c for c in table if c["sea"]]
    return {"sea_cells": len(sea), "land_cells": len(table) - len(sea),
            "sea_overlap_weight": round(sum(c["overlap_fraction"] for c in sea), 6),
            "sea_cells_mostly_inside": sum(1 for c in sea if c["overlap_fraction"] >= 0.5)}


# ---------------------------------------------------------------- plan section

def region_boxes(rois: list[dict]) -> dict[str, list[float]]:
    boxes = defaultdict(list)
    for r in rois:
        boxes[r["region_id"]].append(r["request"]["bbox_w_s_e_n"])
    return {reg: [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]
            for reg, bs in boxes.items()}


def roi_membership(ds: dict, rc: dict, geom) -> dict:
    """Cells of this dataset's grid inside the ROI request, with overlap fraction (degree-space)."""
    import shapely
    lat, lon = ds["_lat"], ds["_lon"]
    hy, hx = ds["grid"]["lat_step"] / 2, ds["grid"]["lon_step"] / 2
    ii, jj = np.meshgrid(np.arange(rc["lat_index"][0], rc["lat_index"][1] + 1),
                         np.arange(rc["lon_index"][0], rc["lon_index"][1] + 1), indexing="ij")
    ii, jj = ii.ravel(), jj.ravel()
    boxes = shapely.box(lon[jj] - hx, lat[ii] - hy, lon[jj] + hx, lat[ii] + hy)
    frac = shapely.area(shapely.intersection(boxes, geom)) / shapely.area(boxes)
    hit = frac > 0
    return {"roi_cells": int(hit.sum()), "cells_mostly_inside": int((frac >= 0.5).sum()),
            "max_overlap_fraction": float(frac.max()) if len(frac) else 0.0,
            "table": [{"lat_index": int(i), "lon_index": int(j), "lat": float(lat[i]), "lon": float(lon[j]),
                       "overlap_fraction": round(float(f), 6)} for i, j, f in zip(ii[hit], jj[hit], frac[hit])]}


def monthly_batch_bytes(ds: dict, per_region: dict, sizes: dict) -> int:
    """Transfer if fetched in monthly batches: each month re-reads every ~155-day chunk it touches."""
    by_month = defaultdict(list)
    for t, d in ds["_tdates"].items():
        by_month[(d.year, d.month)].append(t)
    total = 0
    for rc in per_region.values():
        for ts in by_month.values():
            for k in rc["keys"]:
                var, idx = k.split("/")
                tchunk = int(idx.split(".")[0])
                ct = ds["variables"][var]["chunks"][0]
                if any(t // ct == tchunk for t in ts):
                    total += sizes[k] or 0
    return total


def plan_section(client: MetadataClient, specs: list[dict], period: dict, rois: list[dict], roi_geoms: dict,
                 max_cells: int, static_dir: Path | None = None) -> dict:
    start, end = dt.date.fromisoformat(period["start"]), dt.date.fromisoformat(period["end"])
    out = {"period": period, "access": "Copernicus Marine Toolbox subset via ARCO geoChunked Zarr "
                                      "(service arco-geo-series); Copernicus Marine account required",
           "batch": "one subset per region x dataset for the whole period", "datasets": []}
    regions = region_boxes(rois)
    for spec in specs:
        ds = resolve_dataset(client, spec, start, end)
        per_roi = {(r["region_id"], r["subregion_id"]): roi_chunks(ds, r["request"]["bbox_w_s_e_n"]) for r in rois}
        per_region = {reg: roi_chunks(ds, box) for reg, box in regions.items()}
        for reg, rc in per_region.items():
            if rc["cells"] > max_cells:
                raise ValueError(f"{spec['key']} {reg}: region box needs {rc['cells']} cells/day > {max_cells}")
        keys = set().union(*(rc["keys"] for rc in per_region.values()), *(rc["keys"] for rc in per_roi.values()))
        sizes = head_sizes(client, ds["store"], keys)
        unknown = sorted(k for k, v in sizes.items() if v is None)

        def total(ks):
            return None if any(sizes[k] is None for k in ks) else sum(sizes[k] for k in ks)

        monthly = monthly_batch_bytes(ds, per_region, sizes)
        sm = spec.get("static_mask")
        mask = (SeaMask(client, sm.get("product_id", spec["product_id"]), sm["dataset_id"], ds, regions, static_dir)
                if sm and static_dir is not None else None)

        rows = []
        for r in rois:
            key = (r["region_id"], r["subregion_id"])
            rc = per_roi[key]
            mem = roi_membership(ds, rc, roi_geoms[key])
            sea = sea_summary(mask, mem["table"]) if mask else None
            rows.append({"dataset": spec["key"], "region_id": r["region_id"], "subregion_id": r["subregion_id"],
                         "variables": list(ds["variables"]), "lat_index": rc["lat_index"], "lon_index": rc["lon_index"],
                         "bbox_cells": rc["cells"], "roi_cells": mem["roi_cells"],
                         "cells_mostly_inside": mem["cells_mostly_inside"],
                         **(sea or {"sea_cells": None}),
                         "days_available": ds["available_days"], "days_requested": ds["requested_days"],
                         "chunks_if_fetched_alone": len(rc["keys"]),
                         "transfer_bytes_if_fetched_alone": total(rc["keys"]),
                         "uncompressed_subset_bytes": rc["uncompressed_bytes"],
                         "final_rows": ds["available_days"] * len(ds["variables"]),
                         "membership": mem["table"]})
        reg_rows = {reg: {"bbox_w_s_e_n": regions[reg], "cells": rc["cells"], "chunks": len(rc["keys"]),
                          "transfer_bytes": total(rc["keys"]),
                          "extra_chunks_vs_roi_union": len(rc["keys"] - set().union(
                              *(per_roi[k]["keys"] for k in per_roi if k[0] == reg))),
                          "output_netcdf_bytes_upper": rc["uncompressed_bytes"] + 50_000,
                          "api_calls_est": len(rc["keys"]) + 6}
                    for reg, rc in per_region.items()}
        out["datasets"].append({
            "key": spec["key"], **{k: v for k, v in public(ds).items() if k not in ("key",)},
            "head_requests": len(sizes), "unknown_chunks": unknown,
            "transfer_bytes": None if unknown else sum(r["transfer_bytes"] for r in reg_rows.values()),
            "transfer_bytes_if_monthly_batches": monthly,
            "naive_per_roi_transfer_bytes": sum((r["transfer_bytes_if_fetched_alone"] or 0) for r in rows),
            "regions": reg_rows, "rois": rows,
            "sea_mask": mask.info if mask else None,
            "confidence": "high: transfer = sum of HEAD Content-Length of every chunk the region subsets read",
        })
    t = [d["transfer_bytes"] for d in out["datasets"]]
    out["transfer_bytes_total"] = None if any(x is None for x in t) else sum(t)
    out["final_rows_total"] = sum(r["final_rows"] for d in out["datasets"] for r in d["rois"])
    out["output_netcdf_bytes_upper_total"] = sum(r["output_netcdf_bytes_upper"] for d in out["datasets"]
                                                 for r in d["regions"].values())
    out["api_calls_est"] = sum(r["api_calls_est"] for d in out["datasets"] for r in d["regions"].values())
    out["zones_without_sea"] = [f"{d['key']} {r['region_id']}/{r['subregion_id']}" for d in out["datasets"]
                                for r in d["rois"] if r.get("sea_cells") == 0]
    out["sea_mask_checked"] = all(d["sea_mask"] for d in out["datasets"])
    out["fetch_guards"] = [
        "Open each dataset once per region (surface level, region box); every chunk is read once.",
        "ARCO chunks are large tiles (BGC 8x16 deg, PHY 2.7x5.3 deg): bytes on the wire cover the tile, "
        "but only cells inside each ROI request box are kept; the rest is never written to disk.",
        "Reject a response whose coordinates fall outside the region box or whose shape differs from the plan.",
        "Keep only membership cells marked sea in the static mask; refuse to run while zones_without_sea is non-empty.",
    ]
    out["unknowns"] = [
        "Copernicus Marine Toolbox may also read coordinate arrays and .zmetadata (a few KB per dataset).",
        "ANFC days near the present are revised; values for the last weeks may change after download.",
        "Coarse model grid (0.25 deg BGC, 1/12 deg PHY) versus 5 km coastal zones: at most one BGC cell lies mostly "
        "inside a ROI, so BGC values describe ~28 km cells around the zone. Land cells are identified by the static mask.",
    ]
    return out
