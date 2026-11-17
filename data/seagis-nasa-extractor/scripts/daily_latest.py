"""Daily top-up: every day each source is missing, up to the newest published one, into seagis_daily_metrics.

Runs from .github/workflows/daily-fetch.yml at 19:00 WIB. Same 48 zones, boxes, grid cells, hosts and
aggregation as the approved backfill plan (outputs/plan.json): the plan hash is verified exactly as
`seagis-extract fetch` does, and only the DATE changes. A change to the zones, sources or config
changes the plan hash, so the job refuses until a new plan is reviewed and its hash approved again.

    python scripts/daily_latest.py --approve-plan <PLAN SHA256> [--dry-run] [--confirm-host <db host>]

Per source (observed data only, never a forecast), every day of the last 7 (to yesterday, WIB) that the
database does not have yet, so a missed run or a late release is filled the next evening:
- mur_sst     the MUR granules CMR lists for those days
- gpm_imerg   the IMERG Late daily granules CMR lists for those days
- cmems_*     those days from the Copernicus analysis
- nasa_power  those days whose T2M POWER has published (one call per zone covers the last 10 days)

Nothing missing for a source -> that source is skipped. A day already in the database is not fetched again
(Copernicus fetches one date range per region, so a day it already has may be rewritten with the same value).
Secrets come from the environment (EARTHDATA_TOKEN, COPERNICUSMARINE_SERVICE_USERNAME/PASSWORD, SEAGIS_DB_DSN).
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sys
import time
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
CATCH_UP_DAYS = 7          # a missed day is filled while it is at most this many days before yesterday


def log(msg: str) -> None:
    print(msg, flush=True)


def granule_days(concept_id: str) -> list[dt.date]:
    """Metadata only: the dates of the newest granules of a collection (CMR, no account)."""
    q = urllib.parse.urlencode({"collection_concept_id": concept_id, "sort_key": "-start_date",
                                "page_size": CATCH_UP_DAYS + 5})
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(f"{CMR}?{q}", timeout=60) as r:
                entries = json.load(r)["feed"]["entry"]
            break
        except OSError:
            if attempt == 4:
                raise
            time.sleep(15 * attempt)
    days = {granule_date(e.get("title") or e.get("producer_granule_id") or "") for e in entries}
    return sorted(d for d in days if d)


def db_days(dsn: str | None, since: dt.date) -> dict[str, set[dt.date]]:
    """Complete observed days since `since`, per dataset: a day counts only when it has a value in as many zones
    as the best day of that dataset (a partly fetched day is fetched again). POWER: per T2M, since CERES lags."""
    if not dsn:
        return {}
    import psycopg
    with psycopg.connect(dsn, connect_timeout=20, application_name="seagis-daily") as c:
        rows = c.execute(
            "select dataset, date, count(distinct (region_id, subregion_id)) from public.seagis_daily_metrics "
            "where coalesce(data_type, 'observed') = 'observed' and mean is not null and date >= %s "
            "and (dataset <> 'nasa_power' or variable = 'T2M') group by dataset, date", (since,)).fetchall()
    full: dict[str, int] = {}
    for d, _, n in rows:
        full[d] = max(full.get(d, 0), n)
    out: dict[str, set[dt.date]] = {}
    for d, day, n in rows:
        if n >= full[d]:
            out.setdefault(d, set()).add(day)
    return out


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
    first_ok = yesterday - dt.timedelta(CATCH_UP_DAYS - 1)
    have = db_days(dsn, first_ok)
    log(f"today (WIB) {today}; newest in database: "
        + (", ".join(f"{k} {max(v)}" for k, v in sorted(have.items())) or "unknown"))

    def missing(dataset: str, candidates) -> list[dt.date]:
        """Days of the last CATCH_UP_DAYS (to yesterday) that the database does not have yet."""
        return sorted(d for d in candidates if first_ok <= d <= yesterday and d not in have.get(dataset, set()))

    window = [first_ok + dt.timedelta(n) for n in range(CATCH_UP_DAYS)]

    # ---------------------------------------------------------------- the days each source is missing
    days: dict[str, list[dt.date]] = {}
    if "mur" in sources:
        g = granule_days(plan["dataset"]["collection"]["concept_id"])
        log(f"mur_sst: newest granule {g[-1] if g else None}")
        days["mur"] = missing("mur_sst", g)
    if "imerg" in sources and plan.get("imerg"):
        g = granule_days(plan["imerg"]["collection"]["concept_id"])
        log(f"gpm_imerg: newest granule {g[-1] if g else None}")
        days["imerg"] = missing("gpm_imerg", g)
    specs = {s["key"]: s for s in cfg["_products"].get("copernicus", [])}
    cop_keys = [x["key"] for x in (plan.get("copernicus") or {}).get("datasets", [])
                if not specs.get(x["key"], {}).get("forecast_only")]       # the 3-day outlook has its own run
    cop_need = {k: missing(k, window) for k in cop_keys} if "copernicus" in sources else {}
    days["copernicus"] = sorted({d for v in cop_need.values() for d in v})
    if "power" in sources and plan.get("power"):
        days["power"] = missing("nasa_power", window)   # what POWER has published is known after the call
    days = {k: v for k, v in days.items() if v}
    if not days:
        log("nothing new for any source; done")
        return 0
    log("to fetch: " + "; ".join(f"{k} {', '.join(map(str, v))}" for k, v in days.items()))

    # ---------------------------------------------------------------- the approved plan, re-dated
    p = copy.deepcopy(plan)
    if "copernicus" in days:
        p["copernicus"]["period"] = {"start": str(days["copernicus"][0]), "end": str(days["copernicus"][-1])}
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
    for kind, ds in days.items():
        tag = f"{ds[0]}_{ds[-1]}"
        if kind == "mur":
            units += [{"kind": "mur", "key": f"mur/{r['region_id']}/{r['subregion_id']}/{tag}", "roi": r,
                       "month": tag, "first": ds[0], "last": ds[-1], "expected": ds} for r in p["rois"]]
        elif kind == "imerg":
            units += [{"kind": "imerg", "key": f"imerg/{r['region_id']}/{r['subregion_id']}/{tag}", "row": r,
                       "month": tag, "first": ds[0], "last": ds[-1], "expected": ds} for r in p["imerg"]["rois"]]
        elif kind == "copernicus":
            units += [{"kind": "copernicus", "key": f"{x['key']}/{reg}/{tag}", "dataset": x["key"], "region": reg}
                      for x in p["copernicus"]["datasets"] if cop_need.get(x["key"]) for reg in x["regions"]]
        elif kind == "power":
            units += [{"kind": "power", "key": f"power/{r['region_id']}/{r['subregion_id']}/{tag}", "row": r}
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

    # POWER returns the whole look-back window: keep the missing days whose T2M is published.
    import pandas as pd
    pw_files = sorted((processed / power.DATASET).rglob("*.parquet")) if (processed / power.DATASET).exists() else []
    if pw_files:
        frames = [pd.read_parquet(f) for f in pw_files]
        allp = pd.concat(frames)
        ok = allp[(allp["variable"] == "T2M") & allp["mean"].notna()]
        keep = set(missing("nasa_power", set(pd.to_datetime(ok["date"]).dt.date)))
        log(f"nasa_power: published and missing: {', '.join(map(str, sorted(keep))) or 'none'}")
        if keep:
            days["power"] = sorted(keep)
        else:
            days.pop("power", None)
        for f, d in zip(pw_files, frames):
            d = d[pd.to_datetime(d["date"]).dt.date.isin(keep)]
            if len(d):
                d.to_parquet(f, index=False)
            else:
                f.unlink()

    fetched = [d for v in days.values() for d in v]
    if not fetched:
        log("nothing new to load")
        return 1 if failed else 0
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
