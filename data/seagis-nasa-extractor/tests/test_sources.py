"""Ocean currents (derived), GPM IMERG and NASA POWER. Fakes only: no network, no credentials."""
import datetime as dt
import json
import re
import urllib.parse

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import box

from seagis_extractor import backfill, estimate, fetch, imerg, power, process
from seagis_extractor.http import Response
from test_backfill import cm_opener, make_fetch_plan

ZONE = box(119.72, 4.93, 119.88, 5.02)        # 2 x 2 IMERG cells (119.70-119.90, 4.90-5.10)
KEY = ("PH-T", "a")
IM_SPEC = {"short_name": "GPM_3IMERGDL", "version": "07", "concept_id": "C-IMERG",
           "granule_pattern": "3B-DAY-L*", "variables": ["precipitation", "randomError"]}
PW_SPEC = {"endpoint": "https://power.larc.nasa.gov/api/temporal/daily/point", "community": "AG",
           "parameters": ["T2M", "WD10M"]}


# ---------------------------------------------------------------- currents

def test_current_direction_is_toward_clockwise_from_north():
    w = np.ones(2)
    def run(u, v):
        return {k: s for k, _, s in process.current_stats(np.array(u, float), np.array(v, float), w, "m s-1")}
    east = run([0.3, 0.3], [0.0, 0.0])
    assert east["current_direction"]["mean"] == pytest.approx(90.0)
    assert east["current_speed"]["mean"] == pytest.approx(0.3)
    assert east["current_steadiness"]["mean"] == pytest.approx(1.0)
    assert run([0, 0], [0.2, 0.2])["current_direction"]["mean"] == pytest.approx(0.0)
    assert run([-0.1, -0.1], [-0.1, -0.1])["current_direction"]["mean"] == pytest.approx(225.0)
    cancel = run([0.2, -0.2], [0.0, 0.0])
    assert cancel["current_speed"]["mean"] == pytest.approx(0.2)
    assert cancel["current_steadiness"]["mean"] == pytest.approx(0.0)
    assert cancel["current_direction"]["min"] is None and cancel["current_direction"]["std"] is None
    empty = run([np.nan, np.nan], [0.1, 0.1])
    assert empty["current_direction"]["mean"] is None and empty["current_speed"]["valid_pixel_count"] == 0


def test_copernicus_aggregate_adds_derived_current_rows():
    t = [np.datetime64("2022-06-01")]
    ds = xr.Dataset({"uo": (("time", "latitude", "longitude"), np.full((1, 1, 2), 0.1), {"units": "m s-1"}),
                     "vo": (("time", "latitude", "longitude"), np.full((1, 1, 2), -0.1), {"units": "m s-1"})},
                    coords={"time": t, "latitude": [5.0], "longitude": [119.75, 119.833]})
    mem = [{"lat": 5.0, "lon": 119.75, "overlap_fraction": 0.5, "sea": "True"},
           {"lat": 5.0, "lon": 119.833, "overlap_fraction": 0.2, "sea": "True"}]
    roi = {"region_id": "PH-T", "subregion_id": "a"}
    rows = {r["variable"]: r for r in process.aggregate_copernicus(ds, mem, roi, "cmems_phy_cur", "D")}
    assert set(rows) == {"uo", "vo", "current_speed", "current_direction", "current_steadiness"}
    assert rows["current_direction"]["mean"] == pytest.approx(135.0)       # flowing to the south-east
    assert rows["current_direction"]["units"] == "degree"
    assert rows["current_speed"]["mean"] == pytest.approx(np.hypot(0.1, 0.1), abs=1e-6)


# ---------------------------------------------------------------- IMERG

def imerg_granules(days):
    return [{"granule_ur": f"3B-DAY-L.MS.MRG.3IMERG.{d:%Y%m%d}-S000000-E235959.V07C.nc4", "date": d,
             "revision_date": "2026-01-01"} for d in days]


def imerg_bytes(req, date, value=12.5, shift=0.0):
    g = imerg.ImergGrid()
    (i0, i1), (j0, j1) = req["grid_index_range"]["lat"], req["grid_index_range"]["lon"]
    lat = g.lat(np.arange(i0, i1 + 1)).astype("float32")
    lon = (g.lon(np.arange(j0, j1 + 1)) + shift).astype("float32")
    shape = (1, lon.size, lat.size)                                        # IMERG order: time, lon, lat
    ds = xr.Dataset({"precipitation": (("time", "lon", "lat"), np.full(shape, value, "f4"), {"units": "mm/day"}),
                     "randomError": (("time", "lon", "lat"), np.full(shape, 3.0, "f4"), {"units": "mm/day"})},
                    coords={"time": [np.datetime64(f"{date}T00:00")], "lat": lat, "lon": lon})
    return ds.to_netcdf(engine="h5netcdf")


