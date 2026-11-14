"""seagis-extract command line. Only `catalog` is implemented so far."""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml

from . import catalog
from .http import MetadataClient


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text())
    base = path.resolve().parent.parent  # config/ lives at the project root
    cfg["_root"] = base
    pf = base / cfg.get("products_file", "config/products.yaml")
    cfg["_products"] = yaml.safe_load(pf.read_text())
    return cfg


def cmd_catalog(args) -> int:
    cfg = load_config(Path(args.config))
    start = dt.date.fromisoformat(str(cfg["period"]["start"]))
    end = dt.date.fromisoformat(str(cfg["period"]["end"]))
    client = MetadataClient(retries=int(cfg.get("execution", {}).get("retries", 4)))
    cat = catalog.build_catalog(client, cfg["_products"], cfg.get("products", {}), start, end)
    out_dir = Path(args.out_dir) if args.out_dir else cfg["_root"] / "outputs"
    out = catalog.write_catalog(cat, out_dir)
    csv_path = catalog.write_inventory_csv(cat, out_dir)
    print(catalog.summarize(cat))
    print(f"\nWrote {out}\nWrote {csv_path}")
    return 0


def cmd_regions(args) -> int:
    from . import roi  # geo stack is only needed here

    if args.action != "build":
        print("usage: seagis-extract regions build", file=sys.stderr)
        return 2
    cfg = load_config(Path(args.config))
    root = cfg["_root"]
    sources = yaml.safe_load((root / "config/boundary_sources.yaml").read_text())
    roi_cfg = yaml.safe_load((root / "config/roi_sources.yaml").read_text())
    regions_cfg = yaml.safe_load((root / cfg["regions_file"]).read_text())
    buffer_km = float(cfg["roi"]["seaward_buffer_km"])
    only = args.region or None
    res = roi.build(root, sources, roi_cfg, regions_cfg, buffer_km, only=only)
    qa_dir = root / "outputs" / "qa"
    paths = roi.write_outputs(res, root / cfg.get("roi_directory", "data/roi"), qa_dir)
    paths += roi.qa_maps(res, res["loaded"], qa_dir)
    print(f"{'REGION':14} {'SUBREGION':10} {'AREA km2':>10} {'BEFORE SPLIT':>12} {'PARTS':>5}  BBOX")
    for r in res["review"]:
        print(f"{r['region_id']:14} {r['subregion_id']:10} {r['area_km2']:>10.1f} {r['area_before_split_km2']:>12.1f} "
              f"{r['n_parts']:>5}  {r['bbox']}")
    print("\nAll ROIs are status=candidate, review_status=pending_visual_review.")
    for p in paths:
        print(f"Wrote {p}")
    return 0


def cmd_plan(args) -> int:
    import json

    from . import estimate

    if args.calibrate:
        print("--calibrate needs separate consent and is not implemented yet; planning is metadata-only.",
              file=sys.stderr)
        return 2
    cfg = load_config(Path(args.config))
    root = cfg["_root"]
    out_dir = root / "outputs"
    cat_path = out_dir / "catalog.json"
    roi_path = root / cfg.get("roi_directory", "data/roi") / "roi_candidates_v1.geojson"
    for p in (cat_path, roi_path):
        if not p.exists():
            print(f"missing {p}; run `catalog` and `regions build` first", file=sys.stderr)
            return 2
    roi_cfg = yaml.safe_load((root / "config/roi_sources.yaml").read_text())
    inputs = {name: {"path": str(p.relative_to(root)), "sha256": estimate.file_sha256(p)} for name, p in {
        "catalog": cat_path, "roi_geojson": roi_path, "extraction_config": Path(args.config).resolve(),
        "products_config": root / cfg.get("products_file", "config/products.yaml"),
        "roi_sources_config": root / "config/roi_sources.yaml"}.items()}
    cm_cfg = cfg.get("products", {}).get("copernicus", {})
    cm_fn = None
    if cm_cfg.get("enabled") and cfg["_products"].get("copernicus"):
        from . import copernicus
        from .http import MetadataClient

        specs = [dict(s, depth=cm_cfg.get("depth", s.get("depth", "surface"))) for s in cfg["_products"]["copernicus"]]
        period = {k: str(v) for k, v in cm_cfg["period"].items()}
        max_cells = int(cfg["execution"].get("max_request_cells", 10_000))

        def cm_fn(rois, geoms):
            return copernicus.plan_section(MetadataClient(), specs, period, rois, geoms, max_cells)
    (out_dir / "membership").mkdir(parents=True, exist_ok=True)
    plan = estimate.build_plan(json.loads(cat_path.read_text()), json.loads(roi_path.read_text()), cfg, inputs,
                               out_dir / "membership", pilot=roi_cfg.get("pilot_subregions"), copernicus_fn=cm_fn)
    plan_path = out_dir / "plan.json"
    tmp = plan_path.with_suffix(".json.part")
    tmp.write_text(json.dumps(plan, indent=1, default=str))
    tmp.replace(plan_path)
    estimate.write_estimate_csv(plan, out_dir / "estimate.csv")
    estimate.write_copernicus_csv(plan, out_dir / "estimate_copernicus.csv")
    estimate.request_maps(plan, json.loads(roi_path.read_text()), out_dir / "qa")
    text = estimate.summary(plan)
    (out_dir / "plan_summary.txt").write_text(text + "\n")
    print(text)
    print(f"\nWrote {plan_path}, {out_dir / 'estimate.csv'}, {out_dir / 'plan_summary.txt'}, {out_dir / 'membership'}/")
    return 0


def _not_yet(name):
    def run(_args):
        print(f"`{name}` is not implemented yet (see TASK.md).", file=sys.stderr)
        return 2
    return run


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="seagis-extract")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalog", help="resolve products from NASA CMR (metadata only)")
    c.add_argument("--config", default="config/extraction.yaml")
    c.add_argument("--out-dir", default=None)
    c.set_defaults(func=cmd_catalog)
    r = sub.add_parser("regions", help="build candidate coastal ROIs from admin boundaries")
    r.add_argument("action", choices=["build"])
    r.add_argument("--config", default="config/extraction.yaml")
    r.add_argument("--region", action="append", help="limit to region id (repeatable)")
    r.set_defaults(func=cmd_regions)
    pl = sub.add_parser("plan", help="metadata-only size/cost preflight; writes plan.json + estimate.csv")
    pl.add_argument("--config", default="config/extraction.yaml")
    pl.add_argument("--calibrate", action="store_true", help="(not implemented) approved small calibration sample")
    pl.add_argument("--max-sample-mb", type=float, default=None)
    pl.set_defaults(func=cmd_plan)
    for name in ( "pilot", "fetch", "process", "validate", "export"):
        sp = sub.add_parser(name, help="not implemented yet")
        sp.add_argument("rest", nargs="*")
        sp.set_defaults(func=_not_yet(name))
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
