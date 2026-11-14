"""Preflight size/cost estimate for MUR SST subsets. Metadata and local geometry only.

Every number is derived from: the CMR granule inventory (outputs/catalog.json), UMM-Var
dtypes and dimensions, the candidate ROI polygons, and the explicit assumptions in
ASSUMPTIONS below. Nothing here downloads science data.
"""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import shape

DTYPE_BYTES = {"byte": 1, "ubyte": 1, "short": 2, "ushort": 2, "int": 4, "uint": 4, "float": 4, "double": 8}
EARTH_R_KM = 6371.0088

ASSUMPTIONS = {
    "grid": "MUR v4.1 cell centres lat = -89.99 + 0.01*i (i<17999), lon = -179.99 + 0.01*j (j<36000); "
            "consistent with UMM-Var dimensions but not stated in metadata. Verify (and latitude order) in pilot.",
    "subset_shape": "Harmony HOSS bbox subset returns every grid cell whose extent intersects the request bbox, "
                    "one output file per daily granule.",
    "transfer_ratio_low": "lowest observed global ratio granule_bytes / uncompressed_bytes (CMR sizes).",
    "transfer_ratio_expected": "median observed global ratio; coastal subsets have less land fill, so this may be optimistic.",
    "transfer_ratio_high": 1.0,
    "transfer_ratio_high_why": "HOSS output compression is not documented in metadata; assume none.",
    "file_overhead_bytes": [10_000, 30_000, 60_000],
    "file_overhead_why": "NetCDF-4 header, attributes and lat/lon/time coordinate arrays per output file.",
    "harmony_status_polls_per_job": 6,
    "job_granularity": "one Harmony job per ROI x month (temporal + bbox + variable subset).",
    "concurrency_in_flight_batches": "execution.concurrency ROI-month batches at HIGH size, plus their .part copies.",
    "processing_scratch": "one batch of masked float32 arrays per in-flight batch (uncompressed, 4 bytes/cell/variable).",
    "output_variables": ["analysed_sst", "analysis_error", "sea_ice_fraction"],
    "csv_bytes_per_row": [180, 240, 320],
    "parquet_bytes_per_row": [25, 45, 90],
    "row_size_why": "schema-based model of the daily aggregate table (see FINAL_SCHEMA); no calibration sample yet.",
}

FINAL_SCHEMA = [
    ("date", "date32"), ("region_id", "string"), ("subregion_id", "string"), ("dataset", "string"),
    ("variable", "string"), ("units", "string"), ("valid_pixel_count", "int32"), ("roi_pixel_count", "int32"),
    ("coverage_fraction", "float32"), ("mean", "float32"), ("min", "float32"), ("max", "float32"),
    ("std", "float32"), ("area_weighted", "bool"), ("source_granule", "string"), ("product_version", "string"),
    ("geometry_version", "string"), ("qc_flags", "string"),
]


# ---------------------------------------------------------------- grid

class MurGrid:
    lat0, lon0, step, nlat, nlon = -89.99, -179.99, 0.01, 17999, 36000

    def lat_index(self, lat: float) -> int:
        return int(math.floor((lat - self.lat0) / self.step + 0.5))

    def lon_index(self, lon: float) -> int:
        return int(math.floor((lon - self.lon0) / self.step + 0.5))

    def bbox_indices(self, minx, miny, maxx, maxy):
        """Inclusive index ranges of cells whose extent intersects the bbox."""
        i0, i1 = max(self.lat_index(miny), 0), min(self.lat_index(maxy), self.nlat - 1)
        j0, j1 = max(self.lon_index(minx), 0), min(self.lon_index(maxx), self.nlon - 1)
        return i0, i1, j0, j1

    def lat(self, i):
        return self.lat0 + self.step * np.asarray(i)

    def lon(self, j):
        return self.lon0 + self.step * np.asarray(j)

    def cell_area_km2(self, lat):
        h = self.step / 2
        lat = np.asarray(lat, dtype=float)
        return (EARTH_R_KM ** 2 * math.radians(self.step)
                * (np.sin(np.radians(lat + h)) - np.sin(np.radians(lat - h))))


def membership(grid: MurGrid, geom: shapely.Geometry) -> dict:
    """Cells of the bbox that intersect the ROI, with fractional overlap and cell area."""
    i0, i1, j0, j1 = grid.bbox_indices(*geom.bounds)
    ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
    ii, jj = ii.ravel(), jj.ravel()
    lat, lon = grid.lat(ii), grid.lon(jj)
    h = grid.step / 2
    boxes = shapely.box(lon - h, lat - h, lon + h, lat + h)
    shapely.prepare(geom)
    hit = shapely.intersects(geom, boxes)
    inter = shapely.area(shapely.intersection(boxes[hit], geom))
    frac = inter / (grid.step ** 2)
    area = grid.cell_area_km2(lat[hit])
    return {
        "i0": i0, "i1": i1, "j0": j0, "j1": j1,
        "n_lat": i1 - i0 + 1, "n_lon": j1 - j0 + 1,
        "bbox_cells": int(len(ii)),
        "lat_index": ii[hit], "lon_index": jj[hit], "lat": lat[hit], "lon": lon[hit],
        "frac": np.clip(frac, 0, 1), "cell_area_km2": area,
        "roi_cells": int(hit.sum()),
        "roi_cells_centre_inside": int(shapely.contains_xy(geom, lon, lat).sum()),
        "roi_area_weighted_km2": float((np.clip(frac, 0, 1) * area).sum()),
    }


