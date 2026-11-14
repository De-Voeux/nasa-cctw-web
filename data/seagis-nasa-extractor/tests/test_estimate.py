"""Estimator tests on synthetic catalog + ROI. No network."""
import datetime as dt
import json

import numpy as np
import pytest
from shapely.geometry import box, mapping

from seagis_extractor import estimate

GRID = estimate.MurGrid()


def test_grid_indices_round_trip():
    assert GRID.lat_index(-89.99) == 0 and GRID.lat_index(89.99) == 17998
    assert GRID.lon_index(-179.99) == 0 and GRID.lon_index(180.0) == 35999
    i = GRID.lat_index(5.0)
    assert abs(GRID.lat(i) - 5.0) < 1e-9


def test_bbox_includes_edge_cells():
    # bbox edges at 5.004 / 5.026 -> cells centred 5.00 .. 5.03 (extents 4.995..5.035)
    i0, i1, j0, j1 = GRID.bbox_indices(120.004, 5.004, 120.026, 5.026)
    assert (i1 - i0 + 1, j1 - j0 + 1) == (4, 4)


def test_cell_area_near_equator():
    a = float(GRID.cell_area_km2(0.0))
    assert 1.22 < a < 1.25   # 0.01° x 0.01° at the equator ≈ 1.237 km²
    assert float(GRID.cell_area_km2(60.0)) == pytest.approx(a * 0.5, rel=0.01)


def test_membership_fractions_and_efficiency():
    roi = box(120.0, 5.0, 120.05, 5.05)          # exactly 5x5 cell spans, offset half a cell
    m = estimate.membership(GRID, roi)
    assert m["bbox_cells"] == 36                  # 6x6 cells intersect the bbox
    assert m["roi_cells"] == 36
    assert np.isclose(m["frac"].sum(), 25.0)      # area fractions add up to 25 full cells
    assert m["roi_area_weighted_km2"] == pytest.approx(25 * float(GRID.cell_area_km2(5.025)), rel=0.01)


def _fixture(tmp_path):
    start, end = dt.date(2020, 1, 30), dt.date(2020, 2, 2)
    dates = [start + dt.timedelta(n) for n in range(4) if n != 2]   # 2020-02-01 missing
    unc = 6 * GRID.nlat * GRID.nlon
    cat = {"period": {"start": start.isoformat(), "end": end.isoformat()},
           "products": [{"key": "mur_sst", "collection": {"concept_id": "C1"},
                         "variables": {"analysed_sst": {"dtype": "short", "units": "kelvin", "fill_values": [-32768],
                                                        "scale_factor": 0.001, "add_offset": 298.15},
                                       "analysis_error": {"dtype": "short", "units": "kelvin", "fill_values": [-32768],
                                                          "scale_factor": 0.01, "add_offset": None},
                                       "mask": {"dtype": "byte", "units": None, "fill_values": [-128],
                                                "scale_factor": 1, "add_offset": None},
                                       "sea_ice_fraction": {"dtype": "byte", "units": "fraction", "fill_values": [-128],
                                                            "scale_factor": 0.01, "add_offset": None}},
                         "granules": [{"date": d.isoformat(), "size_bytes": int(unc * r)}
                                      for d, r in zip(dates, (0.1, 0.2, 0.3))]}]}
    feats = [{"type": "Feature", "geometry": mapping(box(120.0, 5.0, 120.1, 5.1)),
              "properties": {"region_id": "PH-T", "subregion_id": "a", "geometry_version": "v1", "status": "candidate"}},
             {"type": "Feature", "geometry": mapping(box(120.05, 5.0, 120.2, 5.1)),
              "properties": {"region_id": "PH-T", "subregion_id": "b", "geometry_version": "v1", "status": "candidate"}}]
    cfg = {"period": {"start": start.isoformat(), "end": end.isoformat()},
           "execution": {"batch": "monthly", "concurrency": 2, "max_download_gb": 20, "max_disk_gb": 30}}
    plan = estimate.build_plan(cat, {"type": "FeatureCollection", "features": feats}, cfg, {"x": {"sha256": "0"}},
                               tmp_path / "m", pilot={"PH-T": "a"}, pilot_days=2)
    return plan


