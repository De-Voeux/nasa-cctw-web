"""`regions build`: candidate coastal ROIs from administrative boundaries.

Method (all distances in a local UTM CRS chosen from the ROI centroid):
1. Select admin units named in config/roi_sources.yaml (exact match on a property; every
   requested name must resolve to exactly one feature, otherwise the build fails).
2. Land mask = union of every admin polygon from the same file inside the search window.
3. Candidate zone = buffer(unit, buffer_km) minus land.
4. Sea is split by nearest coast among the selected units AND their unselected admin
   neighbours: each sea point goes to the unit whose boundary is closest (Voronoi cells of
   densified boundary points). So siblings never overlap, and no ROI claims water that lies
   off a neighbouring regency's coast.

The result is a *candidate* coastal zone. It does not show where seaweed is farmed.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pyproj
import shapely
from shapely.geometry import MultiPoint, mapping
from shapely.ops import unary_union

GEOMETRY_VERSION = "v1"
WGS84 = "EPSG:4326"


@dataclass
class Unit:
    region_id: str
    subregion_id: str
    name: str
    source_key: str
    feature_id: str
    geometry: shapely.Geometry  # in WGS84


def reproject(geom: shapely.Geometry, transformer: pyproj.Transformer) -> shapely.Geometry:
    return shapely.transform(geom, lambda x, y: transformer.transform(x, y), interleaved=False)


def split_near_main(geom: shapely.Geometry, within_km: float) -> tuple[shapely.Geometry, shapely.Geometry]:
    """Keep polygon parts within `within_km` of the unit's largest part; return (kept, dropped)."""
    parts = list(getattr(geom, "geoms", [geom]))
    if len(parts) == 1:
        return geom, shapely.Polygon()
    crs = utm_crs_for(geom)
    to_m = pyproj.Transformer.from_crs(WGS84, crs, always_xy=True)
    parts_m = [reproject(p, to_m) for p in parts]
    main = max(parts_m, key=lambda p: p.area)
    keep = [p for p, pm in zip(parts, parts_m) if pm.distance(main) <= within_km * 1000]
    drop = [p for p, pm in zip(parts, parts_m) if pm.distance(main) > within_km * 1000]
    return unary_union(keep), (unary_union(drop) if drop else shapely.Polygon())