class RequestGuardError(ValueError):
    pass


def request_for(grid: MurGrid, geom: shapely.Geometry, m: dict, variables: list[str]) -> dict:
    """The exact Harmony request for one ROI: its own bounding box, nothing wider.

    `expected_extent` is the outer edge of the grid cells the provider should return; fetch must
    reject any response whose lat/lon coordinates fall outside it.
    """
    minx, miny, maxx, maxy = geom.bounds
    req = [math.floor(minx * 1e4) / 1e4, math.floor(miny * 1e4) / 1e4,
           math.ceil(maxx * 1e4) / 1e4, math.ceil(maxy * 1e4) / 1e4]
    h = grid.step / 2
    extent = [round(float(grid.lon(m["j0"])) - h, 4), round(float(grid.lat(m["i0"])) - h, 4),
              round(float(grid.lon(m["j1"])) + h, 4), round(float(grid.lat(m["i1"])) + h, 4)]
    return {"bbox_w_s_e_n": req, "variables": variables, "expected_cells": m["bbox_cells"],
            "expected_extent_w_s_e_n": extent, "grid_index_range": {"lat": [m["i0"], m["i1"]], "lon": [m["j0"], m["j1"]]}}


def request_tiles(grid: MurGrid, geom: shapely.Geometry, m: dict, variables: list[str], max_cells: int) -> list[dict]:
    """MUR requests for one ROI. One box if the ROI's own bbox fits `max_cells`; otherwise square
    tiles of at most `max_cells` cells, keeping only tiles that touch the ROI, each shrunk to the
    bbox of (ROI ∩ tile). Every request is tied to the ROI; nothing outside its bbox is asked for."""
    if m["bbox_cells"] <= max_cells:
        return [request_for(grid, geom, m, variables) | {"tile": [0, 0], "piece_bounds": list(geom.bounds)}]
    side = int(math.isqrt(max_cells))
    out = []
    for ti, a in enumerate(range(m["i0"], m["i1"] + 1, side)):
        for tj, b in enumerate(range(m["j0"], m["j1"] + 1, side)):
            h = grid.step / 2
            tile = shapely.box(float(grid.lon(b)) - h, float(grid.lat(a)) - h,
                               float(grid.lon(min(b + side - 1, m["j1"]))) + h,
                               float(grid.lat(min(a + side - 1, m["i1"]))) + h)
            piece = shapely.intersection(geom, tile)
            if piece.is_empty or piece.area == 0:
                continue
            i0, i1, j0, j1 = grid.bbox_indices(*piece.bounds)
            # keep tiles disjoint: never step into the neighbouring tile's rows/columns
            i0, i1 = max(i0, a), min(i1, a + side - 1, m["i1"])
            j0, j1 = max(j0, b), min(j1, b + side - 1, m["j1"])
            pm = {"i0": i0, "i1": i1, "j0": j0, "j1": j1, "bbox_cells": (i1 - i0 + 1) * (j1 - j0 + 1)}
            r = request_for(grid, piece, pm, variables)
            r["grid_index_range"] = {"lat": [i0, i1], "lon": [j0, j1]}
            out.append(r | {"tile": [ti, tj], "piece_bounds": list(piece.bounds)})
    return out


def check_tiles(geom: shapely.Geometry, reqs: list[dict], m: dict, max_cells: int, step: float = 0.01) -> None:
    """Every tile obeys the single-request guard for its piece, tiles never overlap, and together
    they cover every ROI cell in the membership table."""
    for r in reqs:
        check_request(shapely.box(*r["piece_bounds"]), r, max_cells, step)
    if len(reqs) > 1:
        cells = set()
        for r in reqs:
            (a, b), (c, d) = r["grid_index_range"]["lat"], r["grid_index_range"]["lon"]
            tile = {(i, j) for i in range(a, b + 1) for j in range(c, d + 1)}
            if cells & tile:
                raise RequestGuardError("MUR tiles overlap")
            cells |= tile
        missing = sum(1 for i, j in zip(m["lat_index"], m["lon_index"]) if (int(i), int(j)) not in cells)
        if missing:
            raise RequestGuardError(f"MUR tiles miss {missing} ROI cells")


