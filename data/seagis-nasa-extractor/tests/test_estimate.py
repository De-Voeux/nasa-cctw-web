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
        assert r["final_rows"] == r["n_time"] * 3
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
