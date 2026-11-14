"""Pilot end to end against fake Harmony + fake Copernicus toolbox. No network, no credentials."""
import csv
import datetime as dt
import gzip
import io
import json
import urllib.parse

import numpy as np
import pytest
import xarray as xr
from shapely.geometry import box

from seagis_extractor import estimate, fetch, pilot, process
from seagis_extractor.http import Response

GRID = estimate.MurGrid()
VARS = ["analysed_sst", "analysis_error", "mask", "sea_ice_fraction"]
ROI = box(119.70, 4.96, 119.75, 5.00)
SPEC = {"key": "nut", "dataset_id": "D", "variables": ["no3"]}


def make_plan(tmp_path, days=3):
    mdir = tmp_path / "membership"
    m = estimate.membership(GRID, ROI)
    estimate.write_membership(m, mdir / "mur_sst__PH-T__a__v1.csv.gz")
    with gzip.open(mdir / "nut__PH-T__a__v1.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["lat_index", "lon_index", "lat", "lon", "overlap_fraction", "sea"])
        w.writeheader()
        w.writerow({"lat_index": 340, "lon_index": 1199, "lat": 5.0, "lon": 119.75, "overlap_fraction": 0.03, "sea": True})
    inp = tmp_path / "input.json"
    inp.write_text("{}")
    roi = {"region_id": "PH-T", "subregion_id": "a", "geometry_version": "v1", "bbox": list(ROI.bounds),
           "request": estimate.request_for(GRID, ROI, m, VARS),
           "mur_requests": estimate.request_tiles(GRID, ROI, m, VARS, 10_000)}
    plan = {"period": {"start": "2022-06-01", "end": "2022-06-30"},
            "dataset": {"collection": {"concept_id": "C1"}, "variables": {v: {} for v in VARS}},
            "rois": [roi],
            "pilot": {"days": days, "rows": [{"region_id": "PH-T", "subregion_id": "a", "missing_dates": [],
                                              "transfer_bytes_low": 1_000, "transfer_bytes_expected": 30_000,
                                              "transfer_bytes_high": 200_000}]},
            "inputs": {"x": {"path": str(inp), "sha256": estimate.file_sha256(inp)}},
            "copernicus": {"zones_without_sea": [], "datasets": [
                {"key": "nut", "grid": {"lat_step": 0.25, "lon_step": 0.25},
                 "rois": [{"region_id": "PH-T", "subregion_id": "a", "lat_index": [340, 340],
                           "lon_index": [1199, 1199], "available": True}]}]}}
    plan["plan_sha256"] = estimate.plan_hash(plan)
    return plan, mdir


def mur_bytes(req, date, shift_lon=0.0, land_cells=0):
    (i0, i1), (j0, j1) = req["grid_index_range"]["lat"], req["grid_index_range"]["lon"]
    lat, lon = GRID.lat(np.arange(i0, i1 + 1)), GRID.lon(np.arange(j0, j1 + 1)) + shift_lon
    shape = (1, lat.size, lon.size)
    mask = np.ones(shape, "i1")
    mask.reshape(-1)[:land_cells] = 2
    ds = xr.Dataset({"analysed_sst": (("time", "lat", "lon"), np.full(shape, 302.0), {"units": "kelvin"}),
                     "analysis_error": (("time", "lat", "lon"), np.full(shape, 0.4), {"units": "kelvin"}),
                     "mask": (("time", "lat", "lon"), mask),
                     "sea_ice_fraction": (("time", "lat", "lon"), np.zeros(shape))},
                    coords={"time": [np.datetime64(f"{date}T09:00")], "lat": lat, "lon": lon})
    return ds.to_netcdf(engine="h5netcdf")


class FakeHarmony:
    def __init__(self, plan, days, **kw):
        self.req = plan["rois"][0]["mur_requests"][0]
        self.dates = [dt.date(2022, 6, 1) + dt.timedelta(n) for n in range(days)]
        self.kw = kw
        self.downloads = 0

    def transport(self, method, url, headers, timeout):
        if "rangeset" in url:
            return Response(200, {}, json.dumps({"jobID": "J"}).encode())
        links = [{"rel": "data", "href": f"https://harmony.earthdata.nasa.gov/service-results/"
                                         f"{d:%Y%m%d}090000-JPL-L4_GHRSST-SSTfnd-MUR-GLOB-v02.0-fv04.1_subsetted.nc4"}
                 for d in self.dates]
        return Response(200, {}, json.dumps({"status": "successful", "links": links}).encode())

    def stream(self, url, headers, timeout, sink):
        self.downloads += 1
        name = urllib.parse.urlsplit(url).path.rsplit("/", 1)[1]
        d = dt.datetime.strptime(name[:8], "%Y%m%d").date()
        sink(mur_bytes(self.req, d, **self.kw))
        return Response(200, {})

    def client(self, plan, limit=5 << 20):
        allowed = {tuple(q["bbox_w_s_e_n"]) for r in plan["rois"] for q in r["mur_requests"]}
        return fetch.HarmonyClient("t", allowed, fetch.ByteBudget(limit), transport=self.transport,
                                   stream=self.stream, sleep=lambda s: None)


def cm_opener(**kw):
    t = [np.datetime64(f"2022-06-0{d}T00:00") for d in (1, 2, 3)]
    assert kw["minimum_depth"] == 0.0 and kw["maximum_depth"] == 1.0
    return xr.Dataset({"no3": (("time", "depth", "latitude", "longitude"), np.full((3, 1, 1, 1), 0.5),
                               {"units": "mmol m-3"})},
                      coords={"time": t, "depth": [0.494], "latitude": [5.0], "longitude": [119.75]})


def run(tmp_path, plan, mdir, fake):
    return pilot.run_pilot(tmp_path, {"_products": {"copernicus": [SPEC]}}, plan, out_dir=tmp_path / "out",
                           raw_dir=tmp_path / "raw", membership_dir=mdir, harmony=fake.client(plan),
                           cm_opener=cm_opener, log=lambda *a: None)


def test_pilot_end_to_end_pass_rows_and_resume(tmp_path):
    plan, mdir = make_plan(tmp_path)
    fake = FakeHarmony(plan, 3)
    rep = run(tmp_path, plan, mdir, fake)
    bad = [c for c in rep["checks"] if c["status"] == "FAIL"]
    assert rep["status"] == "PASS", bad
    rows = list(csv.DictReader((tmp_path / "out/pilot_daily.csv").open()))
    sst = [r for r in rows if r["variable"] == "analysed_sst"]
    assert len(sst) == 3 and float(sst[0]["mean"]) == pytest.approx(28.85) and sst[0]["units"] == "degree_C"
    no3 = [r for r in rows if r["variable"] == "no3"]
    assert len(no3) == 3 and float(no3[0]["mean"]) == pytest.approx(0.5)
    assert (tmp_path / "out/pilot_report.json").exists() and fake.downloads == 3
    run(tmp_path, plan, mdir, fake)                         # resume: verified files are not fetched again
    assert fake.downloads == 3


def test_pilot_flags_coast_cells_that_mur_calls_land(tmp_path):
    plan, mdir = make_plan(tmp_path)
    rep = run(tmp_path, plan, mdir, FakeHarmony(plan, 3, land_cells=4))
    warn = [c for c in rep["checks"] if c["check"] == "mur.coastline_vs_mask"]
    assert warn and all(c["status"] == "WARN" for c in warn)


def test_response_outside_approved_box_aborts_and_is_deleted(tmp_path):
    plan, mdir = make_plan(tmp_path)
    with pytest.raises(fetch.FetchGuardError, match="outside approved extent"):
        run(tmp_path, plan, mdir, FakeHarmony(plan, 3, shift_lon=5.0))   # e.g. a wrong region came back
    assert not list((tmp_path / "raw").rglob("*.nc4"))
    log = (tmp_path / "out/pilot_manifest.jsonl").read_text()
    assert '"status": "rejected"' in log


def test_unexpected_granule_is_not_downloaded(tmp_path):
    plan, mdir = make_plan(tmp_path, days=2)
    fake = FakeHarmony(plan, 3)                              # Harmony offers 3 days, pilot asked for 2
    rep = run(tmp_path, plan, mdir, fake)
    assert fake.downloads == 2 and rep["rejected"][0]["reason"].startswith("granule date 2022-06-03")


# ---------------------------------------------------------------- plan gate

def test_gate_requires_matching_hash_unchanged_plan_and_inputs(tmp_path):
    plan, _ = make_plan(tmp_path)
    h = plan["plan_sha256"]
    pilot.verify_plan(plan, h, tmp_path)
    with pytest.raises(pilot.PlanGateError, match="approve-plan"):
        pilot.verify_plan(plan, None, tmp_path)
    with pytest.raises(pilot.PlanGateError, match="does not match"):
        pilot.verify_plan(plan, "0" * 64, tmp_path)
    edited = json.loads(json.dumps(plan))
    edited["rois"][0]["mur_requests"][0]["bbox_w_s_e_n"] = [-180, -90, 180, 90]
    with pytest.raises(pilot.PlanGateError, match="modified"):
        pilot.verify_plan(edited, h, tmp_path)
    (tmp_path / "input.json").write_text('{"changed": 1}')
    with pytest.raises(pilot.PlanGateError, match="changed"):
        pilot.verify_plan(plan, h, tmp_path)


def test_dry_run_lists_requests_without_token():
    plan, _ = make_plan(__import__("pathlib").Path(__import__("tempfile").mkdtemp()))
    lines = pilot.dry_run_lines(plan, {"_products": {"copernicus": [SPEC]}})
    assert lines[0].startswith("PILOT DRY RUN 2022-06-01..2022-06-03")
    assert any(l.startswith("MUR PH-T/a: https://harmony.earthdata.nasa.gov/C1/") for l in lines)
    assert any(l.startswith("COPERNICUS D PH-T/a") for l in lines)


def test_weighted_stats_ignore_nan_and_zero_weight():
    s = process._stats(np.array([1.0, 3.0, np.nan, 100.0]), np.array([1.0, 3.0, 1.0, 0.0]))
    assert s["valid_pixel_count"] == 2 and s["mean"] == pytest.approx(2.5) and s["max"] == 3.0