def check_request(geom: shapely.Geometry, req: dict, max_cells: int, step: float = 0.01) -> None:
    """Fail closed if a request is not tightly tied to its ROI."""
    minx, miny, maxx, maxy = geom.bounds
    w, s_, e, n = req["bbox_w_s_e_n"]
    eps = 1e-7   # ~1 cm: float noise at tile edges, not a real gap
    if not (w <= minx + eps and s_ <= miny + eps and e >= maxx - eps and n >= maxy - eps):
        raise RequestGuardError(f"request {req['bbox_w_s_e_n']} does not cover ROI bounds {geom.bounds}")
    if w < minx - step or s_ < miny - step or e > maxx + step or n > maxy + step:
        raise RequestGuardError(f"request {req['bbox_w_s_e_n']} extends more than one grid cell beyond ROI {geom.bounds}")
    ew, es, ee, en = req["expected_extent_w_s_e_n"]
    if ew < minx - step or es < miny - step or ee > maxx + step or en > maxy + step:
        raise RequestGuardError(f"expected response extent {req['expected_extent_w_s_e_n']} exceeds ROI by > 1 cell")
    if req["expected_cells"] > max_cells:
        raise RequestGuardError(f"request needs {req['expected_cells']} cells/day > max_request_cells {max_cells}")


