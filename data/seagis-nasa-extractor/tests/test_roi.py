"""ROI construction on synthetic geometry (no downloads)."""
import geopandas as gpd
import pyproj
import pytest
import shapely
from shapely.geometry import box, shape
from shapely.ops import unary_union

from seagis_extractor import roi

# Two adjacent "coastal" admin units on a strip of land; sea is everything north of lat 5.0
A = box(120.00, 4.90, 120.10, 5.00)
B = box(120.10, 4.90, 120.20, 5.00)
INLAND = box(119.90, 4.80, 120.30, 4.90)   # non-selected neighbour, also land
LAND = unary_union([A, B, INLAND])


def units():
    return [roi.Unit("R", "a", "A", "src", "1", A), roi.Unit("R", "b", "B", "src", "2", B)]


def _m(g, crs):
    return roi.reproject(g, pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True))


def test_utm_zone_selection():
    assert roi.utm_crs_for(shapely.Point(120.5, 5.0)).to_epsg() == 32651
    assert roi.utm_crs_for(shapely.Point(119.5, -5.5)).to_epsg() == 32750


def test_zones_exclude_land_respect_buffer_and_do_not_overlap():
    out = roi.build_region(units(), LAND, buffer_km=5)
    crs = out[0]["crs"]
    za, zb = (_m(o["geometry"], crs) for o in out)
    land_m = _m(LAND, crs)
    assert za.intersection(land_m).area < 1.0          # m², numerical noise only
    assert za.intersection(zb).area < 1.0               # siblings split, no double counting
    assert za.distance(_m(A, crs)) < 1.0                # touches its own coast
    # every zone point lies within 5 km (+tolerance) of its own unit
    assert _m(A, crs).buffer(5000 + 1).contains(za)
    # split conserves sea area: union equals union of raw buffers minus land
    raw = unary_union([_m(A, crs).buffer(5000), _m(B, crs).buffer(5000)]).difference(land_m)
    assert abs(za.union(zb).area - raw.area) / raw.area < 0.01
    assert out[0]["area_km2"] < out[0]["area_before_split_km2"]


def test_single_unit_is_not_split():
    out = roi.build_region(units()[:1], LAND, buffer_km=5)
    assert out[0]["area_km2"] == out[0]["area_before_split_km2"]


def test_select_units_requires_exactly_one_match():
    gdf = gpd.GeoDataFrame({"shapeName": ["A", "B", "B"], "shapeID": ["1", "2", "3"]},
                           geometry=[A, B, box(130, 0, 131, 1)], crs="EPSG:4326")
    spec = {"subregions": {"a": "A"}}
    assert roi.select_units(gdf, "R", spec, "s")[0].feature_id == "1"
    with pytest.raises(LookupError):
        roi.select_units(gdf, "R", {"subregions": {"b": "B"}}, "s")
    assert roi.select_units(gdf, "R", {"subregions": {"b": "B"}, "within_bbox": [119, 4, 121, 6]}, "s")[0].feature_id == "2"
    with pytest.raises(LookupError):
        roi.select_units(gdf, "R", {"subregions": {"x": "Nowhere"}}, "s")


def test_build_end_to_end_properties(tmp_path):
    src = tmp_path / "b.geojson"
    gpd.GeoDataFrame({"shapeName": ["A", "B", "Inland"], "shapeID": ["1", "2", "3"]},
                     geometry=[A, B, INLAND], crs="EPSG:4326").to_file(src, driver="GeoJSON")
    sources = {"sources": {"s": {"path": "b.geojson", "name": "test", "level": "ADM3", "license": "x",
                                 "year_represented": 2020}}}
    cfg = {"regions": {"R": {"source": "s", "subregions": {"a": "A", "b": "B"}}}}
    res = roi.build(tmp_path, sources, cfg, {"regions": [{"id": "R"}]}, 5)
    feats = res["geojson"]["features"]
    assert len(feats) == 2
    p = feats[0]["properties"]
    assert p["status"] == "candidate" and p["buffer_km"] == 5 and p["geometry_version"] == "v1"
    assert shape(feats[0]["geometry"]).intersection(LAND).area < 1e-8   # deg², ~120 m² reprojection slivers
    paths = roi.write_outputs(res, tmp_path / "roi", tmp_path / "qa")
    assert all(x.exists() for x in paths)


def test_checksum_mismatch_fails(tmp_path):
    (tmp_path / "b.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    with pytest.raises(ValueError):
        roi.load_source(tmp_path, {"path": "b.geojson", "sha256": "0" * 64})


def test_unselected_neighbour_keeps_its_own_water():
    alone = roi.build_region(units()[:1], LAND, buffer_km=5)[0]
    with_n = roi.build_region(units()[:1], LAND, buffer_km=5, neighbours_wgs84=[B])[0]
    paired = roi.build_region(units(), LAND, buffer_km=5)[0]
    assert with_n["area_km2"] < alone["area_km2"]
    assert abs(with_n["area_km2"] - paired["area_km2"]) / paired["area_km2"] < 0.02


def test_split_near_main_keeps_close_parts_only():
    from shapely.geometry import MultiPolygon
    main = box(120.0, 5.0, 120.2, 5.2)
    near = box(120.3, 5.0, 120.31, 5.01)      # ~11 km east
    far = box(121.0, 5.0, 121.01, 5.01)       # ~89 km east
    kept, dropped = roi.split_near_main(MultiPolygon([main, near, far]), 30)
    assert kept.contains(near.centroid) and kept.contains(main.centroid)
    assert not kept.intersects(far) and dropped.contains(far.centroid)
    single, none = roi.split_near_main(main, 1)
    assert single.equals(main) and none.is_empty
