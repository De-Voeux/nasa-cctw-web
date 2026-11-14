"""`fetch` backfill against fake Harmony + fake Copernicus toolbox. No network, no credentials."""
import datetime as dt
import json
import re
import urllib.parse

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from seagis_extractor import backfill, estimate, fetch, pilot
from seagis_extractor.http import Response
from test_process import SPEC, make_plan, mur_bytes

START, END = dt.date(2022, 6, 29), dt.date(2022, 7, 2)      # two months -> two MUR units


def make_fetch_plan(tmp_path, calibrated=True, available=True):
    plan, mdir = make_plan(tmp_path)
    plan["period"] = {"start": START.isoformat(), "end": END.isoformat()}
    plan["rows"] = [{"region_id": "PH-T", "subregion_id": "a", "missing_dates": []}]
    plan["execution"] = {"concurrency": 2, "retries": 2, "raw_retention": "discard_after_validation",
                         "max_download_gb": 1}
    plan["transfer_ratios"] = {"calibration": {"bytes_per_file": 59_000}} if calibrated else {}
    c = plan["copernicus"]
    c["period"] = dict(plan["period"])
    c["datasets"][0]["regions"] = {"PH-T": {"bbox_w_s_e_n": plan["rois"][0]["request"]["bbox_w_s_e_n"],
                                            "transfer_bytes": 1000}}
    c["datasets"][0]["rois"][0]["available"] = available
    plan["plan_sha256"] = estimate.plan_hash(plan)
    return plan, mdir


class Harmony:
    """Serves the granules inside the submitted time window; can be told to misbehave."""

    def __init__(self, plan, shift_lon=0.0, fail_month=None):
        self.req = plan["rois"][0]["mur_requests"][0]
        self.shift, self.fail_month = shift_lon, fail_month
        self.jobs, self.downloads = {}, 0

    def transport(self, method, url, headers, timeout):
        if "rangeset" in url:
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            t = next(x for x in q["subset"] if x.startswith("time"))
            a, b = re.findall(r'"(\d{4}-\d\d-\d\d)', t)
            jid = f"J{len(self.jobs)}"
            self.jobs[jid] = (dt.date.fromisoformat(a), dt.date.fromisoformat(b))
            return Response(303, {"Location": f"/jobs/{jid}"})
        jid = url.rsplit("/", 1)[1]
        a, b = self.jobs[jid]
        if self.fail_month and a.strftime("%Y-%m") == self.fail_month:
            return Response(200, {}, json.dumps({"status": "failed", "message": "server error"}).encode())
        days = [a + dt.timedelta(n) for n in range((b - a).days + 1)]
        links = [{"rel": "data", "href": f"https://harmony.earthdata.nasa.gov/service-results/"
                                         f"{d:%Y%m%d}090000-JPL-L4_GHRSST-SSTfnd-MUR-GLOB-v02.0-fv04.1_subsetted.nc4"}
                 for d in days]
        return Response(200, {}, json.dumps({"status": "successful", "links": links}).encode())

    def stream(self, url, headers, timeout, sink):
        self.downloads += 1
        d = dt.datetime.strptime(urllib.parse.urlsplit(url).path.rsplit("/", 1)[1][:8], "%Y%m%d").date()
        sink(mur_bytes(self.req, d, shift_lon=self.shift))
        return Response(200, {})

    def client(self, plan):
        allowed = {tuple(q["bbox_w_s_e_n"]) for r in plan["rois"] for q in r["mur_requests"]}
        return fetch.HarmonyClient("t", allowed, fetch.ByteBudget(10 << 20), transport=self.transport,
                                   stream=self.stream, sleep=lambda s: None)


def cm_opener(**kw):
    a = dt.date.fromisoformat(kw["start_datetime"][:10])
    b = dt.date.fromisoformat(kw["end_datetime"][:10])
    t = [np.datetime64(a + dt.timedelta(n)) for n in range((b - a).days + 1)]
    return xr.Dataset({"no3": (("time", "depth", "latitude", "longitude"), np.full((len(t), 1, 3, 3), 0.5),
                               {"units": "mmol m-3"})},
                      coords={"time": t, "depth": [0.494], "latitude": [4.75, 5.0, 5.25],
                              "longitude": [119.5, 119.75, 120.0]})


def make_bf(tmp_path, plan, mdir, harmony):
    cfg = {"_products": {"copernicus": [SPEC]}, "roi": {"pilot_first": ["PH-T"]}}
    return cfg, backfill.Backfill(tmp_path, cfg, plan, out_dir=tmp_path / "out", raw_dir=tmp_path / "raw",
                                  processed_dir=tmp_path / "processed", membership_dir=mdir,
                                  harmony=harmony.client(plan), cm_opener=cm_opener, log=lambda *a: None,
                                  sleep=lambda s: None)


def test_units_pilot_regions_first_and_month_split(tmp_path):
    plan, _ = make_fetch_plan(tmp_path)
    units = backfill.build_units(plan, {"roi": {"pilot_first": ["PH-T"]}})
    assert [u["key"] for u in units] == ["mur/PH-T/a/2022-06", "mur/PH-T/a/2022-07", "nut/PH-T"]
    assert [len(u["expected"]) for u in units[:2]] == [2, 2]