def add_imerg_and_power(tmp_path, plan, mdir):
    plan["rois"][0]["geometry_version"] = "v1"
    days = [dt.date(2022, 6, 29), dt.date(2022, 6, 30), dt.date(2022, 7, 1)]   # 2022-07-02 not published
    plan["imerg"] = imerg.plan_section(None, IM_SPEC, plan["period"], plan["rois"], {KEY: ZONE}, mdir, 10_000,
                                       granules=imerg_granules(days))
    plan["power"] = power.plan_section(None, PW_SPEC, plan["period"], plan["rois"], {KEY: ZONE}, meta={})
    plan["plan_sha256"] = estimate.plan_hash(plan)
    return plan


def test_imerg_plan_requests_cover_zone_cells():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        rois = [{"region_id": "PH-T", "subregion_id": "a", "geometry_version": "v1"}]
        sec = imerg.plan_section(None, IM_SPEC, {"start": "2022-06-29", "end": "2022-07-02"}, rois, {KEY: ZONE},
                                 Path(d), 10_000, granules=imerg_granules([dt.date(2022, 6, 29)]))
        assert sec["missing_dates"] == ["2022-06-30", "2022-07-01", "2022-07-02"]
        r = sec["rois"][0]
        assert r["roi_cells"] == 4 and r["requests"][0]["expected_cells"] == 4
        w, s, e, n = r["requests"][0]["bbox_w_s_e_n"]
        assert w > 119.70 and e < 119.90 and s > 4.90 and n < 5.10              # inside the four cells only
        mem = process.read_membership(Path(d) / r["membership_table"])
        assert len(mem) == 4


class ImergHarmony:
    """Fake Harmony serving MUR or IMERG granules depending on the collection in the URL."""

    def __init__(self, plan, imerg_shift=0.0):
        self.mur_req = plan["rois"][0]["mur_requests"][0]
        self.im_req = plan["imerg"]["rois"][0]["requests"][0]
        self.published = {dt.date(2022, 6, 29), dt.date(2022, 6, 30), dt.date(2022, 7, 1)}
        self.shift, self.jobs = imerg_shift, {}

    def transport(self, method, url, headers, timeout):
        if "rangeset" in url:
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            a, b = re.findall(r'"(\d{4}-\d\d-\d\d)', next(x for x in q["subset"] if x.startswith("time")))
            jid = f"J{len(self.jobs)}"
            self.jobs[jid] = ("C-IMERG" in url, dt.date.fromisoformat(a), dt.date.fromisoformat(b))
            return Response(303, {"Location": f"/jobs/{jid}"})
        is_im, a, b = self.jobs[url.rsplit("/", 1)[1]]
        days = [a + dt.timedelta(n) for n in range((b - a).days + 1)]
        base = "https://harmony.earthdata.nasa.gov/service-results/"
        if is_im:
            links = [{"rel": "data", "href": f"{base}3B-DAY-L.MS.MRG.3IMERG.{d:%Y%m%d}-S000000-E235959.V07C_subsetted.nc4"}
                     for d in days if d in self.published]
        else:
            links = [{"rel": "data", "href": f"{base}{d:%Y%m%d}090000-JPL-L4_GHRSST-SSTfnd-MUR-GLOB-v02.0-fv04.1_subsetted.nc4"}
                     for d in days]
        return Response(200, {}, json.dumps({"status": "successful", "links": links}).encode())

    def stream(self, url, headers, timeout, sink):
        from test_process import mur_bytes
        name = urllib.parse.urlsplit(url).path.rsplit("/", 1)[1]
        if "IMERG" in name:
            d = dt.datetime.strptime(re.search(r"\.(\d{8})-S", name).group(1), "%Y%m%d").date()
            sink(imerg_bytes(self.im_req, d, shift=self.shift))
        else:
            sink(__import__("test_process").mur_bytes(self.mur_req, dt.datetime.strptime(name[:8], "%Y%m%d").date()))
        return Response(200, {})

    def client(self, plan):
        allowed = {tuple(q["bbox_w_s_e_n"]) for r in plan["rois"] for q in r["mur_requests"]}
        allowed |= {tuple(q["bbox_w_s_e_n"]) for r in plan["imerg"]["rois"] for q in r["requests"]}
        return fetch.HarmonyClient("t", allowed, fetch.ByteBudget(10 << 20), transport=self.transport,
                                   stream=self.stream, sleep=lambda s: None)


def power_response(row, days, fill_last=True, lon=None):
    series = {d.strftime("%Y%m%d"): 28.5 for d in days}
    if fill_last:
        series[days[-1].strftime("%Y%m%d")] = -999.0
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon or row["lon"], row["lat"], 0.0]},
            "properties": {"parameter": {"T2M": series, "WD10M": {k: 200.0 for k in series}}},
            "header": {"fill_value": -999.0, "api": {"version": "v2.5"}, "sources": ["MERRA2"]},
            "parameters": {"T2M": {"units": "C"}, "WD10M": {"units": "Degrees"}}}


def power_transport(plan, **kw):
    row = plan["power"]["rois"][0]
    days = [dt.date(2022, 6, 29) + dt.timedelta(n) for n in range(4)]
    calls = []

    def t(method, url, headers, timeout):
        calls.append(url)
        assert "Authorization" not in headers
        return Response(200, {}, json.dumps(power_response(row, days, **kw)).encode())
    return t, calls


