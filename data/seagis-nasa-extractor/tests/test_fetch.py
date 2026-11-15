"""Harmony client against fake transports. No network, no real credentials."""
import datetime as dt
import json
import urllib.parse

import pytest

from seagis_extractor import fetch
from seagis_extractor.http import Response

BOX = [119.6911, 4.9602, 119.8976, 5.204]
TOKEN = "tok.en.value"


def client(transport=None, stream=None, limit=10_000):
    return fetch.HarmonyClient(TOKEN, {tuple(BOX)}, fetch.ByteBudget(limit),
                               transport=transport or (lambda *a: Response(500, {})),
                               stream=stream or (lambda *a: Response(500, {})), sleep=lambda s: None)


def test_harmony_url_selects_exact_days_and_box():
    url = fetch.harmony_url("C1996881146-POCLOUD", ["analysed_sst", "mask"], BOX,
                            dt.date(2022, 6, 1), dt.date(2022, 6, 7))
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert q["variable"] == ["analysed_sst", "mask"]                      # repeated, not comma-joined
    assert "lat(4.9602:5.204)" in q["subset"] and "lon(119.6911:119.8976)" in q["subset"]
    assert 'time("2022-06-01T00:00:00Z":"2022-06-07T20:59:59Z")' in q["subset"]
    assert q["format"] == ["application/x-netcdf4"] and TOKEN not in url


def test_submit_refuses_box_not_in_plan():
    c = client()
    with pytest.raises(fetch.FetchGuardError):
        c.submit("C1", ["analysed_sst"], [-180, -90, 180, 90], dt.date(2022, 6, 1), dt.date(2022, 6, 7))


def test_submit_wait_and_links_with_paging():
    seen = []

    def transport(method, url, headers, timeout):
        seen.append((url, headers))
        if "rangeset" in url:
            return Response(200, {}, json.dumps({"jobID": "J1", "status": "running"}).encode())
        if url.endswith("/jobs/J1") and len([u for u, _ in seen if u.endswith("/jobs/J1")]) < 2:
            return Response(200, {}, json.dumps({"status": "running"}).encode())
        if url.endswith("/jobs/J1"):
            return Response(200, {}, json.dumps({"status": "successful", "links": [
                {"rel": "data", "href": "https://harmony.earthdata.nasa.gov/service-results/a.nc4"},
                {"rel": "next", "href": "https://harmony.earthdata.nasa.gov/jobs/J1?page=2"}]}).encode())
        return Response(200, {}, json.dumps({"links": [
            {"rel": "data", "href": "https://harmony.earthdata.nasa.gov/service-results/b.nc4"}]}).encode())

    c = client(transport)
    job = c.wait(c.submit("C1", ["analysed_sst"], BOX, dt.date(2022, 6, 1), dt.date(2022, 6, 7)))
    assert [l["href"].rsplit("/", 1)[1] for l in c.data_links(job)] == ["a.nc4", "b.nc4"]
    assert all(h == {"Authorization": f"Bearer {TOKEN}"} for _, h in seen)


def test_failed_job_raises():
    def transport(method, url, headers, timeout):
        body = {"jobID": "J"} if "rangeset" in url else {"status": "failed", "message": "bad variable"}
        return Response(200, {}, json.dumps(body).encode())
    c = client(transport)
    with pytest.raises(fetch.FetchError, match="bad variable"):
        c.wait(c.submit("C1", ["x"], BOX, dt.date(2022, 6, 1), dt.date(2022, 6, 1)))


def test_download_follows_redirect_without_leaking_token(tmp_path):
    calls = []

    def stream(url, headers, timeout, sink):
        calls.append((urllib.parse.urlsplit(url).hostname, dict(headers)))
        if "harmony" in url:
            return Response(307, {"Location": "https://bucket.s3.us-west-2.amazonaws.com/a.nc4?X-Amz-Signature=s"})
        sink(b"x" * 100)
        return Response(200, {})

    info = client(stream=stream).download("https://harmony.earthdata.nasa.gov/service-results/a.nc4", tmp_path / "a.nc4")
    assert info["bytes"] == 100 and (tmp_path / "a.nc4").read_bytes() == b"x" * 100
    assert calls[0] == ("harmony.earthdata.nasa.gov", {"Authorization": f"Bearer {TOKEN}"})
    assert calls[1] == ("bucket.s3.us-west-2.amazonaws.com", {})          # token never sent to S3