def test_plan_rows_ranges_and_hash(tmp_path):
    plan = _fixture(tmp_path)
    assert plan["metadata_only"] and plan["science_bytes_downloaded"] == 0
    rows = plan["rows"]
    assert len(rows) == 4                                   # 2 ROIs x 2 months
    jan = next(r for r in rows if r["subregion_id"] == "a" and r["month"] == "2020-01")
    feb = next(r for r in rows if r["subregion_id"] == "a" and r["month"] == "2020-02")
    assert jan["n_time"] == 2 and feb["n_time"] == 1 and feb["missing_dates"] == ["2020-02-01"]
    for r in rows:
        assert r["transfer_bytes_low"] < r["transfer_bytes_expected"] < r["transfer_bytes_high"]
        assert r["transfer_bytes_high"] >= r["uncompressed_bytes"]       # HIGH = no compression + overhead
        overhead = estimate.ASSUMPTIONS["file_overhead_bytes"][1] * r["n_time"]
        assert r["transfer_bytes_expected"] - overhead < r["uncompressed_bytes"]   # never equate the two
        assert 0 < r["mask_efficiency"] <= 1
        assert r["final_rows"] == r["n_time"] * len(estimate.ASSUMPTIONS["output_variables"])
    assert plan["transfer_ratios"]["low"] == pytest.approx(0.1, rel=1e-6)
    assert plan["transfer_ratios"]["expected"] == pytest.approx(0.2, rel=1e-6)
    sf = plan["shared_fetch"]["PH-T"]
    assert sf["unique_bbox_cells"] < sf["naive_bbox_cells"]          # overlapping bboxes deduplicated
    g = plan["totals"]["grand"]
    one_roi = sum(r["retained_raw_bytes_archive_all"] for r in rows if r["subregion_id"] == "a")
    assert g["retained_raw_bytes_archive_all"] == one_roi               # global granules counted once
    assert [r["subregion_id"] for r in plan["pilot"]["rows"]] == ["a"]
    assert plan["pilot"]["rows"][0]["n_time"] == 2
    assert plan["plan_sha256"] == estimate.plan_hash(plan)
    assert len(list((tmp_path / "m").glob("*.csv.gz"))) == 2


def test_hash_is_reproducible_and_sensitive(tmp_path):
    a = _fixture(tmp_path)
    b = _fixture(tmp_path)
    assert a["plan_sha256"] == b["plan_sha256"]                      # timestamp excluded
    b["execution"]["max_download_gb"] = 999
    assert estimate.plan_hash(b) != a["plan_sha256"]


def test_period_mismatch_refuses(tmp_path):
    plan_cfg = {"period": {"start": "2020-01-01", "end": "2020-01-02"}, "execution": {}}
    cat = {"period": {"start": "2019-01-01", "end": "2020-01-02"}, "products": [{"key": "mur_sst"}]}
    with pytest.raises(ValueError):
        estimate.build_plan(cat, {"features": []}, plan_cfg, {}, tmp_path)


def test_estimate_csv_and_summary(tmp_path):
    plan = _fixture(tmp_path)
    path = tmp_path / "estimate.csv"
    estimate.write_estimate_csv(plan, path)
    lines = path.read_text().splitlines()
    assert len(lines) == 5 and lines[0].startswith("dataset,country,region_id")
    text = estimate.summary(plan)
    assert plan["plan_sha256"] in text and "No historical data downloaded" in text
    assert "2020-02-01" in text
    json.dumps(plan, default=str)   # serialisable


# ---------------------------------------------------------------- download-scope guards

def test_request_is_tight_around_roi():
    roi = box(119.6911, 4.9603, 119.8975, 5.2040)
    m = estimate.membership(GRID, roi)
    req = estimate.request_for(GRID, roi, m, ["analysed_sst"])
    w, s, e, n = req["bbox_w_s_e_n"]
    ew, es, ee, en = req["expected_extent_w_s_e_n"]
    q = GRID.step / 4
    # covers the ROI, or at least reaches a quarter cell into every edge cell
    assert w <= max(119.6911, ew + q) and e >= min(119.8975, ee - q)
    assert s <= max(4.9603, es + q) and n >= min(5.2040, en - q)
    # and never sits on (or within a quarter cell of) a cell boundary
    assert w >= ew + q - 1e-9 and s >= es + q - 1e-9 and e <= ee - q + 1e-9 and n <= en - q + 1e-9
    assert e - w < 0.21 + 0.01 and n - s < 0.25 + 0.01
    assert ew >= 119.6911 - 0.01 and ee <= 119.8975 + 0.01
    estimate.check_request(roi, req, max_cells=10_000)



def test_tile_edges_are_inset_from_cell_boundaries():
    # wide ROI -> tiles; every tile edge lies on a cell boundary, so the request must be inset
    roi = box(121.70, -1.90, 122.95, -0.40)
    m = estimate.membership(GRID, roi)
    reqs = estimate.request_tiles(GRID, roi, m, ["analysed_sst"], 10_000)
    assert len(reqs) > 1
    for r in reqs:
        w, s, e, n = r["bbox_w_s_e_n"]
        ew, es, ee, en = r["expected_extent_w_s_e_n"]
        assert min(w - ew, s - es, ee - e, en - n) >= GRID.step / 4 - 1e-9
    estimate.check_tiles(roi, reqs, m, 10_000)