def test_fetch_writes_parquet_discards_raw_and_resumes(tmp_path):
    plan, mdir = make_fetch_plan(tmp_path)
    h = Harmony(plan)
    cfg, bf = make_bf(tmp_path, plan, mdir, h)
    s = bf.run(backfill.build_units(plan, cfg))
    assert s["ok"] == 3 and s["failed"] == [] and not s["with_issues"]
    june = pd.read_parquet(tmp_path / "processed/mur_sst/PH-T/a/2022-06.parquet")
    assert sorted(june["variable"].unique()) == ["analysed_sst", "analysis_error"]     # sea_ice_fraction dropped
    assert len(june) == 4 and june["mean"].iloc[0] == pytest.approx(28.85, abs=1e-3)
    no3 = pd.read_parquet(tmp_path / "processed/nut/PH-T/a.parquet")
    assert len(no3) == 4 and float(no3["mean"].iloc[0]) == pytest.approx(0.5)
    assert not list((tmp_path / "raw").rglob("*.nc4"))                                  # raw discarded
    n = h.downloads
    cfg, bf2 = make_bf(tmp_path, plan, mdir, h)
    s2 = bf2.run(backfill.build_units(plan, cfg))
    assert s2["units_run"] == 0 and s2["units_skipped_done"] == 3 and h.downloads == n


def test_guard_violation_stops_the_whole_run(tmp_path):
    plan, mdir = make_fetch_plan(tmp_path)
    cfg, bf = make_bf(tmp_path, plan, mdir, Harmony(plan, shift_lon=5.0))
    with pytest.raises(fetch.FetchGuardError):
        bf.run(backfill.build_units(plan, cfg))
    assert not list((tmp_path / "raw").rglob("*.nc4"))
    assert not list((tmp_path / "processed").rglob("*.parquet"))


def test_failing_unit_is_retried_recorded_and_others_continue(tmp_path):
    plan, mdir = make_fetch_plan(tmp_path)
    cfg, bf = make_bf(tmp_path, plan, mdir, Harmony(plan, fail_month="2022-06"))
    s = bf.run(backfill.build_units(plan, cfg))
    assert s["failed"] == ["mur/PH-T/a/2022-06"] and s["ok"] == 2
    rec = bf.manifest.items["mur/PH-T/a/2022-06"]
    assert rec["status"] == "failed" and rec["attempt"] == 2 and "server error" in rec["error"]


def test_unavailable_copernicus_zone_writes_nothing(tmp_path):
    plan, mdir = make_fetch_plan(tmp_path, available=False)
    cfg, bf = make_bf(tmp_path, plan, mdir, Harmony(plan))
    s = bf.run(backfill.build_units(plan, cfg))
    assert s["ok"] == 3 and not (tmp_path / "processed/nut").exists()
    assert "unavailable by decision" in s["with_issues"]["nut/PH-T"][0]


def test_gate_refuses_uncalibrated_plan(tmp_path):
    plan, _ = make_fetch_plan(tmp_path, calibrated=False)
    with pytest.raises(pilot.PlanGateError, match="calibrated"):
        backfill.verify_fetch_plan(plan, plan["plan_sha256"], tmp_path)
    plan, _ = make_fetch_plan(tmp_path)
    backfill.verify_fetch_plan(plan, plan["plan_sha256"], tmp_path)


def test_run_lock_blocks_a_second_live_run_and_clears_stale(tmp_path):
    import os
    lock = tmp_path / "fetch.lock"
    with backfill.RunLock(lock):
        assert lock.read_text() == str(os.getpid())
        with pytest.raises(fetch.FetchError, match="another fetch"):
            backfill.RunLock(lock).__enter__()
    assert not lock.exists()
    lock.write_text("999999")                       # stale pid from a killed run
    with backfill.RunLock(lock):
        pass


def test_concurrency_override_runs_and_keeps_plan_hash(tmp_path):
    plan, mdir = make_fetch_plan(tmp_path)
    h = plan["plan_sha256"]
    cfg = {"_products": {"copernicus": [SPEC]}, "roi": {"pilot_first": ["PH-T"]}}
    bf = backfill.Backfill(tmp_path, cfg, plan, out_dir=tmp_path / "out", raw_dir=tmp_path / "raw",
                           processed_dir=tmp_path / "processed", membership_dir=mdir,
                           harmony=Harmony(plan).client(plan), cm_opener=cm_opener, log=lambda *a: None,
                           sleep=lambda s: None, concurrency=8)
    assert bf.concurrency == 8
    assert bf.run(backfill.build_units(plan, cfg))["ok"] == 3
    backfill.verify_fetch_plan(plan, h, tmp_path)


def test_cli_concurrency_bounds():
    import argparse
    from seagis_extractor import cli
    assert cli._concurrency("12") == 12
    for bad in ("0", "17"):
        with pytest.raises(argparse.ArgumentTypeError):
            cli._concurrency(bad)


def test_status_counts_done_remaining_and_eta(tmp_path):
    import os
    plan, mdir = make_fetch_plan(tmp_path)
    cfg, bf = make_bf(tmp_path, plan, mdir, Harmony(plan, fail_month="2022-07"))
    units = backfill.build_units(plan, cfg)
    bf.run(units)
    lock, log = tmp_path / "out/fetch.lock", tmp_path / "out/batch1.log"
    s = backfill.status(units, tmp_path / "out/fetch_manifest.jsonl", lock, tmp_path / "raw")
    assert (s["done"], s["remaining"], s["running"]) == (2, 1, False)
    assert s["failed_last_attempt"] == ["mur/PH-T/a/2022-07"]
    lock.write_text(str(os.getpid()))
    log.write_text("3 units, 0 already done, running 3\n")
    s = backfill.status(units, tmp_path / "out/fetch_manifest.jsonl", lock, tmp_path / "raw", log,
                        now=lock.stat().st_mtime + 600)
    assert s["running"] and s["done_this_run"] == 2 and s["elapsed_min"] == 10.0 and s["eta_min"] == 5.0
