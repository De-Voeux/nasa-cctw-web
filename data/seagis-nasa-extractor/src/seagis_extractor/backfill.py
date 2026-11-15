"""`fetch`: the approved full backfill.

Gate: the same checks as `pilot`, plus the plan must be calibrated from a PASSing pilot.

Work units (each resumable, recorded in outputs/fetch/fetch_manifest.jsonl):
- MUR: one unit per ROI x month. One Harmony job per approved request box for that month;
  every file is guarded (cells must be the approved box's cells) and checked, the day's tiles
  are aggregated over the ROI's sea cells (MUR mask), the month is written to Parquet, and the
  raw NetCDF files are deleted (raw_retention: discard_after_validation).
- Copernicus: one unit per dataset x region, whole period, surface level, region box only.
  Each ROI is cropped to its own plan cells, aggregated over static-mask sea cells, written to
  Parquet. Pairs listed in unavailable_by_decision write no rows.

Order: pilot regions first, so usable data arrives early. A guard violation stops everything;
other unit errors are retried, then recorded as failed while the run continues.
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import os
import shutil
import time
import urllib.parse
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from . import auth, estimate, process, validate
from .catalog import granule_date
from .fetch import (ByteBudget, FetchError, FetchGuardError, HarmonyClient, copernicus_open, crop_to_cells)
from .manifest import Manifest
from .pilot import PlanGateError, verify_plan

CRITICAL_MUR_CHECKS = {"mur.grid_origin", "mur.timestamp", "mur.units", "mur.value_range"}


def verify_fetch_plan(plan: dict, approve: str | None, root: Path) -> None:
    verify_plan(plan, approve, root)
    if not (plan.get("transfer_ratios") or {}).get("calibration"):
        raise PlanGateError("plan is not calibrated from a pilot; run `pilot`, then `plan`, then approve the new hash")


def _months(start: dt.date, end: dt.date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        first = max(start, dt.date(y, m, 1))
        last = min(end, dt.date(y, m, calendar.monthrange(y, m)[1]))
        yield f"{y:04d}-{m:02d}", first, last
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def build_units(plan: dict, cfg: dict, regions: list[str] | None = None, sources: str = "all") -> list[dict]:
    start, end = (dt.date.fromisoformat(plan["period"][k]) for k in ("start", "end"))
    first_regions = list((cfg.get("roi") or {}).get("pilot_first") or [])
    order = first_regions + [r["region_id"] for r in plan["rois"] if r["region_id"] not in first_regions]
    order = list(dict.fromkeys(order))
    if regions:
        order = [r for r in order if r in regions]
    missing = defaultdict(set)
    for row in plan["rows"]:
        missing[(row["region_id"], row["subregion_id"])] |= set(row["missing_dates"])
    units = []
    for reg in order:
        if sources in ("all", "mur"):
            for roi in (r for r in plan["rois"] if r["region_id"] == reg):
                key = (roi["region_id"], roi["subregion_id"])
                for month, first, last in _months(start, end):
                    days = [first + dt.timedelta(n) for n in range((last - first).days + 1)]
                    exp = [d for d in days if d.isoformat() not in missing[key]]
                    if exp:
                        units.append({"kind": "mur", "key": f"mur/{key[0]}/{key[1]}/{month}", "roi": roi,
                                      "month": month, "first": first, "last": last, "expected": exp})
        if sources in ("all", "copernicus"):
            for d in (plan.get("copernicus") or {}).get("datasets", []):
                if reg in d["regions"]:
                    units.append({"kind": "copernicus", "key": f"{d['key']}/{reg}", "dataset": d["key"], "region": reg})
    return units


def _write_parquet(rows: list[dict], path: Path) -> dict:
    import pandas as pd

    cols = [c for c, _ in estimate.FINAL_SCHEMA]
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for c in ("valid_pixel_count", "roi_pixel_count"):
        df[c] = df[c].astype("int32")
    for c in ("coverage_fraction", "mean", "min", "max", "std"):
        df[c] = df[c].astype("float32")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    df.to_parquet(part, index=False)
    part.replace(path)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": len(df)}


def _open_nc(path: Path):
    import xarray as xr
    return xr.open_dataset(path, engine="h5netcdf", mask_and_scale=True).load()


class Backfill:
    def __init__(self, root: Path, cfg: dict, plan: dict, *, out_dir: Path, raw_dir: Path, processed_dir: Path,
                 membership_dir: Path, harmony: HarmonyClient | None = None, cm_opener=None, log=print,
                 sleep=time.sleep, concurrency: int | None = None):
        self.root, self.cfg, self.plan = root, cfg, plan
        self.out_dir, self.raw_dir, self.processed_dir, self.membership_dir = out_dir, raw_dir, processed_dir, membership_dir
        self.log, self.sleep = log, sleep
        self.manifest = Manifest(out_dir / "fetch_manifest.jsonl")
        ex = plan["execution"]
        self.retries = int(ex.get("retries", 3))
        # speed only: how many units run at once; not part of what is downloaded, so not in the plan hash
        self.concurrency = int(concurrency or ex.get("concurrency", 2))
        self.discard_raw = ex.get("raw_retention", "discard_after_validation") == "discard_after_validation"
        self.grid = estimate.MurGrid()
        self.cid = plan["dataset"]["collection"]["concept_id"]
        self.variables = list(plan["dataset"]["variables"])
        already = sum(int(r.get("bytes", 0)) for r in self.manifest.items.values() if r.get("status") == "ok")
        budget = ByteBudget(int(float(ex.get("max_download_gb", 20)) * 1e9), used=already)
        if harmony is None:
            allowed = {tuple(q["bbox_w_s_e_n"]) for r in plan["rois"] for q in r["mur_requests"]}
            harmony = HarmonyClient(auth.earthdata_token(), allowed, budget)
        self.harmony = harmony
        self.cm_opener = cm_opener
        self.cm_specs = {s["key"]: s for s in cfg["_products"].get("copernicus", [])}
        self.cm_plan = {d["key"]: d for d in (plan.get("copernicus") or {}).get("datasets", [])}

    # ------------------------------------------------ MUR
    def mur_unit(self, u: dict) -> dict:
        roi = u["roi"]
        key = (roi["region_id"], roi["subregion_id"])
        per_day, downloaded, issues, raw = defaultdict(list), 0, [], []
        for q in roi["mur_requests"]:
            tile = "t{}_{}".format(*q.get("tile", [0, 0]))
            job = self.harmony.wait(self.harmony.submit(self.cid, self.variables, q["bbox_w_s_e_n"], u["first"], u["last"]))
            got = set()
            for link in self.harmony.data_links(job):
                name = Path(urllib.parse.urlsplit(link["href"]).path).name
                d = granule_date(name)
                if d not in u["expected"]:
                    issues.append(f"unexpected granule {name}")
                    continue
                dest = self.raw_dir / "mur" / key[0] / key[1] / tile / name
                info = self.harmony.download(link["href"], dest)
                downloaded += info["bytes"]
                raw.append(dest)
                ds = _open_nc(dest)
                try:
                    validate.mur_guard(ds, q)
                except FetchGuardError:
                    dest.unlink(missing_ok=True)
                    raise
                bad = [c for c in validate.mur_checks(ds, q, self.grid, d)
                       if c["status"] == "FAIL" and c["check"] in CRITICAL_MUR_CHECKS]
                if bad:
                    raise FetchError(f"{name}: " + "; ".join(f"{c['check']}: {c['detail']}" for c in bad))
                per_day[d].append((ds, name))
                got.add(d)
            if got != set(u["expected"]):
                issues.append(f"{tile}: {len(got)}/{len(u['expected'])} days returned")
        mem = process.read_membership(self.membership_dir /
                                      f"mur_sst__{key[0]}__{key[1]}__{roi['geometry_version']}.csv.gz")
        rows, n_tiles = [], len(roi["mur_requests"])
        for d in sorted(per_day):
            if len(per_day[d]) != n_tiles:
                issues.append(f"{d}: {len(per_day[d])}/{n_tiles} tiles")
                continue
            r, _ = process.aggregate_mur([x for x, _ in per_day[d]], mem, self.grid, roi, d,
                                         ";".join(n for _, n in per_day[d]))
            rows += [x for x in r if x["variable"] in estimate.ASSUMPTIONS["output_variables"]]
        out = _write_parquet(rows, self.processed_dir / "mur_sst" / key[0] / key[1] / f"{u['month']}.parquet")
        if self.discard_raw:
            for p in raw:
                p.unlink(missing_ok=True)
        days = len({r["date"] for r in rows})
        return out | {"bytes": downloaded, "days": days, "expected_days": len(u["expected"]), "issues": issues}

    # ------------------------------------------------ Copernicus
    def copernicus_unit(self, u: dict) -> dict:
        spec, d_plan = self.cm_specs[u["dataset"]], self.cm_plan[u["dataset"]]
        region = d_plan["regions"][u["region"]]
        start, end = (dt.date.fromisoformat(self.plan["copernicus"]["period"][k]) for k in ("start", "end"))
        if self.cm_opener is None and not auth.copernicus_configured():
            raise auth.AuthError("Copernicus Marine credentials not found (.env or `copernicusmarine login`)")
        step_lat, step_lon = d_plan["grid"]["lat_step"], d_plan["grid"]["lon_step"]
        ds = copernicus_open(spec, region["bbox_w_s_e_n"], start, end, opener=self.cm_opener)
        validate.copernicus_guard(ds, region["bbox_w_s_e_n"], step_lat, step_lon)
        ds = crop_to_cells(ds, region["bbox_w_s_e_n"], step_lat, step_lon).load()
        if "depth" in ds.dims:
            ds = ds.isel(depth=0, drop=False)
        dates = [start + dt.timedelta(n) for n in range((end - start).days + 1)]
        rois = {(r["region_id"], r["subregion_id"]): r for r in self.plan["rois"] if r["region_id"] == u["region"]}
        written, issues = [], []
        for row in (r for r in d_plan["rois"] if r["region_id"] == u["region"]):
            key = (row["region_id"], row["subregion_id"])
            if row.get("available") is False:
                issues.append(f"{key[1]}: unavailable by decision")
                continue
            bbox = rois[key]["request"]["bbox_w_s_e_n"]
            sub = crop_to_cells(ds, bbox, step_lat, step_lon)
            mem = process.read_membership(self.membership_dir / f"{u['dataset']}__{key[0]}__{key[1]}__v1.csv.gz")
            bad = [c for c in validate.copernicus_checks(sub, u["dataset"], row, dates, mem) if c["status"] == "FAIL"]
            if bad:
                raise FetchError(f"{u['dataset']} {key[1]}: " + "; ".join(f"{c['check']}: {c['detail']}" for c in bad))
            rows = process.aggregate_copernicus(sub, mem, rois[key], u["dataset"], spec["dataset_id"])
            written.append(_write_parquet(rows, self.processed_dir / u["dataset"] / key[0] / f"{key[1]}.parquet"))
        if not written:
            return {"path": "", "sha256": "", "rows": 0, "bytes": 0, "issues": issues, "files": []}
        first = written[0]
        return {"path": first["path"], "sha256": first["sha256"], "rows": sum(w["rows"] for w in written),
                "files": written, "bytes": 0, "issues": issues,
                "transfer_bytes_planned": region["transfer_bytes"]}

    # ------------------------------------------------ driver
    def _run_one(self, u: dict) -> dict:
        for attempt in range(1, self.retries + 1):
            try:
                t0 = time.monotonic()
                res = self.mur_unit(u) if u["kind"] == "mur" else self.copernicus_unit(u)
                res["seconds"] = round(time.monotonic() - t0, 1)
                return self.manifest.record(u["key"], status="ok", attempt=attempt, **res)
            except (FetchGuardError, auth.AuthError):
                raise
            except Exception as e:  # noqa: BLE001 - recorded, retried, then the run moves on
                if attempt == self.retries:
                    return self.manifest.record(u["key"], status="failed", attempt=attempt,
                                                error=f"{type(e).__name__}: {str(e)[:500]}")
                self.sleep(min(60, 2 ** attempt))

    def _done(self, u: dict) -> bool:
        return unit_files_ok(self.manifest.items.get(u["key"]))

    def run(self, units: list[dict], max_units: int | None = None) -> dict:
        free = shutil.disk_usage(self.root).free
        if free < 2e9:
            raise FetchError(f"only {free / 1e9:.1f} GB free on disk; need at least 2 GB")
        if self.discard_raw and self.raw_dir.exists():
            shutil.rmtree(self.raw_dir)          # leftovers of interrupted units; they are re-fetched
        todo = [u for u in units if not self._done(u)]
        skipped = len(units) - len(todo)
        if max_units is not None:
            todo = todo[:max_units]
        self.log(f"{len(units)} units, {skipped} already done, running {len(todo)}")
        t0, results = time.monotonic(), []

        def report(rec, u, i, n):
            el = time.monotonic() - t0
            eta = el / i * (n - i) if i else 0
            self.log(f"[{i}/{n}] {u['key']}: {rec['status']} rows={rec.get('rows', 0)} "
                     f"MB={int(rec.get('bytes', 0)) / 1e6:.2f} total={self.harmony.budget.used / 1e6:.1f}MB "
                     f"elapsed={el / 60:.1f}m eta={eta / 60:.1f}m" + (f" ERROR {rec.get('error')}" if rec['status'] != 'ok' else ""))

        mur = [u for u in todo if u["kind"] == "mur"]
        cm = [u for u in todo if u["kind"] == "copernicus"]
        n = len(todo)
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futs = {pool.submit(self._run_one, u): u for u in mur}
            pending = set(futs)
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)   # report each unit as it lands
                for f in done:
                    if f.exception():
                        for p in pending:
                            p.cancel()
                        raise f.exception()
                    results.append(f.result())
                    report(results[-1], futs[f], len(results), n)
        for u in cm:
            results.append(self._run_one(u))
            report(results[-1], u, len(results), n)
        summary = {"units_total": len(units), "units_skipped_done": skipped, "units_run": len(results),
                   "ok": sum(r["status"] == "ok" for r in results), "failed": [r["key"] for r in results if r["status"] != "ok"],
                   "with_issues": {r["key"]: r["issues"] for r in results if r.get("issues")},
                   "mur_bytes_this_run": sum(int(r.get("bytes", 0)) for r in results if r["key"].startswith("mur/")),
                   "rows_this_run": sum(int(r.get("rows", 0)) for r in results),
                   "minutes": round((time.monotonic() - t0) / 60, 1), "plan_sha256": self.plan["plan_sha256"]}
        self.out_dir.mkdir(parents=True, exist_ok=True)
        import json
        (self.out_dir / "fetch_summary.json").write_text(json.dumps(summary, indent=1))
        return summary


def unit_files_ok(rec: dict | None) -> bool:
    """A manifest record is a finished unit whose output files still match their SHA-256."""
    if not rec or rec.get("status") != "ok":
        return False
    files = rec.get("files") or ([{"path": rec["path"], "sha256": rec["sha256"]}] if rec.get("path") else [])
    return all(Path(f["path"]).exists() and hashlib.sha256(Path(f["path"]).read_bytes()).hexdigest() == f["sha256"]
               for f in files)


def status(units: list[dict], manifest_path: Path, lock_path: Path, raw_dir: Path, log_path: Path | None = None,
           now: float | None = None) -> dict:
    """Read-only progress of a (running) fetch: nothing is requested, nothing is written."""
    import os
    import re
    now = time.time() if now is None else now
    items = Manifest(manifest_path).items
    keys = [u["key"] for u in units]
    done = [k for k in keys if unit_files_ok(items.get(k))]
    failed = [k for k in keys if (items.get(k) or {}).get("status") == "failed"]
    running, started = False, None
    if lock_path.exists():
        try:
            os.kill(int(lock_path.read_text().strip()), 0)
            running, started = True, lock_path.stat().st_mtime
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    done_at_start = None
    if log_path and log_path.exists():
        hits = re.findall(r"^(\d+) units, (\d+) already done, running (\d+)$", log_path.read_text(), re.M)
        if hits:
            done_at_start = int(hits[-1][1])
    out = {"running": running, "units_total": len(keys), "done": len(done), "remaining": len(keys) - len(done),
           "failed_last_attempt": failed, "raw_files_in_progress": sum(1 for p in raw_dir.rglob("*") if p.is_file())
           if raw_dir.exists() else 0, "elapsed_min": None, "done_this_run": None, "eta_min": None}
    if running and started:
        el = (now - started) / 60
        out["elapsed_min"] = round(el, 1)
        if done_at_start is not None:
            n = len(done) - done_at_start
            out["done_this_run"] = n
            if n > 0:
                out["eta_min"] = round(el / n * out["remaining"], 1)
    return out


class RunLock:
    """One fetch at a time: two runs on the same units waste bandwidth and race on the same files."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                pid = int(self.path.read_text().strip())
                os.kill(pid, 0)
                raise FetchError(f"another fetch is running (pid {pid}); stop it first or wait")
            except (ValueError, ProcessLookupError):
                pass                                   # stale lock from a killed run
            except PermissionError:
                raise FetchError("another fetch is running (lock held)")
        self.path.write_text(str(os.getpid()))
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
