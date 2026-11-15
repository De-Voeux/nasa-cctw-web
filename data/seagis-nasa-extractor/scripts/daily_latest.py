"""Daily top-up: the newest published day of each source, one day per source, into seagis_daily_metrics.

Runs from .github/workflows/daily-fetch.yml at 19:00 WIB. Same 48 zones, boxes, grid cells, hosts and
aggregation as the approved backfill plan (outputs/plan.json): the plan hash is verified exactly as
`seagis-extract fetch` does, and only the DATE changes. A change to the zones, sources or config
changes the plan hash, so the job refuses until a new plan is reviewed and its hash approved again.

    python scripts/daily_latest.py --approve-plan <PLAN SHA256> [--dry-run] [--confirm-host <db host>]

Per source (observed data only, never a forecast):
- mur_sst     newest MUR granule in CMR, if it is newer than the database
- gpm_imerg   newest IMERG Late daily granule in CMR, if newer
- cmems_*     yesterday (WIB) from the Copernicus analysis, if newer
- nasa_power  newest day of the last 10 whose T2M is published, if newer

Nothing new for a source -> that source is skipped. A day already in the database is never fetched again.
Secrets come from the environment (EARTHDATA_TOKEN, COPERNICUSMARINE_SERVICE_USERNAME/PASSWORD, SEAGIS_DB_DSN).
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seagis_extractor import __version__, auth, backfill, export, power  # noqa: E402
from seagis_extractor.catalog import granule_date  # noqa: E402
from seagis_extractor.cli import load_config  # noqa: E402

WIB = dt.timezone(dt.timedelta(hours=7))
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
OUT = ROOT / "outputs" / "daily"
POWER_LOOKBACK = 10


def log(msg: str) -> None:
    print(msg, flush=True)


def newest_granule_day(concept_id: str) -> dt.date | None:
    """Metadata only: the date of the newest granule of a collection (CMR, no account)."""
    q = urllib.parse.urlencode({"collection_concept_id": concept_id, "sort_key": "-start_date", "page_size": 5})
    with urllib.request.urlopen(f"{CMR}?{q}", timeout=60) as r:
        entries = json.load(r)["feed"]["entry"]
    days = [granule_date(e.get("title") or e.get("producer_granule_id") or "") for e in entries]
    days = [d for d in days if d]
    return max(days) if days else None


def db_latest(dsn: str | None) -> dict[str, dt.date]:
    """Newest observed day with a value, per dataset (POWER: per T2M, since CERES fields lag)."""
    if not dsn:
        return {}
    import psycopg
    with psycopg.connect(dsn, connect_timeout=20, application_name="seagis-daily") as c:
        rows = c.execute(
            "select dataset, max(date) from public.seagis_daily_metrics "
            "where coalesce(data_type, 'observed') = 'observed' and mean is not null "
            "and (dataset <> 'nasa_power' or variable = 'T2M') group by dataset").fetchall()
    return {d: m for d, m in rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/extraction.yaml")
    ap.add_argument("--plan", default=None, help="default outputs/plan.json")
    ap.add_argument("--approve-plan", required=True, help="the reviewed PLAN SHA256")
    ap.add_argument("--sources", default="mur,imerg,copernicus,power")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD in WIB (default: now); for tests and reruns")
    ap.add_argument("--dry-run", action="store_true", help="pick the days and print the work; download and write nothing")
    ap.add_argument("--confirm-host", default=None, help="must equal the DSN host to write")
    args = ap.parse_args(argv)

    cfg = load_config(ROOT / args.config)
    root = cfg["_root"]
    plan = json.loads((Path(args.plan) if args.plan else root / "outputs/plan.json").read_text())
    backfill.verify_fetch_plan(plan, args.approve_plan, root)      # same gate as `seagis-extract fetch`
    auth.apply_env(root / ".env")                                  # local runs; CI passes env vars
    sources = set(args.sources.split(","))
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(WIB).date()
    yesterday = today - dt.timedelta(1)

    try:
        dsn = export.dsn_from_env()
    except export.ExportError:
        dsn = None
    if not args.dry_run and not dsn:
        log("REFUSED: SEAGIS_DB_DSN is not set")
        return 2
    if dsn and not args.dry_run and args.confirm_host != export.dsn_host(dsn):
        log("REFUSED: --confirm-host does not match the DSN host; nothing fetched")
        return 2
    have = db_latest(dsn)
    log(f"today (WIB) {today}; newest in database: " + (", ".join(f"{k} {v}" for k, v in sorted(have.items())) or "unknown"))

    def newer(dataset: str, day: dt.date | None) -> bool:
        return day is not None and day <= yesterday and (dataset not in have or day > have[dataset])

    # ---------------------------------------------------------------- pick one day per source
    days: dict[str, dt.date] = {}
    if "mur" in sources:
        d = newest_granule_day(plan["dataset"]["collection"]["concept_id"])
        log(f"mur_sst: newest granule {d}")
        if newer("mur_sst", d):
            days["mur"] = d
    if "imerg" in sources and plan.get("imerg"):
        d = newest_granule_day(plan["imerg"]["collection"]["concept_id"])
        log(f"gpm_imerg: newest granule {d}")
        if newer("gpm_imerg", d):
            days["imerg"] = d
    specs = {s["key"]: s for s in cfg["_products"].get("copernicus", [])}
    cop_keys = [x["key"] for x in (plan.get("copernicus") or {}).get("datasets", [])
                if not specs.get(x["key"], {}).get("forecast_only")]       # the 3-day outlook has its own run
    if "copernicus" in sources and cop_keys:
        if any(newer(k, yesterday) for k in cop_keys):
            days["copernicus"] = yesterday
    if "power" in sources and plan.get("power") and newer("nasa_power", yesterday):
        days["power"] = yesterday            # the newest published day inside the window is chosen after the call
    if not days:
        log("nothing new for any source; done")
        return 0
    log("to fetch: " + ", ".join(f"{k} {v}" for k, v in days.items()))

    # ---------------------------------------------------------------- the approved plan, re-dated
    p = copy.deepcopy(plan)
    p["copernicus"]["period"] = {"start": str(days.get("copernicus", yesterday)), "end": str(days.get("copernicus", yesterday))}
    pw_start = yesterday - dt.timedelta(POWER_LOOKBACK - 1)
    if p.get("power"):
        spec = cfg["_products"]["power"]
        p0 = {k: dt.date.fromisoformat(v) for k, v in plan["power"]["period"].items()}
        p["power"]["period"] = {"start": str(pw_start), "end": str(yesterday)}
        for row in p["power"]["rois"]:
            if power.point_url(spec, row["lat"], row["lon"], p0["start"], p0["end"]) != row["url"]:
                raise SystemExit(f"POWER URL of {row['subregion_id']} is not the approved one; refusing")
            row["url"] = power.point_url(spec, row["lat"], row["lon"], pw_start, yesterday)  # same point, new dates
    units = []
    for kind, d in days.items():
        month = d.isoformat()
        if kind == "mur":
            units += [{"kind": "mur", "key": f"mur/{r['region_id']}/{r['subregion_id']}/{month}", "roi": r,
                       "month": month, "first": d, "last": d, "expected": [d]} for r in p["rois"]]
        elif kind == "imerg":
            units += [{"kind": "imerg", "key": f"imerg/{r['region_id']}/{r['subregion_id']}/{month}", "row": r,
                       "month": month, "first": d, "last": d, "expected": [d]} for r in p["imerg"]["rois"]]
        elif kind == "copernicus":
            units += [{"kind": "copernicus", "key": f"{x['key']}/{reg}/{month}", "dataset": x["key"], "region": reg}
                      for x in p["copernicus"]["datasets"] if x["key"] in cop_keys and newer(x["key"], d)
                      for reg in x["regions"]]
        elif kind == "power":
            units += [{"kind": "power", "key": f"power/{r['region_id']}/{r['subregion_id']}/{month}", "row": r}
                      for r in p["power"]["rois"]]
    log(f"{len(units)} units: " + ", ".join(f"{k} {sum(1 for u in units if u['kind'] == k)}" for k in days))
    if args.dry_run:
        log("DRY RUN: nothing downloaded or written")
        return 0

    run_dir = OUT / today.isoformat()
    processed = run_dir / "processed"
    bf = backfill.Backfill(root, cfg, p, out_dir=run_dir, raw_dir=run_dir / "raw", processed_dir=processed,
                           membership_dir=root / "outputs/membership", log=log)
    bf.run(units)
    failed = [r for r in bf.manifest.items.values() if r.get("status") != "ok"]
    log(f"fetch: {len(units) - len(failed)} ok, {len(failed)} failed")

    # POWER returns the whole look-back window: keep only its newest day with T2M published.
    import pandas as pd
    pw_files = sorted((processed / power.DATASET).rglob("*.parquet")) if (processed / power.DATASET).exists() else []
    if pw_files:
        frames = [pd.read_parquet(f) for f in pw_files]
        allp = pd.concat(frames)
        ok = allp[(allp["variable"] == "T2M") & allp["mean"].notna()]
        best = pd.to_datetime(ok["date"]).dt.date.max() if len(ok) else None
        if best is None or ("nasa_power" in have and best <= have["nasa_power"]):
            log(f"nasa_power: newest published day {best} is not new; skipped")
            for f in pw_files:
                f.unlink()
        else:
            days["power"] = best
            log(f"nasa_power: newest published day {best}")
            for f, d in zip(pw_files, frames):
                d[pd.to_datetime(d["date"]).dt.date == best].to_parquet(f, index=False)

    fetched = list(days.values())
    pe = copy.deepcopy(plan)
    pe["period"] = {"start": str(min(fetched)), "end": str(max(fetched))}   # export keeps rows inside this window
    roi_path = root / cfg.get("roi_directory", "data/roi") / "roi_candidates_v1.geojson"
    try:
        inp = export.load_inputs(root, pe, processed, roi_path)
    except export.ExportError as e:
        log(f"nothing to export: {e}")
        return 1 if failed else 0
    for line in export.summary_lines(inp):
        log(line)
    import psycopg
    with psycopg.connect(dsn, connect_timeout=20, application_name="seagis-daily") as conn:
        out = export.export(conn, inp, pe, None, tool_version=f"{__version__}+daily_latest")
    log(json.dumps(out, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
