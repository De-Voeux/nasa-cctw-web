"""Load validated daily Parquet outputs into PostgreSQL / Supabase.

Connection: a Postgres connection string in the environment (`SEAGIS_DB_DSN`, read from .env);
never on the command line, never printed. Writing needs `--confirm-host <host>` matching the DSN,
so a run can never land on a database the operator did not name.

Upsert key: (region_id, subregion_id, geometry_version, dataset, variable, date). Re-running an
export updates rows in place; nothing is deleted.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import urllib.parse
from pathlib import Path

import yaml

DSN_ENV = "SEAGIS_DB_DSN"
MIGRATIONS_TABLE = "seagis_schema_migrations"
EXTRACTOR_MIGRATION = "20261115000000_seagis_environment.sql"
EXTRACTOR_MIGRATIONS = (
    EXTRACTOR_MIGRATION,
    "20261115000005_seagis_forecast.sql",
    "20261115010000_seagis_more_sources.sql",
    "20261115020000_seagis_monthly_metrics.sql",
)

METRIC_COLUMNS = ["region_id", "subregion_id", "geometry_version", "dataset", "variable", "date", "data_type", "units",
                  "mean", "min", "max", "std", "valid_pixel_count", "roi_pixel_count", "coverage_fraction",
                  "area_weighted", "source_granule", "product_version", "qc_flags"]
METRIC_KEY = ["region_id", "subregion_id", "geometry_version", "dataset", "variable", "date", "data_type"]

# Display labels written to the DB (decided 2026-11-15). Labels only: every pair is the same unit,
# so no value changes. Parquet in data/processed keeps the source's own unit strings.
DISPLAY_UNITS = {
    "degree_C": "°C", "degrees_C": "°C", "C": "°C",
    "kelvin": "°C",             # MUR analysis_error is a temperature difference: 1 K = 1 °C
    "mmol m-3": "mmol/m³",
    "1e-3": "PSU",              # Copernicus salinity (practical salinity, ~ PSU)
    "m s-1": "m/s", "m/s": "m/s",
    "degree": "°", "Degrees": "°",
    "mm/day": "mm/day",
    "MJ/m^2/day": "MJ/m²/day",
    "%": "%",
}
# unitless variables, labelled by what they are
DISPLAY_UNITS_BY_VARIABLE = {"ph": "pH", "current_steadiness": "0–1"}


def display_unit(variable: str, unit: str) -> str:
    if variable in DISPLAY_UNITS_BY_VARIABLE:
        return DISPLAY_UNITS_BY_VARIABLE[variable]
    if unit not in DISPLAY_UNITS:
        raise ExportError(f"no display label for unit {unit!r} ({variable}); add it to export.DISPLAY_UNITS")
    return DISPLAY_UNITS[unit]


class ExportError(RuntimeError):
    pass


def dsn_from_env() -> str:
    dsn = os.environ.get(DSN_ENV, "").strip().strip('"').strip("'")
    if not dsn:
        raise ExportError(f"{DSN_ENV} is not set. Put the Postgres connection string in .env (never in chat or code).")
    if urllib.parse.urlsplit(dsn).scheme not in ("postgres", "postgresql"):
        raise ExportError(f"{DSN_ENV} must be a postgresql:// connection string (an https project URL cannot run SQL)")
    return dsn


def dsn_host(dsn: str) -> str:
    return urllib.parse.urlsplit(dsn).hostname or ""


def describe(dsn: str) -> str:
    """Host / port / database / user, no password."""
    u = urllib.parse.urlsplit(dsn)
    return f"host={u.hostname} port={u.port or 5432} db={u.path.lstrip('/') or '-'} user={u.username or '-'}"


# ---------------------------------------------------------------- inputs

def load_inputs(root: Path, plan: dict, processed_dir: Path, roi_path: Path) -> dict:
    """Everything to load, read from disk only. Excluded regions (config/fetch_batches.yaml) are skipped."""
    import pandas as pd

    cfg_regions = yaml.safe_load((root / "config/regions.yaml").read_text())["regions"]
    batches = yaml.safe_load((root / "config/fetch_batches.yaml").read_text()) or {}
    excluded = set(batches.get("excluded") or [])
    regions = [{"region_id": r["id"], "country": r["country"], "name": r["name"], "status": r["status"],
                "review_notes": r.get("review_notes"), "excluded": r["id"] in excluded} for r in cfg_regions]

    plan_zones = {(r["region_id"], r["subregion_id"], r["geometry_version"]) for r in plan["rois"]}
    gj = json.loads(roi_path.read_text())
    zones = []
    import shapely.geometry
    for f in gj["features"]:
        p = f["properties"]
        key = (p["region_id"], p["subregion_id"], p["geometry_version"])
        if key not in plan_zones or p["region_id"] in excluded:
            continue
        w, s, e, n = shapely.geometry.shape(f["geometry"]).bounds
        zones.append({"region_id": key[0], "subregion_id": key[1], "geometry_version": key[2],
                      "name": p.get("name") or key[1], "status": p.get("status") or "candidate",
                      "buffer_km": p.get("buffer_km"), "area_km2": p.get("area_km2"),
                      "bbox_w": w, "bbox_s": s, "bbox_e": e, "bbox_n": n, "source": p.get("source"),
                      "source_sha256": p.get("source_sha256"), "method": p.get("method"),
                      "review_notes": p.get("review_notes") or None, "built_at": p.get("built_at") or None})
    zone_keys = {(z["region_id"], z["subregion_id"], z["geometry_version"]) for z in zones}

    start, end = (dt.date.fromisoformat(plan["period"][k]) for k in ("start", "end"))
    files = sorted(processed_dir.rglob("*.parquet"))
    frames, skipped = [], {"excluded_region": 0, "zone_not_in_plan": 0, "outside_period": 0}
    for f in files:
        d = pd.read_parquet(f)
        if d.empty:
            continue
        d["date"] = pd.to_datetime(d["date"]).dt.date
        keep = ~d["region_id"].isin(excluded)
        skipped["excluded_region"] += int((~keep).sum())
        inz = d.apply(lambda r: (r["region_id"], r["subregion_id"], r["geometry_version"]) in zone_keys, axis=1)
        skipped["zone_not_in_plan"] += int((keep & ~inz).sum())
        keep &= inz
        inp = (d["date"] >= start) & (d["date"] <= end)
        skipped["outside_period"] += int((keep & ~inp).sum())
        frame = d[keep & inp].copy()
        if "data_type" not in frame:
            frame["data_type"] = "observed"
        frames.append(frame)
    metrics = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=METRIC_COLUMNS)
    if "data_type" not in metrics:
        metrics["data_type"] = "observed"
    metrics["data_type"] = metrics["data_type"].fillna("observed")
    metrics = metrics[METRIC_COLUMNS].copy()
    if len(metrics):
        pairs = metrics[["variable", "units"]].drop_duplicates()
        label = {(v, u): display_unit(v, u) for v, u in pairs.itertuples(index=False)}
        metrics["units"] = [label[(v, u)] for v, u in zip(metrics["variable"], metrics["units"])]
    dup = int(metrics.duplicated(METRIC_KEY).sum())
    if dup:
        raise ExportError(f"{dup} duplicate (zone, dataset, variable, date) rows in data/processed; fix before export")
    return {"regions": regions, "zones": zones, "metrics": metrics, "files": len(files), "skipped": skipped,
            "excluded": sorted(excluded), "period": (start, end)}


def summary_lines(inp: dict) -> list[str]:
    m = inp["metrics"]
    out = [f"regions {len(inp['regions'])} (excluded: {', '.join(inp['excluded']) or 'none'}), "
           f"zones {len(inp['zones'])}, parquet files {inp['files']}, metric rows {len(m)}"]
    if len(m):
        g = m.groupby(["dataset", "variable"]).agg(rows=("date", "size"), zones=("subregion_id", "nunique"),
                                                   first=("date", "min"), last=("date", "max"),
                                                   units=("units", "first"))
        for (ds, var), r in g.iterrows():
            out.append(f"  {ds:14} {var:19} {r['units']:10} rows {r['rows']:6}  zones {r['zones']:3}  "
                       f"{r['first']}..{r['last']}")
    sk = {k: v for k, v in inp["skipped"].items() if v}
    if sk:
        out.append("  skipped rows: " + ", ".join(f"{k} {v}" for k, v in sk.items()))
    return out


# ---------------------------------------------------------------- database

def migration_files(migrations_dir: Path) -> list[Path]:
    """Return only the extractor-owned migration.

    The repository also contains the web application's RAG and environment
    migrations. The extractor must never apply those or maintain a second
    migration history for them.
    """
    return [migrations_dir / n for n in EXTRACTOR_MIGRATIONS if (migrations_dir / n).is_file()]


def apply_migrations(conn, migrations_dir: Path, log=print) -> list[str]:
    """Apply each migration file once, in name order, recorded in seagis_schema_migrations."""
    applied = []
    with conn.cursor() as cur:
        cur.execute(f"create table if not exists public.{MIGRATIONS_TABLE} "
                    "(name text primary key, applied_at timestamptz not null default now())")
        # bookkeeping only: RLS on with no policy, so the anon/authenticated API roles cannot touch it
        cur.execute(f"alter table public.{MIGRATIONS_TABLE} enable row level security")
        cur.execute(f"select name from public.{MIGRATIONS_TABLE}")
        done = {r[0] for r in cur.fetchall()}
        for p in migration_files(migrations_dir):
            if p.name in done:
                continue
            cur.execute(p.read_text())
            cur.execute(f"insert into public.{MIGRATIONS_TABLE} (name) values (%s)", (p.name,))
            applied.append(p.name)
            log(f"applied migration {p.name}")
    return applied


def _upsert(cur, table: str, rows: list[dict], key: list[str]) -> int:
    if not rows:
        return 0
    cols = list(rows[0])
    upd = [c for c in cols if c not in key]
    sql = (f"insert into public.{table} ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
           f"on conflict ({', '.join(key)}) do update set "
           + ", ".join(f"{c} = excluded.{c}" for c in upd) + ", updated_at = now()")
    cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
    return len(rows)


def _copy_metrics(cur, metrics, plan_sha256: str, run_id) -> int:
    """COPY into a temp table, then one upsert into seagis_daily_metrics."""
    import math
    cur.execute("create temp table _seagis_metrics (like public.seagis_daily_metrics including defaults) on commit drop")
    cols = METRIC_COLUMNS + ["plan_sha256", "load_run_id"]
    n = 0
    with cur.copy(f"copy _seagis_metrics ({', '.join(cols)}) from stdin") as cp:
        for rec in metrics.itertuples(index=False):
            row = []
            for v in rec:
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    row.append(None)
                elif hasattr(v, "item"):
                    row.append(v.item())
                else:
                    row.append(v)
            cp.write_row(row + [plan_sha256, run_id])
            n += 1
    upd = [c for c in cols if c not in METRIC_KEY]
    cur.execute(f"insert into public.seagis_daily_metrics ({', '.join(cols)}) select {', '.join(cols)} from _seagis_metrics "
                f"on conflict ({', '.join(METRIC_KEY)}) do update set "
                + ", ".join(f"{c} = excluded.{c}" for c in upd) + ", loaded_at = now()")
    return n


def export(conn, inp: dict, plan: dict, migrations_dir: Path | None = None, tool_version: str = "", log=print) -> dict:
    """One transaction: migrations (optional), regions, zones, metrics, load-run record."""
    with conn.transaction():
        applied = apply_migrations(conn, migrations_dir, log) if migrations_dir else []
        with conn.cursor() as cur:
            start, end = inp["period"]
            cur.execute("insert into public.seagis_load_runs (plan_sha256, period_start, period_end, files, tool_version, notes) "
                        "values (%s, %s, %s, %s, %s, %s) returning run_id",
                        (plan["plan_sha256"], start, end, inp["files"], tool_version,
                         f"excluded regions: {', '.join(inp['excluded']) or 'none'}"))
            run_id = cur.fetchone()[0]
            nr = _upsert(cur, "seagis_regions", inp["regions"], ["region_id"])
            nz = _upsert(cur, "seagis_zones", inp["zones"], ["region_id", "subregion_id", "geometry_version"])
            nm = _copy_metrics(cur, inp["metrics"], plan["plan_sha256"], run_id)
            cur.execute("update public.seagis_load_runs set finished_at = now(), rows_upserted = %s where run_id = %s",
                        (nm, run_id))
            cur.execute("select count(*) from public.seagis_daily_metrics")
            total = cur.fetchone()[0]
    return {"run_id": str(run_id), "migrations_applied": applied, "regions": nr, "zones": nz,
            "metrics_upserted": nm, "metrics_in_db": total}
