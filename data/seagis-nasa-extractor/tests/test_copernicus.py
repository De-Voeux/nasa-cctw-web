"""Copernicus ARCO sizing against a fake STAC/Zarr/S3 transport. No network."""
import datetime as dt
import json
import urllib.parse

import numcodecs
import numpy as np
from shapely.geometry import box

from seagis_extractor import copernicus as cm
from seagis_extractor.http import MetadataClient, Response

STORE = "https://s3.example/arco/P/D/geoChunked.zarr"
BLOSC = {"id": "blosc", "cname": "lz4", "clevel": 5, "shuffle": 1, "blocksize": 0}
LAT = np.arange(-10, 10.01, 0.25, dtype="<f4")       # 81
LON = np.arange(110, 130.01, 0.25, dtype="<f4")      # 81
ELEV = np.array([-100, -10, -0.5], dtype="<f4")      # surface is last (max)
# daily times from 2021-11-10, but 2021-11-20 missing
DATES = [dt.datetime(2021, 11, 10) + dt.timedelta(n) for n in range(30) if n != 10]
TIME = np.array([(d - dt.datetime(1950, 1, 1)).total_seconds() / 3600 for d in DATES], dtype="<f4")


def enc(a):
    return numcodecs.get_codec(BLOSC).encode(a.tobytes())


ZMETA = {"metadata": {
    "latitude/.zarray": {"shape": [len(LAT)], "chunks": [len(LAT)], "dtype": "<f4", "compressor": BLOSC},
    "longitude/.zarray": {"shape": [len(LON)], "chunks": [len(LON)], "dtype": "<f4", "compressor": BLOSC},
    "elevation/.zarray": {"shape": [3], "chunks": [3], "dtype": "<f4", "compressor": BLOSC},
    "time/.zarray": {"shape": [len(TIME)], "chunks": [16], "dtype": "<f4", "compressor": BLOSC},
    "time/.zattrs": {"units": "hours since 1950-01-01"},
    "no3/.zarray": {"shape": [len(TIME), 3, len(LAT), len(LON)], "chunks": [10, 2, 32, 32], "dtype": "<f4",
                    "compressor": BLOSC, "fill_value": 9.96e36},
    "no3/.zattrs": {"units": "mmol m-3", "standard_name": "mole_concentration_of_nitrate_in_sea_water"},
}}
STAC = {"properties": {"start_datetime": "2021-11-10T00:00:00Z", "end_datetime": "2021-12-09T00:00:00Z"},
        "assets": {"geoChunked": {"href": STORE}}}


class Fake:
    def __init__(self):
        self.heads = []

    def __call__(self, method, url, timeout, headers):
        path = urllib.parse.urlsplit(url).path
        if "stac" in url:
            return Response(200, {}, json.dumps(STAC).encode())
        if path.endswith(".zmetadata"):
            return Response(200, {}, json.dumps(ZMETA).encode())
        name = path.split("geoChunked.zarr/")[1]
        coords = {"latitude/0": LAT, "longitude/0": LON, "elevation/0": ELEV,
                  "time/0": TIME[:16], "time/1": TIME[16:]}
        if method == "GET" and name in coords:
            return Response(200, {}, enc(coords[name]))
        if method == "HEAD":
            self.heads.append(name)
            if name.endswith(".9.9"):
                return Response(404, {})
            return Response(200, {"Content-Length": "1000"})
        raise AssertionError(f"unexpected {method} {url}")


SPEC = {"key": "nut", "product_id": "P", "dataset_id": "D", "variables": ["no3"], "depth": "surface"}


def resolved(start=dt.date(2021, 11, 15), end=dt.date(2021, 11, 25)):
    c = MetadataClient(transport=Fake(), sleep=lambda s: None)
    return c, cm.resolve_dataset(c, SPEC, start, end)


def test_resolve_dataset_dates_depth_and_missing():
    _, ds = resolved()
    assert ds["depth"]["index"] == 2 and ds["depth"]["elevation_m"] == -0.5
    assert ds["requested_days"] == 11 and ds["available_days"] == 10
    assert ds["missing_dates"] == ["2021-11-20"]
    assert ds["variables"]["no3"]["units"] == "mmol m-3"


def test_roi_chunks_only_surface_and_needed_tiles():
    _, ds = resolved()
    rc = cm.roi_chunks(ds, [119.9, 4.9, 120.1, 5.1])
    # lat index of 5.0 = 60 -> chunk 1; lon index of 120.0 = 40 -> chunk 1; surface z=2 -> zchunk 1
    # time indices 5..14 (Nov 15..25 minus Nov 20) with chunk 10 -> time chunks 0 and 1
    assert rc["keys"] == {"no3/0.1.1.1", "no3/1.1.1.1"}
    assert rc["cells"] == 1                       # one 0.25° cell (119.875-120.125, 4.875-5.125)


def test_plan_section_exact_bytes_dedupe_and_monthly():
    c, _ = resolved()
    rois = [{"region_id": "R", "subregion_id": "a", "request": {"bbox_w_s_e_n": [119.9, 4.9, 120.1, 5.1]}},
            {"region_id": "R", "subregion_id": "b", "request": {"bbox_w_s_e_n": [120.2, 4.9, 120.4, 5.1]}}]
    geoms = {("R", "a"): box(119.9, 4.9, 120.1, 5.1), ("R", "b"): box(120.2, 4.9, 120.4, 5.1)}
    sec = cm.plan_section(c, [SPEC], {"start": "2021-11-15", "end": "2021-12-05"}, rois, geoms, 10_000)
    d = sec["datasets"][0]
    # Nov 15 .. Dec 5 -> time indices 5..24 -> time chunks 0, 1, 2
    assert d["regions"]["R"]["chunks"] == 3 and d["regions"]["R"]["extra_chunks_vs_roi_union"] == 0
    assert d["transfer_bytes"] == 3000                               # shared chunks counted once
    assert d["naive_per_roi_transfer_bytes"] == 6000                 # each ROI alone re-reads them
    # here no month straddles a time chunk, so monthly batches cost the same; never less
    assert d["transfer_bytes_if_monthly_batches"] >= d["transfer_bytes"]
    assert d["rois"][0]["roi_cells"] >= 1 and "membership" in d["rois"][0]
    assert sec["transfer_bytes_total"] == 3000


def test_missing_chunk_counts_zero_bytes():
    c, ds = resolved()
    sizes = cm.head_sizes(c, ds["store"], {"no3/0.1.9.9", "no3/0.1.1.1"})
    assert sizes == {"no3/0.1.9.9": 0, "no3/0.1.1.1": 1000}