def test_budget_aborts_and_leaves_no_partial_file(tmp_path):
    def stream(url, headers, timeout, sink):
        for _ in range(10):
            sink(b"x" * 400)
        return Response(200, {})
    with pytest.raises(fetch.FetchGuardError, match="budget"):
        client(stream=stream, limit=1000).download("https://harmony.earthdata.nasa.gov/r/a.nc4", tmp_path / "a.nc4")
    assert list(tmp_path.iterdir()) == []


def test_submit_accepts_303_redirect_to_job():
    def transport(method, url, headers, timeout):
        return Response(303, {"Location": "/jobs/93d52a5c-02c6-443e-a5c3-08bce5ee4e47"}, b"See Other")
    c = client(transport)
    assert c.submit("C1", ["analysed_sst"], BOX, dt.date(2022, 6, 1), dt.date(2022, 6, 7)) == \
        "93d52a5c-02c6-443e-a5c3-08bce5ee4e47"


def test_copernicus_open_splits_version_and_asks_surface_only():
    seen = {}
    fetch.copernicus_open({"dataset_id": "cmems_mod_glo_bgc-nut_anfc_0.25deg_P1D-m_202311", "variables": ["no3"]},
                          BOX, dt.date(2022, 6, 1), dt.date(2022, 6, 7), opener=lambda **kw: seen.update(kw))
    assert seen["dataset_id"] == "cmems_mod_glo_bgc-nut_anfc_0.25deg_P1D-m" and seen["dataset_version"] == "202311"
    assert (seen["minimum_depth"], seen["maximum_depth"]) == (0.49, 0.5)
    assert seen["minimum_longitude"] == BOX[0] and seen["maximum_latitude"] == BOX[3]


def _flaky(n_fail, exc, ok):
    state = {"n": 0}

    def call(*a):
        state["n"] += 1
        if state["n"] <= n_fail:
            raise exc
        return ok(*a)
    return call, state


def test_transient_resets_are_retried_per_request(tmp_path):
    import urllib.error
    from seagis_extractor.http import Response
    reset = urllib.error.URLError(ConnectionResetError(54, "Connection reset by peer"))
    tr, ts = _flaky(2, reset, lambda *a: Response(200, {}, b'{"status": "successful", "links": []}'))

    def body(url, headers, timeout, sink):
        sink(b"abc")
        return Response(200, {})
    st, ss = _flaky(3, ConnectionResetError(54, "reset"), body)
    slept = []
    c = fetch.HarmonyClient("t", set(), fetch.ByteBudget(1 << 20), transport=tr, stream=st, sleep=slept.append)
    assert c._json("https://harmony.earthdata.nasa.gov/jobs/J")["status"] == "successful"
    out = c.download("https://harmony.earthdata.nasa.gov/service-results/x.nc4", tmp_path / "x.nc4")
    assert out["bytes"] == 3 and (tmp_path / "x.nc4").read_bytes() == b"abc"
    assert ts["n"] == 3 and ss["n"] == 4 and len(slept) == 5
    assert not list(tmp_path.glob("*.part"))


def test_retry_gives_up_and_429_is_retried(tmp_path):
    from seagis_extractor.http import Response
    calls = []

    def tr(method, url, headers, timeout):
        calls.append(1)
        return Response(429, {"Retry-After": "7"}, b"slow down") if len(calls) < 3 else Response(200, {}, b"{}")
    slept = []
    c = fetch.HarmonyClient("t", set(), fetch.ByteBudget(1 << 20), transport=tr, sleep=slept.append)
    assert c._json("https://harmony.earthdata.nasa.gov/jobs/J") == {}
    assert slept == [7.0, 7.0]
    st, _ = _flaky(99, ConnectionResetError(54, "reset"), None)
    c = fetch.HarmonyClient("t", set(), fetch.ByteBudget(1 << 20), stream=st, sleep=lambda s: None)
    with pytest.raises(fetch.FetchError, match=r"download https://harmony.earthdata.nasa.gov/service-results/x.nc4 failed 6x: ConnectionResetError"):
        c.download("https://harmony.earthdata.nasa.gov/service-results/x.nc4", tmp_path / "y.nc4")