def utm_crs_for(geom: shapely.Geometry) -> pyproj.CRS:
    c = geom.centroid
    zone = int((c.x + 180) // 6) + 1
    return pyproj.CRS.from_epsg((32600 if c.y >= 0 else 32700) + zone)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_source(root: Path, src: dict, verify: bool = True) -> gpd.GeoDataFrame:
    path = root / src["path"]
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; download it (see config/boundary_sources.yaml)")
    if verify and src.get("sha256") and sha256(path) != src["sha256"]:
        raise ValueError(f"checksum mismatch for {path}")
    os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")  # geoBoundaries features exceed GDAL's 200 MB default
    gdf = gpd.read_file(path)
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.set_crs(WGS84) if gdf.crs is None else gdf.to_crs(WGS84)
    gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
    return gdf


def select_units(gdf: gpd.GeoDataFrame, region_id: str, spec: dict, source_key: str) -> list[Unit]:
    prop = spec.get("match_property", "shapeName")
    units = []
    for sub_id, wanted in spec["subregions"].items():
        hits = gdf[gdf[prop] == wanted]
        if within := spec.get("within_bbox"):
            hits = hits[hits.intersects(shapely.box(*within))]
        if len(hits) != 1:
            raise LookupError(f"{region_id}/{sub_id}: {prop}=={wanted!r} matched {len(hits)} features")
        row = hits.iloc[0]
        units.append(Unit(region_id, sub_id, wanted, source_key, str(row.get("shapeID", row.name)), row.geometry))
    return units


def nearest_coast_partition(units_m: list[shapely.Geometry], spacing_m: float = 250.0) -> list[shapely.Geometry]:
    """Territory per unit: union of Voronoi cells of points sampled along that unit's boundary."""
    pts, owner = [], []
    for i, g in enumerate(units_m):
        b = g.boundary
        n = max(int(b.length // spacing_m), 8)
        for d in range(n):
            pts.append(b.interpolate(d * b.length / n))
            owner.append(i)
    env = unary_union(units_m).envelope.buffer(100_000)
    cells = shapely.voronoi_polygons(MultiPoint(pts), extend_to=env)
    # match each cell to its generating point
    tree = shapely.STRtree(pts)
    terr = [[] for _ in units_m]
    for cell in cells.geoms:
        idx = tree.query(cell, predicate="contains")
        if len(idx):
            terr[owner[int(idx[0])]].append(cell)
    return [unary_union(t) if t else shapely.Polygon() for t in terr]


def build_region(units: list[Unit], land_wgs84: shapely.Geometry, buffer_km: float,
                 neighbours_wgs84: list[shapely.Geometry] | None = None) -> list[dict]:
    crs = utm_crs_for(unary_union([u.geometry for u in units]))
    to_m = pyproj.Transformer.from_crs(WGS84, crs, always_xy=True)
    to_ll = pyproj.Transformer.from_crs(crs, WGS84, always_xy=True)
    units_m = [reproject(u.geometry, to_m) for u in units]
    land_m = reproject(land_wgs84, to_m)
    raw = [g.buffer(buffer_km * 1000).difference(land_m) for g in units_m]
    neigh_m = [reproject(g, to_m) for g in (neighbours_wgs84 or [])]
    if len(units) + len(neigh_m) > 1:
        terr = nearest_coast_partition(units_m + neigh_m)[: len(units)]
        zones = [r.intersection(t) for r, t in zip(raw, terr)]
    else:
        zones = raw
    out = []
    for u, r, z in zip(units, raw, zones):
        z = shapely.make_valid(z)
        z = unary_union([g for g in getattr(z, "geoms", [z]) if g.geom_type in ("Polygon", "MultiPolygon")])
        out.append({
            "unit": u,
            "crs": crs.to_string(),
            "area_km2": round(z.area / 1e6, 3),
            "area_before_split_km2": round(r.area / 1e6, 3),
            "n_parts": len(getattr(z, "geoms", [z])),
            "geometry": reproject(z, to_ll),
        })
    return out


def build(root: Path, sources: dict, roi_cfg: dict, regions_cfg: dict, buffer_km: float,
          only: list[str] | None = None, verify: bool = True) -> dict:
    regions_meta = {r["id"]: r for r in regions_cfg["regions"]}
    loaded: dict[str, gpd.GeoDataFrame] = {}
    features, review = [], []
    for region_id, spec in roi_cfg["regions"].items():
        if only and region_id not in only:
            continue
        src_key = spec["source"]
        src = sources["sources"][src_key]
        if src_key not in loaded:
            loaded[src_key] = load_source(root, src, verify)
        gdf = loaded[src_key]
        units = select_units(gdf, region_id, spec, src_key)
        dropped_parts, part_notes = [], {}
        for u in units:
            km = (spec.get("keep_parts_within_km_of_main") or {}).get(u.subregion_id)
            if km is not None:
                n0 = len(getattr(u.geometry, "geoms", [u.geometry]))
                u.geometry, dropped = split_near_main(u.geometry, float(km))
                n1 = len(getattr(u.geometry, "geoms", [u.geometry]))
                if not dropped.is_empty:
                    dropped_parts.append(dropped)
                part_notes[u.subregion_id] = (f"kept {n1} of {n0} admin polygon parts within {km:g} km "
                                              f"of the unit's largest landmass")
        window = unary_union([u.geometry for u in units]).envelope.buffer(buffer_km / 50 + 0.2)
        land = unary_union(gdf[gdf.intersects(window)].geometry.values)
        reach = unary_union([u.geometry for u in units]).buffer(buffer_km / 111.0 * 1.5)
        chosen = {u.feature_id for u in units}
        ids = gdf["shapeID"].astype(str) if "shapeID" in gdf else gdf.index.astype(str)
        neighbours = list(gdf[gdf.intersects(reach) & ~ids.isin(chosen)].geometry.values) + dropped_parts
        for z in build_region(units, land, buffer_km, neighbours):
            u = z["unit"]
            props = {
                "region_id": region_id,
                "subregion_id": u.subregion_id,
                "name": u.name,
                "geometry_version": GEOMETRY_VERSION,
                "status": "candidate",
                "buffer_km": buffer_km,
                "source": f"{src['name']} {src['level']} ({src['license']}), feature {u.feature_id}",
                "source_date": str(src.get("year_represented")),
                "source_sha256": src.get("sha256"),
                "method": "seaward buffer of admin unit minus admin land; sea split by nearest coast among selected units and their admin neighbours",
                "review_notes": spec.get("review_notes", "") or regions_meta.get(region_id, {}).get("review_notes", ""),
                "part_filter": part_notes.get(u.subregion_id, ""),
                "area_km2": z["area_km2"],
                "built_at": dt.date.today().isoformat(),
            }
            features.append({"type": "Feature", "properties": props, "geometry": mapping(z["geometry"])})
            minx, miny, maxx, maxy = z["geometry"].bounds
            review.append({**{k: props[k] for k in ("region_id", "subregion_id", "name", "area_km2")},
                           "area_before_split_km2": z["area_before_split_km2"], "n_parts": z["n_parts"],
                           "bbox": f"{minx:.4f},{miny:.4f},{maxx:.4f},{maxy:.4f}", "utm_crs": z["crs"],
                           "review_status": "pending_visual_review", "reviewer": "", "review_date": ""})
    return {"geojson": {"type": "FeatureCollection", "features": features}, "review": review, "loaded": loaded}


def write_outputs(result: dict, roi_dir: Path, qa_dir: Path) -> list[Path]:
    roi_dir.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)
    gj = roi_dir / f"roi_candidates_{GEOMETRY_VERSION}.geojson"
    tmp = gj.with_suffix(".part")
    tmp.write_text(json.dumps(result["geojson"]))
    tmp.replace(gj)
    rv = qa_dir / "roi_review_manifest.csv"
    with rv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(result["review"][0].keys()))
        w.writeheader()
        w.writerows(result["review"])
    return [gj, rv]


def qa_maps(result: dict, sources_gdfs: dict, qa_dir: Path) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gdf = gpd.GeoDataFrame.from_features(result["geojson"]["features"], crs=WGS84)
    paths = []
    for region_id, grp in gdf.groupby("region_id"):
        minx, miny, maxx, maxy = grp.total_bounds
        pad = 0.15
        win = shapely.box(minx - pad, miny - pad, maxx + pad, maxy + pad)
        fig, ax = plt.subplots(figsize=(9, 9))
        for land in sources_gdfs.values():
            land[land.intersects(win)].plot(ax=ax, color="#d9d2c3", edgecolor="#8a8170", linewidth=0.3)
        grp.plot(ax=ax, column="subregion_id", alpha=0.65, legend=True, categorical=True,
                 legend_kwds={"loc": "lower left", "fontsize": 8})
        ax.set_xlim(minx - pad, maxx + pad)
        ax.set_ylim(miny - pad, maxy + pad)
        ax.set_title(f"{region_id} candidate coastal zones ({GEOMETRY_VERSION}, "
                     f"{grp['buffer_km'].iloc[0]} km seaward) — NOT farm extents", fontsize=10)
        ax.set_xlabel("lon")
        ax.set_ylabel("lat")
        p = qa_dir / f"roi_{region_id}.png"
        fig.savefig(p, dpi=130, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)
    return paths
