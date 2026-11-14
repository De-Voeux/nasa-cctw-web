"""catalog tests against a fake CMR/Harmony transport. No network, no credentials."""
import datetime as dt
import json
import urllib.parse

import pytest

from seagis_extractor import catalog
from seagis_extractor.http import MetadataClient, Response, TransientError

START, END = dt.date(2020, 1, 1), dt.date(2020, 1, 5)


def _gran(ur, name, size, rev="2024-01-01T00:00:00Z", url=None):
    return {"meta": {"revision-date": rev},
            "umm": {"GranuleUR": ur,
                    "TemporalExtent": {"RangeDateTime": {"BeginningDateTime": "x", "EndingDateTime": "y"}},
                    "DataGranule": {"ArchiveAndDistributionInformation": [
                        {"Name": name, "SizeInBytes": size, "Checksum": {"Value": "abc", "Algorithm": "MD5"}},
                        {"Name": name + ".md5", "SizeInBytes": 95}]},
                    "RelatedUrls": [{"Type": "GET DATA VIA DIRECT ACCESS", "URL": "s3://b/" + name},
                                    {"Type": "GET DATA", "URL": url or f"https://archive.example/protected-bucket/{name}?sig=SECRET"}]}}


COLL = {"items": [{"meta": {"concept-id": "C1-POCLOUD", "provider-id": "POCLOUD", "revision-date": "r",
                            "associations": {"services": ["S1"], "variables": ["V1", "V2"]}},
                   "umm": {"ShortName": "MUR", "Version": "4.1", "DOI": {"DOI": "10.x/y"},
                           "TemporalExtents": [{"RangeDateTimes": [{"BeginningDateTime": "2002-05-31T21:00:00Z"}]}]}}]}
VARS = {"items": [
    {"meta": {"concept-id": "V1"}, "umm": {"Name": "analysed_sst", "DataType": "short", "Units": "kelvin",
                                          "FillValues": [{"Value": -32768}], "Scale": 0.001, "Offset": 298.15,
                                          "Dimensions": [{"Name": "lat", "Size": 17999}, {"Name": "lon", "Size": 36000}]}},
    {"meta": {"concept-id": "V2"}, "umm": {"Name": "lat", "DataType": "float"}}]}
CAPS = {"services": [{"name": "sds/HOSS-geographic",
                      "capabilities": {"subsetting": {"bbox": True, "shape": True, "temporal": True, "variable": True, "dimension": False},
                                       "outputFormats": [{"name": "NETCDF-4"}]}}]}
# day 3 missing, day 2 duplicated (newer revision should win), one out-of-period granule
GRANS = {"items": [
    _gran("20191231090000-JPL-L4-MUR", "20191231090000-JPL-L4-MUR.nc", 100),
    _gran("20200101090000-JPL-L4-MUR", "20200101090000-JPL-L4-MUR.nc", 700),
    _gran("OLD_20200102090000-JPL-L4-MUR", "20200102090000-JPL-L4-MUR.nc", 650, rev="2020-01-01T00:00:00Z"),
    _gran("20200102090000-JPL-L4-MUR", "20200102090000-JPL-L4-MUR.nc", 710, rev="2025-01-01T00:00:00Z"),
    _gran("20200104090000-JPL-L4-MUR", "20200104090000-JPL-L4-MUR.nc", 720),
    _gran("20200105090000-JPL-L4-MUR", "20200105090000-JPL-L4-MUR.nc", 730),
]}


class FakeTransport:
    def __init__(self):
        self.log = []

    def __call__(self, method, url, timeout, headers):
        self.log.append((method, url, headers))
        path = urllib.parse.urlsplit(url).path
        if method == "HEAD":
            return Response(303, {"Location": "https://cdn.example/signed?Signature=SECRET"})
        if path.endswith("/collections.umm_json"):
            return Response(200, {}, json.dumps(COLL).encode())
        if path.endswith("/variables.umm_json"):
            return Response(200, {}, json.dumps(VARS).encode())
        if path.endswith("/granules.umm_json"):
            return Response(200, {}, json.dumps(GRANS).encode())
        if path.endswith("/capabilities"):
            return Response(200, {}, json.dumps(CAPS).encode())
        raise AssertionError(f"unexpected {method} {url}")


PRODUCTS = {"mur_sst": {"short_name": "MUR", "granule_pattern": "*MUR*", "variables": ["analysed_sst", "mask"]}}


def run():
    t = FakeTransport()
    cat = catalog.build_catalog(MetadataClient(transport=t, sleep=lambda s: None), PRODUCTS,
                                {"mur_sst": {"enabled": True}}, START, END)
    return cat, t


