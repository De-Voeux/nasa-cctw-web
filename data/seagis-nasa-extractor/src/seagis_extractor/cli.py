"""seagis-extract command line: catalog, regions build, plan, pilot, fetch (process/validate/export pending)."""
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
            return copernicus.plan_section(MetadataClient(), specs, period, rois, geoms, max_cells,
                                           static_dir=root / "data/raw/static/copernicus",
                                           no_sea_accepted=cm_cfg.get("no_sea_accepted"))
    (out_dir / "membership").mkdir(parents=True, exist_ok=True)
    pilot_report = None
    rep_path = out_dir / "pilot" / "pilot_report.json"
    if rep_path.exists() and not args.no_calibration:
        pilot_report = json.loads(rep_path.read_text())
        inputs["pilot_report"] = {"path": str(rep_path.relative_to(root)), "sha256": estimate.file_sha256(rep_path)}
        print(f"Calibrating MUR transfer from {rep_path.relative_to(root)} (pilot {pilot_report.get('status')})")
    plan = estimate.build_plan(json.loads(cat_path.read_text()), json.loads(roi_path.read_text()), cfg, inputs,
                               out_dir / "membership", pilot=roi_cfg.get("pilot_subregions"), copernicus_fn=cm_fn,
                               pilot_report=pilot_report)
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
    empty = (plan.get("copernicus") or {}).get("zones_without_sea") or []
    if empty:
        print("\nBLOCKING: these zones have no sea cell in the model grid: " + ", ".join(empty), file=sys.stderr)
        return 3
    return 0


def cmd_pilot(args) -> int:
    import json

    from . import auth, pilot

    cfg = load_config(Path(args.config))
    root = cfg["_root"]
    plan_path = Path(args.plan) if args.plan else root / "outputs/plan.json"
    plan = json.loads(plan_path.read_text())
    if args.dry_run:
        for line in pilot.dry_run_lines(plan, cfg):
            print(line)
        return 0
    try:
        pilot.verify_plan(plan, args.approve_plan, root)
    except pilot.PlanGateError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    names = auth.apply_env(root / ".env")
    if names:
        print("Loaded from .env: " + ", ".join(sorted(names)) + " (values not shown)")
    try:
        report = pilot.run_pilot(root, cfg, plan, out_dir=root / "outputs/pilot", raw_dir=root / "data/raw/pilot",
                                 membership_dir=root / "outputs/membership")
    except (pilot.FetchGuardError,) as e:
        print(f"ABORTED by download guard: {e}", file=sys.stderr)
        return 5
    except (auth.AuthError, pilot.FetchError) as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 4
    print(pilot.summary(report))
    print(f"\nWrote {root / 'outputs/pilot'}/pilot_report.json, pilot_daily.csv, pilot_summary.txt")
    return 0 if report["status"] == "PASS" else 4


MAX_CONCURRENCY = 16


def _concurrency(v: str) -> int:
    n = int(v)
    if not 1 <= n <= MAX_CONCURRENCY:
        raise argparse.ArgumentTypeError(f"must be 1..{MAX_CONCURRENCY}")
    return n


def cmd_status(args) -> int:
    import json

    from . import backfill

    cfg = load_config(Path(args.config))
    root = cfg["_root"]
    plan = json.loads((Path(args.plan) if args.plan else root / "outputs/plan.json").read_text())
    regions = None
    if args.batch is not None:
        batches = (yaml.safe_load((root / "config/fetch_batches.yaml").read_text()) or {}).get("batches") or {}
        if args.batch not in batches:
            print(f"unknown batch {args.batch}; defined: {sorted(batches)}", file=sys.stderr)
            return 2
        regions = batches[args.batch]
    units = backfill.build_units(plan, cfg, regions=regions)
    log = root / f"outputs/fetch/batch{args.batch}.log" if args.batch is not None else None
    s = backfill.status(units, root / "outputs/fetch/fetch_manifest.jsonl", root / "outputs/fetch/fetch.lock",
                        root / "data/raw/fetch", log)
    scope = f"batch {args.batch}" if args.batch is not None else "all batches"
    print(f"{scope}: {'RUNNING' if s['running'] else 'not running'}")
    print(f"  done {s['done']}/{s['units_total']} units, remaining {s['remaining']}")
    if s["running"]:
        print(f"  elapsed {s['elapsed_min']} min" + (f", finished this run {s['done_this_run']}" if s["done_this_run"] is not None else ""))
        print(f"  ETA {s['eta_min']} min" if s["eta_min"] is not None else
              "  ETA: not yet (no unit finished in this run, or no batch log to read the start from)")
        print(f"  raw daily files in progress: {s['raw_files_in_progress']}")
    if s["failed_last_attempt"] and s["running"]:
        print(f"  {len(s['failed_last_attempt'])} of the remaining failed in an earlier run and are being retried now")
    elif s["failed_last_attempt"]:
        print(f"  failed ({len(s['failed_last_attempt'])}), rerun the same fetch command to retry:")
        for k in s["failed_last_attempt"][:10]:
            print(f"    {k}")
        if len(s["failed_last_attempt"]) > 10:
            print(f"    ... and {len(s['failed_last_attempt']) - 10} more")
    return 0