@pytest.mark.parametrize("bad", [
    [-180, -90, 180, 90],                        # global, e.g. pulling Africa too
    [119.0, 4.9603, 119.8975, 5.2040],           # extends far west of the ROI
    [119.70, 4.97, 119.89, 5.20],                # does not cover the ROI
])
def test_guard_rejects_requests_not_tied_to_roi(bad):
    roi = box(119.6911, 4.9603, 119.8975, 5.2040)
    m = estimate.membership(GRID, roi)
    req = estimate.request_for(GRID, roi, m, ["analysed_sst"]) | {"bbox_w_s_e_n": bad}
    with pytest.raises(estimate.RequestGuardError):
        estimate.check_request(roi, req, max_cells=10_000)


def test_guard_rejects_oversized_roi_and_plan_fails(tmp_path):
    roi = box(119.0, 4.0, 121.0, 6.0)            # 200 x 200 cells
    m = estimate.membership(GRID, roi)
    req = estimate.request_for(GRID, roi, m, ["analysed_sst"])
    with pytest.raises(estimate.RequestGuardError):
        estimate.check_request(roi, req, max_cells=10_000)


def test_plan_records_request_per_roi_and_rows(tmp_path):
    plan = _fixture(tmp_path)
    for roi in plan["rois"]:
        assert roi["request"]["expected_cells"] == roi["bbox_cells"]
        assert roi["n_requests"] == len(roi["mur_requests"]) == 1
    assert all(r["request_bbox"] is not None for r in plan["rows"])
    assert any("Reject" in g for g in plan["fetch_guards"])


def test_large_roi_is_tiled_tight_and_complete():
    import shapely
    # an L-shaped coastal strip ~2.0 x 1.5 deg: one bbox would be ~30,000 cells
    roi = shapely.union(box(119.0, 4.0, 121.0, 4.1), box(120.9, 4.0, 121.0, 5.5))
    m = estimate.membership(GRID, roi)
    assert m["bbox_cells"] > 10_000
    reqs = estimate.request_tiles(GRID, roi, m, ["analysed_sst"], 10_000)
    assert len(reqs) > 1 and all(r["expected_cells"] <= 10_000 for r in reqs)
    assert sum(r["expected_cells"] for r in reqs) < m["bbox_cells"] / 2       # empty corner never requested
    estimate.check_tiles(roi, reqs, m, 10_000)                                # covers every ROI cell, no overlap
    with pytest.raises(estimate.RequestGuardError):
        estimate.check_tiles(roi, reqs[1:], m, 10_000)                        # dropping a tile is caught


def test_small_roi_keeps_single_request():
    roi = box(119.6911, 4.9603, 119.8975, 5.2040)
    m = estimate.membership(GRID, roi)
    reqs = estimate.request_tiles(GRID, roi, m, ["analysed_sst"], 10_000)
    assert len(reqs) == 1 and reqs[0]["expected_cells"] == m["bbox_cells"]


def test_calibration_from_pilot_files():
    rois = [{"region_id": "R", "subregion_id": s, "mur_requests": [{"expected_cells": c}]} for s, c in (("a", 500), ("b", 1500))]
    files = [{"source": "mur_sst", "roi": "R/a", "bytes": 59_000 + 500}] * 3 + \
            [{"source": "mur_sst", "roi": "R/b", "bytes": 59_000 + 1500}] * 3
    cal = estimate.calibrate_from_pilot({"status": "PASS", "files": files}, rois)
    assert cal["bytes_per_file"] == pytest.approx(59_000, rel=1e-6) and cal["bytes_per_cell"] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        estimate.calibrate_from_pilot({"status": "FAIL", "files": files}, rois)


def test_calibrated_plan_uses_measured_bytes(tmp_path):
    import json as _j
    plan = _fixture(tmp_path)
    cal = {"bytes_per_file": 50_000, "bytes_per_cell": 2.0, "low_factor": 0.9, "high_factor": 1.25}
    r = plan["rows"][0]
    roi = next(x for x in plan["rois"] if x["subregion_id"] == r["subregion_id"])
    m = {"bbox_cells": roi["bbox_cells"], "roi_cells": roi["roi_cells"], "n_lat": roi["n_lat"], "n_lon": roi["n_lon"],
         "i0": 0, "i1": 0, "j0": 0, "j1": 0}
    row = estimate.row_estimate(roi, m, r["month"], dt.date(2020, 1, 30), dt.date(2020, 1, 31), {"2020-01-30", "2020-01-31"},
                                {"analysed_sst": 2}, {"low": 0.1, "expected": 0.2, "high": 1.0, "calibration": cal}, 1,
                                {"2020-01-30": 0, "2020-01-31": 0})
    cells = sum(q["expected_cells"] for q in roi["mur_requests"])
    assert row["transfer_bytes_expected"] == int((50_000 * len(roi["mur_requests"]) + 2.0 * cells) * 2)
    assert row["transfer_bytes_high"] > row["transfer_bytes_expected"] > row["transfer_bytes_low"]