def test_metadata_only_and_no_science_get():
    cat, t = run()
    assert cat["science_bytes_downloaded"] == 0
    gets = [u for m, u, _ in t.log if m == "GET"]
    assert all("cmr.earthdata.nasa.gov" in u or "harmony.earthdata.nasa.gov" in u for u in gets)
    heads = [u for m, u, _ in t.log if m == "HEAD"]
    assert len(heads) == 1


def test_variables_units_and_missing_variable_reported():
    p = run()[0]["products"][0]
    v = p["variables"]["analysed_sst"]
    assert v["units"] == "kelvin" and v["fill_values"] == [-32768] and v["add_offset"] == 298.15
    assert v["dimensions"] == {"lat": 17999, "lon": 36000}
    assert p["missing_variables"] == ["mask"]


def test_inventory_dedupes_and_reports_gaps():
    inv = run()[0]["products"][0]["inventory"]
    assert inv["unique_dates"] == 4
    assert inv["first_date"] == "2020-01-01" and inv["last_date"] == "2020-01-05"
    m = inv["months"]["2020-01"]
    assert m["days_in_period"] == 5 and m["granules"] == 4
    assert m["missing_dates"] == ["2020-01-03"]
    assert m["bytes_total"] == 700 + 710 + 720 + 730  # newer duplicate kept, .md5 sidecar ignored
    assert inv["duplicates"] == [{"date": "2020-01-02", "kept": "20200102090000-JPL-L4-MUR",
                                  "dropped": "OLD_20200102090000-JPL-L4-MUR"}]


def test_no_signed_urls_or_secrets_in_output():
    cat = run()[0]
    blob = json.dumps(cat)
    assert "SECRET" not in blob and "Signature" not in blob
    ep = cat["products"][0]["endpoint"]
    assert ep["classification"] == "redirect_to_signed_url" and ep["redirect_host"] == "cdn.example"
    assert ep["bucket"] == "protected-bucket"


def test_harmony_capabilities_summarised():
    h = run()[0]["products"][0]["harmony"]
    assert h["services"][0]["subsetting"] == {"bbox": True, "shape": True, "temporal": True, "variable": True}


def test_pagination_uses_search_after_header():
    page1 = {"items": [_gran(f"2020010{i}090000-X", f"2020010{i}090000-X.nc", 1) for i in range(1, 3)]}
    page2 = {"items": [_gran("20200103090000-X", "20200103090000-X.nc", 1)]}
    calls = []

    def tr(method, url, timeout, headers):
        calls.append(headers)
        body, hdr = (page1, {"CMR-Search-After": '["tok"]'}) if not headers else (page2, {})
        return Response(200, hdr, json.dumps(body).encode())

    old = catalog.PAGE_SIZE
    catalog.PAGE_SIZE = 2
    try:
        g = catalog.list_granules(MetadataClient(transport=tr), "X", "*", START, END)
    finally:
        catalog.PAGE_SIZE = old
    assert len(g) == 3 and calls[1] == {"CMR-Search-After": '["tok"]'}


def test_retry_with_backoff_then_fail():
    sleeps = []
    c = MetadataClient(transport=lambda *a: Response(503, {}), retries=3, backoff=1, sleep=sleeps.append)
    with pytest.raises(TransientError):
        c.request("GET", "https://cmr.example/x")
    assert sleeps == [1, 2, 4] and c.calls == 4


def test_unknown_collection_is_recorded_not_fatal():
    def tr(method, url, timeout, headers):
        return Response(200, {}, b'{"items": []}')
    cat = catalog.build_catalog(MetadataClient(transport=tr), PRODUCTS, {}, START, END)
    assert "no collection" in cat["products"][0]["error"]


@pytest.mark.parametrize("name,expected", [
    ("20200101090000-JPL-L4_GHRSST-SSTfnd-MUR-GLOB-v02.0-fv04.1", dt.date(2020, 1, 1)),
    ("20261113090000-JPL-L4_GHRSST-SSTfnd-MUR-GLOB-v02.0-fv04.1.nc", dt.date(2026, 11, 13)),
    ("no-date-here.nc", None),
])
def test_granule_date(name, expected):
    assert catalog.granule_date(name) == expected


def test_inventory_csv(tmp_path):
    import csv
    path = catalog.write_inventory_csv(run()[0], tmp_path)
    rows = list(csv.DictReader(path.open()))
    assert len(rows) == 1
    r = rows[0]
    assert r["month"] == "2020-01" and r["granules_available"] == "4" and r["missing_days"] == "1"
    assert r["missing_dates"] == "2020-01-03" and r["full_granule_bytes_total"] == str(700 + 710 + 720 + 730)