def make_bf(tmp_path, plan, mdir, harmony, ptransport):
    cfg = {"_products": {"copernicus": [{"key": "nut", "dataset_id": "D", "variables": ["no3"]}]},
           "roi": {"pilot_first": ["PH-T"]}}
    pc = power.PowerClient({r["url"] for r in plan["power"]["rois"]}, transport=ptransport, sleep=lambda s: None)
    return cfg, backfill.Backfill(tmp_path, cfg, plan, out_dir=tmp_path / "out", raw_dir=tmp_path / "raw",
                                  processed_dir=tmp_path / "processed", membership_dir=mdir,
                                  harmony=harmony.client(plan), cm_opener=cm_opener, log=lambda *a: None,
                                  sleep=lambda s: None, power_client=pc)


def test_fetch_imerg_and_power_units(tmp_path):
    plan, mdir = make_fetch_plan(tmp_path)
    plan = add_imerg_and_power(tmp_path, plan, mdir)
    units = backfill.build_units(plan, {"roi": {"pilot_first": ["PH-T"]}})
    keys = [u["key"] for u in units]
    assert keys[-3:] == ["imerg/PH-T/a/2022-06", "imerg/PH-T/a/2022-07", "power/PH-T/a"]
    assert [len(u["expected"]) for u in units if u["kind"] == "imerg"] == [2, 1]
    pt, calls = power_transport(plan)
    cfg, bf = make_bf(tmp_path, plan, mdir, ImergHarmony(plan), pt)
    s = bf.run(units)
    assert s["failed"] == [] and s["ok"] == len(units)
    june = pd.read_parquet(tmp_path / "processed/gpm_imerg/PH-T/a/2022-06.parquet")
    assert sorted(june["variable"].unique()) == ["precipitation", "randomError"]
    p = june[june["variable"] == "precipitation"]
    assert len(p) == 2 and p["mean"].iloc[0] == pytest.approx(12.5) and (p["valid_pixel_count"] == 4).all()
    assert not list((tmp_path / "raw").rglob("*.nc4"))
    w = pd.read_parquet(tmp_path / "processed/nasa_power/PH-T/a.parquet")
    assert len(w) == 8 and not w["area_weighted"].any() and (w["roi_pixel_count"] == 1).all()
    t2m = w[w["variable"] == "T2M"].sort_values("date")
    assert t2m["units"].iloc[0] == "C" and t2m["mean"].iloc[0] == pytest.approx(28.5)
    assert pd.isna(t2m["mean"].iloc[-1]) and t2m["valid_pixel_count"].iloc[-1] == 0     # fill kept empty
    assert "fill" in s["with_issues"]["power/PH-T/a"][0]
    assert len(calls) == 1 and urllib.parse.urlsplit(calls[0]).hostname == "power.larc.nasa.gov"


def test_imerg_response_off_grid_aborts(tmp_path):
    plan, mdir = make_fetch_plan(tmp_path)
    plan = add_imerg_and_power(tmp_path, plan, mdir)
    units = backfill.build_units(plan, {"roi": {"pilot_first": ["PH-T"]}}, sources="imerg")
    pt, _ = power_transport(plan)
    cfg, bf = make_bf(tmp_path, plan, mdir, ImergHarmony(plan, imerg_shift=0.5), pt)
    with pytest.raises(fetch.FetchGuardError):
        bf.run(units)
    assert not list((tmp_path / "processed").rglob("*.parquet"))


def test_power_guard_and_allowlist(tmp_path):
    plan, mdir = make_fetch_plan(tmp_path)
    plan = add_imerg_and_power(tmp_path, plan, mdir)
    row = plan["power"]["rois"][0]
    assert ZONE.covers(__import__("shapely").Point(row["lon"], row["lat"]))
    days = [dt.date(2022, 6, 29) + dt.timedelta(n) for n in range(4)]
    with pytest.raises(fetch.FetchGuardError, match="point"):
        power.guard(power_response(row, days, lon=row["lon"] + 0.5), row, ["T2M", "WD10M"], days)
    with pytest.raises(fetch.FetchGuardError, match="requested days"):
        power.guard(power_response(row, days[:3]), row, ["T2M", "WD10M"], days)
    pc = power.PowerClient({row["url"]}, transport=lambda *a: Response(200, {}, b"{}"), sleep=lambda s: None)
    with pytest.raises(fetch.FetchGuardError, match="not in the approved plan"):
        pc.get(row["url"].replace("T2M", "PRECTOTCORR"))
    flaky = iter([ConnectionResetError("reset"), Response(503, {}), Response(200, {}, b'{"ok": 1}')])

    def t(*a):
        x = next(flaky)
        if isinstance(x, Exception):
            raise x
        return x
    assert power.PowerClient({row["url"]}, transport=t, sleep=lambda s: None).get(row["url"]) == {"ok": 1}