def cmd_fetch(args) -> int:
    import json

    from . import auth, backfill, pilot

    cfg = load_config(Path(args.config))
    root = cfg["_root"]
    plan_path = Path(args.plan) if args.plan else root / "outputs/plan.json"
    plan = json.loads(plan_path.read_text())
    regions = list(args.region or [])
    if args.batch is not None:
        batches = (yaml.safe_load((root / "config/fetch_batches.yaml").read_text()) or {}).get("batches") or {}
        if args.batch not in batches:
            print(f"unknown batch {args.batch}; defined: {sorted(batches)}", file=sys.stderr)
            return 2
        regions += batches[args.batch]
    units = backfill.build_units(plan, cfg, regions=regions or None, sources=args.source)
    if args.dry_run:
        mur = [u for u in units if u["kind"] == "mur"]
        jobs = sum(len(u["roi"]["mur_requests"]) for u in mur)
        files = sum(len(u["roi"]["mur_requests"]) * len(u["expected"]) for u in mur)
        print(f"FETCH DRY RUN (nothing is requested): {len(units)} units = {len(mur)} MUR ROI-months "
              f"({jobs} Harmony jobs, {files} daily files) + {len(units) - len(mur)} Copernicus dataset-regions")
        for u in units[:5] + ([{"key": "..."}] if len(units) > 5 else []):
            print("  " + u["key"])
        cal = (plan.get("transfer_ratios") or {}).get("calibration")
        print(f"Calibrated: {'yes' if cal else 'NO (fetch will refuse)'}; budget {plan['execution'].get('max_download_gb')} GB; "
              f"concurrency {args.concurrency or plan['execution'].get('concurrency')}")
        return 0
    try:
        backfill.verify_fetch_plan(plan, args.approve_plan, root)
    except pilot.PlanGateError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    names = auth.apply_env(root / ".env")
    if names:
        print("Loaded from .env: " + ", ".join(sorted(names)) + " (values not shown)")
    try:
        bf = backfill.Backfill(root, cfg, plan, out_dir=root / "outputs/fetch", raw_dir=root / "data/raw/fetch",
                               processed_dir=root / "data/processed", membership_dir=root / "outputs/membership",
                               log=lambda m: print(m, flush=True), concurrency=args.concurrency)
        with backfill.RunLock(root / "outputs/fetch/fetch.lock"):
            summary = bf.run(units, max_units=args.max_units)
    except pilot.FetchGuardError as e:
        print(f"ABORTED by download guard: {e}", file=sys.stderr)
        return 5
    except (auth.AuthError, pilot.FetchError) as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 4
    print(json.dumps(summary, indent=1))
    return 0 if not summary["failed"] else 4


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
    pl.add_argument("--no-calibration", action="store_true", help="ignore outputs/pilot/pilot_report.json")
    pl.set_defaults(func=cmd_plan)
    pi = sub.add_parser("pilot", help="approved 7-day calibration run for the plan's pilot subregions")
    pi.add_argument("--config", default="config/extraction.yaml")
    pi.add_argument("--plan", default=None, help="default outputs/plan.json")
    pi.add_argument("--approve-plan", default=None, help="the PLAN SHA256 you reviewed (required)")
    pi.add_argument("--dry-run", action="store_true", help="print the exact requests; send nothing")
    pi.set_defaults(func=cmd_pilot)
    fe = sub.add_parser("fetch", help="approved full backfill (needs a pilot-calibrated plan)")
    fe.add_argument("--config", default="config/extraction.yaml")
    fe.add_argument("--plan", default=None, help="default outputs/plan.json")
    fe.add_argument("--approve-plan", default=None, help="the PLAN SHA256 you reviewed (required)")
    fe.add_argument("--region", action="append", help="limit to region id (repeatable)")
    fe.add_argument("--batch", type=int, default=None, help="run one batch from execution.batches")
    fe.add_argument("--source", choices=["all", "mur", "copernicus"], default="all")
    fe.add_argument("--concurrency", type=_concurrency, default=None,
                    help=f"units run at once (1-{MAX_CONCURRENCY}); overrides execution.concurrency, does not change the plan")
    fe.add_argument("--max-units", type=int, default=None, help="stop after N units (e.g. to measure speed)")
    fe.add_argument("--dry-run", action="store_true", help="count the work; send nothing")
    fe.set_defaults(func=cmd_fetch)
    st = sub.add_parser("status", help="read-only progress of fetch (done / remaining / ETA)")
    st.add_argument("--config", default="config/extraction.yaml")
    st.add_argument("--plan", default=None, help="default outputs/plan.json")
    st.add_argument("--batch", type=int, default=None, help="batch number; omit for every unit in the plan")
    st.set_defaults(func=cmd_status)
    for name in ("process", "validate", "export"):
        sp = sub.add_parser(name, help="not implemented yet")
        sp.add_argument("rest", nargs="*")
        sp.set_defaults(func=_not_yet(name))
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