def write_membership(m: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lat_index", "lon_index", "lat", "lon", "overlap_fraction", "cell_area_km2", "weight_km2"])
        for row in zip(m["lat_index"], m["lon_index"], m["lat"], m["lon"], m["frac"], m["cell_area_km2"]):
            i, j, la, lo, fr, ar = row
            w.writerow([int(i), int(j), f"{la:.2f}", f"{lo:.2f}", f"{fr:.6f}", f"{ar:.6f}", f"{fr * ar:.6f}"])


# ---------------------------------------------------------------- per ROI x month

def months(start: dt.date, end: dt.date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        first = max(start, dt.date(y, m, 1))
        last = min(end, dt.date(y, m, calendar.monthrange(y, m)[1]))
        yield f"{y:04d}-{m:02d}", first, last
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def transfer_ratios(granules: list[dict], var_bytes_per_cell: int, ncells_global: int) -> dict:
    unc = var_bytes_per_cell * ncells_global
    r = sorted(g["size_bytes"] / unc for g in granules if g.get("size_bytes"))
    if not r:
        return {"low": None, "expected": None, "high": 1.0, "n": 0}
    return {"low": r[0], "expected": r[len(r) // 2], "high": float(ASSUMPTIONS["transfer_ratio_high"]),
            "n": len(r), "global_uncompressed_bytes": unc}


def row_estimate(roi: dict, m: dict, month: str, first: dt.date, last: dt.date, available: set,
                 var_bytes: dict, ratios: dict, concurrency: int, full_sizes: dict) -> dict:
    days = [first + dt.timedelta(n) for n in range((last - first).days + 1)]
    avail = [d for d in days if d.isoformat() in available]
    reqs = roi.get("mur_requests") or [{"expected_cells": m["bbox_cells"],
                                        "grid_index_range": {"lat": [m["i0"], m["i1"]], "lon": [m["j0"], m["j1"]]}}]
    cells = sum(r["expected_cells"] for r in reqs)
    coords = sum((r["grid_index_range"]["lat"][1] - r["grid_index_range"]["lat"][0] + 1)
                 + (r["grid_index_range"]["lon"][1] - r["grid_index_range"]["lon"][0] + 1) for r in reqs)
    files = len(reqs)
    per_day_unc = cells * sum(var_bytes.values()) + 4 * coords + 8 * files
    unc = per_day_unc * len(avail)
    oh = ASSUMPTIONS["file_overhead_bytes"]
    t = {}
    for k, idx in (("low", 0), ("expected", 1), ("high", 2)):
        ratio = ratios[k]
        t[k] = None if ratio is None else int(per_day_unc * ratio * len(avail) + oh[idx] * files * len(avail))
    n_out = len(ASSUMPTIONS["output_variables"])
    rows = len(avail) * n_out
    scratch = cells * 4 * len(var_bytes) * len(avail)
    peak = {k: (None if v is None else int(concurrency * (2 * v + scratch))) for k, v in t.items()}
    return {
        "dataset": "mur_sst", "country": roi["region_id"].split("-")[0], "region_id": roi["region_id"],
        "subregion_id": roi["subregion_id"], "month": month,
        "bbox": [round(x, 4) for x in roi["bbox"]],
        "request_bbox": roi["request"]["bbox_w_s_e_n"] if "request" in roi else None,
        "n_requests": files,
        "n_time": len(avail), "n_lat": m["n_lat"], "n_lon": m["n_lon"], "n_variables": len(var_bytes),
        "days_in_month_period": len(days), "days_available": len(avail),
        "missing_dates": [d.isoformat() for d in days if d.isoformat() not in available],
        "bbox_cells": m["bbox_cells"], "requested_cells": cells, "roi_ocean_cells": m["roi_cells"],
        "mask_efficiency": round(m["roi_cells"] / cells, 4) if cells else None,
        "uncompressed_bytes": unc,
        "transfer_bytes_low": t["low"], "transfer_bytes_expected": t["expected"], "transfer_bytes_high": t["high"],
        "peak_disk_bytes_low": peak["low"], "peak_disk_bytes_expected": peak["expected"], "peak_disk_bytes_high": peak["high"],
        "retained_raw_bytes_discard_after_validation": 0,
        "retained_raw_bytes_archive_subsets_high": t["high"],
        "retained_raw_bytes_archive_all": sum(full_sizes[d.isoformat()] for d in avail),
        "final_rows": rows,
        "final_parquet_bytes_expected": rows * ASSUMPTIONS["parquet_bytes_per_row"][1],
        "final_csv_bytes_expected": rows * ASSUMPTIONS["csv_bytes_per_row"][1],
        "api_calls": files * (1 + ASSUMPTIONS["harmony_status_polls_per_job"] + len(avail)) if avail else 0,
        "confidence": {"days": "high (CMR inventory)", "grid": "medium (assumed grid origin)",
                       "transfer": "low (no calibration sample; HOSS compression unknown)",
                       "final_size": "low (schema model)"},
    }


# ---------------------------------------------------------------- plan

def canonical_hash(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shared_fetch(rois_m: list[tuple[dict, dict]]) -> dict:
    """Naive per-ROI bbox cells vs unique cells across overlapping bboxes, per region."""
    out = {}
    by_region = defaultdict(list)
    for roi, m in rois_m:
        by_region[roi["region_id"]].append(m)
    for region, ms in by_region.items():
        naive = sum(m["bbox_cells"] for m in ms)
        cells = set()
        for m in ms:
            for i in range(m["i0"], m["i1"] + 1):
                cells.update((i, j) for j in range(m["j0"], m["j1"] + 1))
        union = (min(m["i0"] for m in ms), max(m["i1"] for m in ms), min(m["j0"] for m in ms), max(m["j1"] for m in ms))
        region_bbox = (union[1] - union[0] + 1) * (union[3] - union[2] + 1)
        out[region] = {"naive_bbox_cells": naive, "unique_bbox_cells": len(cells),
                       "overlap_saving_fraction": round(1 - len(cells) / naive, 4) if naive else 0,
                       "single_region_bbox_cells": region_bbox,
                       "note": "per-ROI jobs fetch naive cells with one job set per ROI; one region-wide bbox "
                               "needs fewer jobs/files but fetches single_region_bbox_cells"}
    return out


def build_plan(catalog: dict, roi_geojson: dict, cfg: dict, inputs: dict, membership_dir: Path,
               pilot: dict | None = None, pilot_days: int = 7, copernicus_fn=None) -> dict:
    """copernicus_fn(rois, roi_geoms) -> plan section (network HEADs); None skips Copernicus."""
    prod = next(p for p in catalog["products"] if p["key"] == "mur_sst")
    start = dt.date.fromisoformat(str(cfg["period"]["start"]))
    end = dt.date.fromisoformat(str(cfg["period"]["end"]))
    if catalog["period"] != {"start": start.isoformat(), "end": end.isoformat()}:
        raise ValueError(f"catalog period {catalog['period']} != config period {start}..{end}; rerun catalog")
    variables = prod["variables"]
    var_bytes = {k: DTYPE_BYTES[v["dtype"]] for k, v in variables.items()}
    grid = MurGrid()
    ratios = transfer_ratios(prod["granules"], sum(var_bytes.values()), grid.nlat * grid.nlon)
    available = {g["date"] for g in prod["granules"]}
    full_sizes = {g["date"]: g["size_bytes"] or 0 for g in prod["granules"]}
    conc = int(cfg["execution"].get("concurrency", 2))

    rows, rois_m, roi_summ, roi_geoms = [], [], [], {}
    for f in roi_geojson["features"]:
        p = f["properties"]
        geom = shape(f["geometry"])
        roi_geoms[(p["region_id"], p["subregion_id"])] = geom
        roi = {"region_id": p["region_id"], "subregion_id": p["subregion_id"], "bbox": list(geom.bounds),
               "geometry_version": p["geometry_version"], "status": p["status"]}
        m = membership(grid, geom)
        max_cells = int(cfg["execution"].get("max_request_cells", 10_000))
        roi["request"] = request_for(grid, geom, m, list(variables))     # the ROI's whole bbox (also used by Copernicus)
        roi["mur_requests"] = request_tiles(grid, geom, m, list(variables), max_cells)
        check_tiles(geom, roi["mur_requests"], m, max_cells)
        mpath = membership_dir / f"mur_sst__{p['region_id']}__{p['subregion_id']}__{p['geometry_version']}.csv.gz"
        write_membership(m, mpath)
        rois_m.append((roi, m))
        roi_summ.append({**roi, "n_lat": m["n_lat"], "n_lon": m["n_lon"], "bbox_cells": m["bbox_cells"],
                         "requested_cells": sum(r["expected_cells"] for r in roi["mur_requests"]),
                         "n_requests": len(roi["mur_requests"]),
                         "roi_cells": m["roi_cells"], "roi_cells_centre_inside": m["roi_cells_centre_inside"],
                         "roi_area_weighted_km2": round(m["roi_area_weighted_km2"], 2),
                         "grid_index_range": {"lat": [m["i0"], m["i1"]], "lon": [m["j0"], m["j1"]]},
                         "membership_table": str(mpath.name)})
        for month, first, last in months(start, end):
            rows.append(row_estimate(roi, m, month, first, last, available, var_bytes, ratios, conc, full_sizes))

    pilot_rows = []
    if pilot:
        pstart = start
        pend = start + dt.timedelta(pilot_days - 1)
        for roi, m in rois_m:
            if pilot.get(roi["region_id"]) == roi["subregion_id"]:
                r = row_estimate(roi, m, f"pilot {pstart}..{pend}", pstart, pend, available, var_bytes, ratios, 1, full_sizes)
                pilot_rows.append(r)

    plan = {
        "schema": "seagis.plan/1",
        "metadata_only": True,
        "science_bytes_downloaded": 0,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "dataset": {"key": "mur_sst", "collection": prod["collection"],
                    "variables": {k: {kk: v[kk] for kk in ("dtype", "units", "fill_values", "scale_factor", "add_offset")}
                                  for k, v in variables.items()},
                    "access": "Harmony sds/HOSS-geographic (bbox + temporal + variable subset, NetCDF-4)",
                    "auth": "NASA Earthdata Login required (Harmony token or ~/.netrc)"},
        "execution": {k: cfg["execution"][k] for k in ("batch", "concurrency", "raw_retention", "max_download_gb",
                                                       "max_disk_gb", "retries", "max_request_cells") if k in cfg["execution"]},
        "fetch_guards": [
            "Only the MUR requests listed in rois[].mur_requests may be sent; no global or unlisted bbox. "
            "Large ROIs are split into tiles of at most max_request_cells, each tied to the ROI.",
            "Reject (and do not keep) any response whose lat/lon lie outside that request's expected_extent_w_s_e_n.",
            "Reject any response whose cell count per day differs from that request's expected_cells.",
            "Only pixels in the ROI membership table enter the daily aggregates; the rest of the rectangle is discarded.",
        ],
        "inputs": inputs,
        "assumptions": ASSUMPTIONS,
        "transfer_ratios": ratios,
        "final_schema": FINAL_SCHEMA,
        "rois": roi_summ,
        "shared_fetch": shared_fetch(rois_m),
        "rows": rows,
        "pilot": {"days": pilot_days, "rows": pilot_rows},
        "unknowns": [
            "HOSS output compression and exact cell-edge inclusion rule (calibrate in pilot).",
            "MUR grid origin and latitude ordering (verify in pilot).",
            "Harmony job/poll counts and rate limits.",
            "Final Parquet/CSV bytes per row (no calibration sample).",
            "Coastline accuracy of admin polygons versus MUR mask.",
        ],
    }
    if copernicus_fn is not None:
        sec = copernicus_fn(roi_summ, roi_geoms)
        for d in sec["datasets"]:
            for r in d["rois"]:
                table = r.pop("membership")
                path = membership_dir / f"{d['key']}__{r['region_id']}__{r['subregion_id']}__v1.csv.gz"
                with gzip.open(path, "wt", newline="") as fh:
                    w = csv.DictWriter(fh, fieldnames=["lat_index", "lon_index", "lat", "lon", "overlap_fraction", "sea"],
                                       extrasaction="raise", restval="")
                    w.writeheader()
                    w.writerows(table)
                r["membership_table"] = path.name
        plan["copernicus"] = sec
    plan["totals"] = totals(plan)
    plan["plan_sha256"] = plan_hash(plan)
    plan["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return plan


HASH_EXCLUDED = ("plan_sha256", "generated_at")


def plan_hash(plan: dict) -> str:
    """SHA-256 over everything that defines the work; timestamps excluded so re-planning is reproducible."""
    return canonical_hash({k: v for k, v in plan.items() if k not in HASH_EXCLUDED})


def _sum(rows, key):
    vals = [r[key] for r in rows]
    return None if any(v is None for v in vals) else sum(vals)


def _unique_full(rows) -> int:
    """Whole global granules are shared by every ROI: count each month once, not once per ROI."""
    per_month = defaultdict(int)
    for r in rows:
        per_month[r["month"]] = max(per_month[r["month"]], r["retained_raw_bytes_archive_all"])
    return sum(per_month.values())


def totals(plan: dict) -> dict:
    rows = plan["rows"]
    keys = ["n_time", "uncompressed_bytes", "transfer_bytes_low", "transfer_bytes_expected", "transfer_bytes_high",
            "retained_raw_bytes_archive_subsets_high", "retained_raw_bytes_archive_all", "final_rows",
            "final_parquet_bytes_expected", "final_csv_bytes_expected", "api_calls"]
    out = {"grand": {k: _sum(rows, k) for k in keys}}
    out["grand"]["retained_raw_bytes_archive_all"] = _unique_full(rows)
    for group in ("country", "region_id", "subregion_id"):
        g = defaultdict(list)
        for r in rows:
            g[r[group] if group != "subregion_id" else f"{r['region_id']}/{r['subregion_id']}"].append(r)
        out[group] = {name: {k: _sum(rs, k) for k in keys} | {"retained_raw_bytes_archive_all": _unique_full(rs)}
                      for name, rs in g.items()}
    # peak disk is a max over batches, not a sum; final outputs accumulate on top of it
    for k in ("low", "expected", "high"):
        peak = max(r[f"peak_disk_bytes_{k}"] for r in rows)
        out["grand"][f"peak_disk_bytes_{k}"] = peak + (out["grand"]["final_parquet_bytes_expected"] or 0) \
            + (out["grand"]["final_csv_bytes_expected"] or 0)
    pr = plan["pilot"]["rows"]
    out["pilot"] = {k: _sum(pr, k) for k in keys} if pr else {}
    return out


ESTIMATE_COLUMNS = ["dataset", "country", "region_id", "subregion_id", "month", "bbox", "n_time", "n_lat", "n_lon",
                    "n_variables", "days_in_month_period", "days_available", "missing_dates", "bbox_cells",
                    "roi_ocean_cells", "mask_efficiency", "uncompressed_bytes", "transfer_bytes_low",
                    "transfer_bytes_expected", "transfer_bytes_high", "peak_disk_bytes_low",
                    "peak_disk_bytes_expected", "peak_disk_bytes_high",
                    "retained_raw_bytes_discard_after_validation", "retained_raw_bytes_archive_subsets_high",
                    "retained_raw_bytes_archive_all", "final_rows", "final_parquet_bytes_expected",
                    "final_csv_bytes_expected", "api_calls", "confidence_transfer"]


def write_estimate_csv(plan: dict, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ESTIMATE_COLUMNS)
        w.writeheader()
        for r in plan["rows"]:
            row = {k: r.get(k) for k in ESTIMATE_COLUMNS}
            row["bbox"] = " ".join(str(x) for x in r["bbox"])
            row["missing_dates"] = ";".join(r["missing_dates"])
            row["confidence_transfer"] = r["confidence"]["transfer"]
            w.writerow(row)


COPERNICUS_COLUMNS = ["dataset", "region_id", "subregion_id", "variables", "bbox_cells", "roi_cells",
                      "cells_mostly_inside", "sea_cells", "land_cells", "sea_overlap_weight",
                      "sea_cells_mostly_inside", "days_requested", "days_available", "chunks_if_fetched_alone",
                      "transfer_bytes_if_fetched_alone", "uncompressed_subset_bytes", "final_rows", "membership_table"]


def write_copernicus_csv(plan: dict, path: Path) -> None:
    cm = plan.get("copernicus")
    if not cm:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COPERNICUS_COLUMNS + ["region_fetch_transfer_bytes"])
        w.writeheader()
        for d in cm["datasets"]:
            for r in d["rois"]:
                row = {k: r.get(k) for k in COPERNICUS_COLUMNS}
                row["variables"] = ";".join(r["variables"])
                row["region_fetch_transfer_bytes"] = d["regions"][r["region_id"]]["transfer_bytes"]
                w.writerow(row)


def human(n) -> str:
    if n is None:
        return "unknown"
    for unit, div in (("TiB", 2**40), ("GiB", 2**30), ("MiB", 2**20)):
        if n >= div:
            return f"{n / div:.2f} {unit}"
    return f"{n / 2**20:.3f} MiB"


def summary(plan: dict) -> str:
    t = plan["totals"]
    L = []
    L.append(f"PLAN  MUR SST {plan['dataset']['collection']['concept_id']}  "
             f"{plan['period']['start']} .. {plan['period']['end']}  (metadata only, 0 science bytes)")
    L.append("")
    hdr = f"{'REGION/SUBREGION':26} {'BBOX CELLS':>10} {'ROI CELLS':>9} {'EFF':>5} {'DAYS':>5}  {'TRANSFER LOW / EXPECTED / HIGH':>38}  {'ROWS':>6}"
    L += [hdr, "-" * len(hdr)]
    for roi in plan["rois"]:
        key = f"{roi['region_id']}/{roi['subregion_id']}"
        s = t["subregion_id"][key]
        eff = roi["roi_cells"] / roi["bbox_cells"]
        L.append(f"{key:26} {roi['bbox_cells']:>10} {roi['roi_cells']:>9} {eff:>5.2f} {s['n_time']:>5}  "
                 f"{human(s['transfer_bytes_low']):>11} / {human(s['transfer_bytes_expected']):>11} / {human(s['transfer_bytes_high']):>11}  {s['final_rows']:>6}")
    L.append("-" * len(hdr))
    for c, s in t["country"].items():
        L.append(f"{'COUNTRY ' + c:26} {'':>10} {'':>9} {'':>5} {'':>5}  "
                 f"{human(s['transfer_bytes_low']):>11} / {human(s['transfer_bytes_expected']):>11} / {human(s['transfer_bytes_high']):>11}  {s['final_rows']:>6}")
    g = t["grand"]
    span = f"TOTAL MUR {plan['period']['start'][:4]}-{plan['period']['end'][2:4]}"
    L.append(f"{span:26} {'':>10} {'':>9} {'':>5} {'':>5}  "
             f"{human(g['transfer_bytes_low']):>11} / {human(g['transfer_bytes_expected']):>11} / {human(g['transfer_bytes_high']):>11}  {g['final_rows']:>6}")
    L.append("")
    L.append(f"Peak disk LOW / EXPECTED / HIGH : {human(g['peak_disk_bytes_low'])} / {human(g['peak_disk_bytes_expected'])} / {human(g['peak_disk_bytes_high'])}")
    L.append(f"Retained raw: discard_after_validation 0 | archive_subsets <= {human(g['retained_raw_bytes_archive_subsets_high'])} | archive_all {human(g['retained_raw_bytes_archive_all'])}")
    L.append(f"Final aggregate: {g['final_rows']} rows, Parquet ~{human(g['final_parquet_bytes_expected'])}, CSV ~{human(g['final_csv_bytes_expected'])}")
    L.append(f"Uncompressed subset arrays: {human(g['uncompressed_bytes'])}   API calls (est.): {g['api_calls']}")
    lim_dl, lim_disk = plan["execution"].get("max_download_gb"), plan["execution"].get("max_disk_gb")
    L.append(f"Limits: max_download_gb={lim_dl} -> HIGH {'within' if g['transfer_bytes_high'] <= lim_dl * 1e9 else 'EXCEEDS'} limit; "
             f"max_disk_gb={lim_disk} -> HIGH peak {'within' if g['peak_disk_bytes_high'] <= lim_disk * 1e9 else 'EXCEEDS'} limit")
    sf = plan["shared_fetch"]
    L.append("Shared fetch (cells/day): " + "; ".join(f"{r} per-ROI {v['naive_bbox_cells']}, unique {v['unique_bbox_cells']}, one region bbox {v['single_region_bbox_cells']}"
                                                         for r, v in sf.items()))
    miss = sorted({d for r in plan["rows"] for d in r["missing_dates"]})
    L.append("Download scope: only the boxes in plan.json rois[].mur_requests (see outputs/qa/requests_*.png); "
             f"{sum(r['n_requests'] for r in plan['rois'])} boxes for {len(plan['rois'])} ROIs, largest "
             + str(max(q["expected_cells"] for r in plan["rois"] for q in r["mur_requests"])) + " cells/day, "
             "limit " + str(plan["execution"].get("max_request_cells", 10000)))
    L.append(f"Missing dates (not published): {', '.join(miss) or 'none'}")
    L.append("Confidence: days HIGH, grid MEDIUM, transfer LOW, final size LOW. See plan.json assumptions/unknowns.")
    if plan["pilot"]["rows"]:
        p = t["pilot"]
        names = ", ".join(f"{r['region_id']}/{r['subregion_id']}" for r in plan["pilot"]["rows"])
        L.append(f"Pilot ({plan['pilot']['days']} days; {names}): transfer {human(p['transfer_bytes_low'])} / "
                 f"{human(p['transfer_bytes_expected'])} / {human(p['transfer_bytes_high'])}, {p['api_calls']} API calls")
    cm = plan.get("copernicus")
    if cm:
        L.append("")
        L.append(f"COPERNICUS MARINE  {cm['period']['start']} .. {cm['period']['end']}  surface level, exact chunk sizes via HEAD")
        h2 = f"{'DATASET':16} {'VARS':10} {'GRID':>7} {'DAYS':>9} {'PER REGION':>11} {'IF MONTHLY':>11} {'UNIQUE':>11}"
        L += [h2, "-" * len(h2)]
        for d in cm["datasets"]:
            g = d["grid"]["lat_step"]
            L.append(f"{d['key']:16} {','.join(d['variables']):10} {g:>6.3f}° {d['available_days']:>4}/{d['requested_days']:<4} "
                     f"{human(d['transfer_bytes']):>11} {human(d['transfer_bytes_if_monthly_batches']):>11} "
                     f"{human(d.get('transfer_bytes_unique_all_regions')):>11}")
            L.append("    by region: " + ", ".join(f"{k} {human(v['transfer_bytes'])}" for k, v in d["regions"].items()))
        L.append(f"{'TOTAL COPERNICUS':16} {'':10} {'':>7} {'':>9} {human(cm['transfer_bytes_total']):>11} {'':>11} "
                 f"{human(cm.get('transfer_bytes_total_unique_chunks')):>11}")
        L.append("  PER REGION = one subset per region (chunks shared by regions re-read); "
                 "UNIQUE = every chunk read once (fetch with a shared chunk cache).")
        if cm.get("zones_without_sea"):
            L.append("  BLOCKING zones without sea cells: " + ", ".join(cm["zones_without_sea"]))
        for d in cm["datasets"]:
            if d["missing_dates"]:
                L.append(f"  {d['key']}: {len(d['missing_dates'])} days not in dataset ({d['missing_dates'][0]} .. {d['missing_dates'][-1]})")
        for d in cm["datasets"]:
            sc = [r.get("sea_cells") for r in d["rois"]]
            if all(x is not None for x in sc):
                L.append(f"  {d['key']}: sea cells per ROI min {min(sc)} / median {sorted(sc)[len(sc) // 2]} / max {max(sc)}")
        L.append(f"  Outputs: {cm['final_rows_total']} daily rows, NetCDF subsets <= {human(cm['output_netcdf_bytes_upper_total'])}, "
                 f"~{cm['api_calls_est']} requests. Account: Copernicus Marine (free) needed for fetch.")
        g_t = plan["totals"]["grand"]["transfer_bytes_expected"]
        L.append(f"GRAND TOTAL TRANSFER (MUR expected + Copernicus): {human(g_t + (cm['transfer_bytes_total'] or 0))} per-region, "
                 f"{human(g_t + (cm.get('transfer_bytes_total_unique_chunks') or 0))} with shared chunk cache")
    L.append("")
    L.append(f"PLAN SHA256: {plan['plan_sha256']}")
    L.append("No historical data downloaded. Run fetch only after reviewing and approving the plan.")
    return "\n".join(L)


def request_maps(plan: dict, roi_geojson: dict, qa_dir: Path) -> list[Path]:
    """One overview of all requests in Southeast Asia, plus one zoomed map per region."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    qa_dir.mkdir(parents=True, exist_ok=True)
    geoms = {(f["properties"]["region_id"], f["properties"]["subregion_id"]): shape(f["geometry"])
             for f in roi_geojson["features"]}
    paths = []

    def draw(ax, rois):
        for roi in rois:
            g = geoms[(roi["region_id"], roi["subregion_id"])]
            import geopandas as gpd
            gpd.GeoSeries([g]).plot(ax=ax, color="#2a7ab0", alpha=0.55, lw=0)   # keeps land holes empty
            for q in roi["mur_requests"]:
                w, s_, e, n = q["expected_extent_w_s_e_n"]
                ax.add_patch(Rectangle((w, s_), e - w, n - s_, fill=False, ec="#d1495b", lw=0.9))
            w, s_, e, n = roi["request"]["expected_extent_w_s_e_n"]
            ax.annotate(roi["subregion_id"], (w, n), fontsize=6, color="#d1495b", va="bottom")

    fig, ax = plt.subplots(figsize=(9, 7))
    draw(ax, plan["rois"])
    ax.set_xlim(104, 137)
    ax.set_ylim(-10, 18)
    ax.set_aspect("equal")
    ax.grid(lw=0.3)
    ax.set_title("Requested MUR boxes (red) vs candidate zones (blue): only these boxes are downloaded", fontsize=9)
    p = qa_dir / "requests_overview.png"
    fig.savefig(p, dpi=130, bbox_inches="tight")
    plt.close(fig)
    paths.append(p)

    by_region = defaultdict(list)
    for roi in plan["rois"]:
        by_region[roi["region_id"]].append(roi)
    for region, rois in by_region.items():
        fig, ax = plt.subplots(figsize=(8, 8))
        draw(ax, rois)
        ext = np.array([r["request"]["expected_extent_w_s_e_n"] for r in rois])
        ax.set_xlim(ext[:, 0].min() - 0.05, ext[:, 2].max() + 0.05)
        ax.set_ylim(ext[:, 1].min() - 0.05, ext[:, 3].max() + 0.05)
        ax.set_aspect("equal")
        ax.grid(lw=0.3)
        ax.set_title(f"{region}: requested boxes (red) vs candidate zones (blue)", fontsize=9)
        p = qa_dir / f"requests_{region}.png"
        fig.savefig(p, dpi=130, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)
    return paths
