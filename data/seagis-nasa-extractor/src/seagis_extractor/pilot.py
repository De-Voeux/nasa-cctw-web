"""`pilot`: the small, approved calibration run (task criterion 4).

Gate (all must hold, otherwise nothing is requested):
1. `--approve-plan` equals plan.json's plan_sha256, and that hash still matches the plan contents.
2. Every input recorded in the plan (catalog, ROI GeoJSON, configs) is unchanged on disk.
3. No Copernicus zone without sea cells is left unaccepted.

Scope: only plan.pilot rows (one small subregion per pilot region), only the first `pilot.days`
days of the period, only the plan's approved request boxes. Raw pilot files are kept under
data/raw/pilot/ (gitignored) for inspection.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import urllib.parse
from collections import defaultdict
from pathlib import Path

from . import auth, estimate, process, validate
from .catalog import granule_date
from .fetch import (ByteBudget, FetchError, FetchGuardError, HarmonyClient, copernicus_open, crop_to_cells,
                    harmony_url)
from .manifest import Manifest

MIB = 1 << 20


class PlanGateError(RuntimeError):
    pass


def verify_plan(plan: dict, approve: str | None, root: Path) -> None:
    if not approve:
        raise PlanGateError("refusing to run: pass --approve-plan <PLAN SHA256> after reviewing the plan")
    actual = estimate.plan_hash(plan)
    if actual != plan.get("plan_sha256"):
        raise PlanGateError(f"plan.json was modified after it was generated (content hash {actual[:12]}… "
                            f"!= recorded {str(plan.get('plan_sha256'))[:12]}…); re-run `plan`")
    if approve != plan["plan_sha256"]:
        raise PlanGateError(f"--approve-plan {approve[:12]}… does not match plan_sha256 {plan['plan_sha256'][:12]}…")
    for name, rec in plan.get("inputs", {}).items():
        p = Path(rec["path"])
        p = p if p.is_absolute() else root / p
        if not p.exists():
            raise PlanGateError(f"plan input {name} missing: {rec['path']}")
        if hashlib.sha256(p.read_bytes()).hexdigest() != rec["sha256"]:
            raise PlanGateError(f"plan input {name} changed since the plan was made ({rec['path']}); re-run `plan`")
    cm = plan.get("copernicus") or {}
    if cm.get("zones_without_sea"):
        raise PlanGateError("plan has zones without sea cells: " + ", ".join(cm["zones_without_sea"]))


def pilot_scope(plan: dict) -> tuple[list[dict], dt.date, dt.date, dict]:
    days = int(plan["pilot"]["days"])
    start = dt.date.fromisoformat(plan["period"]["start"])
    end = start + dt.timedelta(days - 1)
    by_key = {(r["region_id"], r["subregion_id"]): r for r in plan["rois"]}
    rois, missing = [], {}
    for row in plan["pilot"]["rows"]:
        key = (row["region_id"], row["subregion_id"])
        rois.append(by_key[key])
        missing[key] = set(row.get("missing_dates", []))
    if not rois:
        raise PlanGateError("plan has no pilot rows")
    return rois, start, end, missing


def mur_budget(plan: dict) -> int:
    high = sum(r["transfer_bytes_high"] or 0 for r in plan["pilot"]["rows"])
    return max(4 * high, 5 * MIB)


def dry_run_lines(plan: dict, cfg: dict) -> list[str]:
    rois, start, end, _ = pilot_scope(plan)
    cid = plan["dataset"]["collection"]["concept_id"]
    var = list(plan["dataset"]["variables"])
    out = [f"PILOT DRY RUN {start}..{end} (nothing is requested)"]
    for roi in rois:
        for q in roi["mur_requests"]:
            out.append(f"MUR {roi['region_id']}/{roi['subregion_id']}: {harmony_url(cid, var, q['bbox_w_s_e_n'], start, end)}")
    for spec in cfg["_products"].get("copernicus", []):
        for roi in rois:
            out.append(f"COPERNICUS {spec['dataset_id']} {roi['region_id']}/{roi['subregion_id']}: "
                       f"bbox {roi['request']['bbox_w_s_e_n']}, {start}..{end}, surface, vars {spec['variables']}")
    out.append(f"MUR byte budget: {mur_budget(plan)} bytes")
    return out


def _open_nc(path: Path):
    import xarray as xr
    return xr.open_dataset(path, engine="h5netcdf", mask_and_scale=True).load()


def run_pilot(root: Path, cfg: dict, plan: dict, *, out_dir: Path, raw_dir: Path, membership_dir: Path,
              harmony: HarmonyClient | None = None, cm_opener=None, log=print) -> dict:
    rois, start, end, missing = pilot_scope(plan)
    dates = [start + dt.timedelta(n) for n in range((end - start).days + 1)]
    grid = estimate.MurGrid()
    manifest = Manifest(out_dir / "pilot_manifest.jsonl")
    checks, rows, rejected, files = [], [], [], []
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    # ------------------------------------------------ MUR via Harmony
    if harmony is None:
        allowed = {tuple(q["bbox_w_s_e_n"]) for r in rois for q in r["mur_requests"]}
        harmony = HarmonyClient(auth.earthdata_token(), allowed, ByteBudget(mur_budget(plan)))
    cid = plan["dataset"]["collection"]["concept_id"]
    variables = list(plan["dataset"]["variables"])
    for roi in rois:
        key = (roi["region_id"], roi["subregion_id"])
        expected = [d for d in dates if d.isoformat() not in missing[key]]
        per_day = defaultdict(list)
        for q in roi["mur_requests"]:
            tile = "t{}_{}".format(*q.get("tile", [0, 0]))
            log(f"MUR {key[0]}/{key[1]} {tile}: submitting Harmony job")
            job = harmony.wait(harmony.submit(cid, variables, q["bbox_w_s_e_n"], start, end))
            links = harmony.data_links(job)
            got = set()
            for link in links:
                name = Path(urllib.parse.urlsplit(link["href"]).path).name
                d = granule_date(name)
                if d not in expected:
                    rejected.append({"file": name, "reason": f"granule date {d} not in pilot dates"})
                    continue
                mkey = f"mur/{key[0]}/{key[1]}/{tile}/{d}"
                dest = raw_dir / "mur" / key[0] / key[1] / tile / name
                rec = manifest.done(mkey)
                if rec is None:
                    info = harmony.download(link["href"], dest)
                    ds = _open_nc(dest)
                    try:
                        validate.mur_guard(ds, q)
                    except FetchGuardError as e:
                        dest.unlink(missing_ok=True)
                        manifest.record(mkey, status="rejected", reason=str(e))
                        raise
                    rec = manifest.record(mkey, status="ok", path=str(dest), bytes=info["bytes"], sha256=info["sha256"])
                else:
                    ds = _open_nc(dest)
                    validate.mur_guard(ds, q)
                files.append({"source": "mur_sst", "roi": "/".join(key), "date": d.isoformat(), "file": name,
                              "bytes": rec["bytes"], "sha256": rec["sha256"]})
                checks += [c | {"roi": "/".join(key), "date": d.isoformat()} for c in validate.mur_checks(ds, q, grid, d)]
                per_day[d].append((ds, name))
                got.add(d)
            checks.append(validate.check("mur.days_returned", got == set(expected),
                                         f"{len(got)}/{len(expected)} expected days, {len(links)} links") | {"roi": "/".join(key)})
        mem = process.read_membership(membership_dir / f"mur_sst__{key[0]}__{key[1]}__{roi['geometry_version']}.csv.gz")
        for d in sorted(per_day):
            r, info = process.aggregate_mur([x for x, _ in per_day[d]], mem, grid, roi, d,
                                            ";".join(n for _, n in per_day[d]))
            rows += r
            checks.append(validate.check("mur.coastline_vs_mask", info["cells_mur_land_or_lake"] == 0,
                                         f"{info['cells_mur_land_or_lake']}/{info['membership_cells']} zone cells are land/lake "
                                         f"in MUR's mask", warn=True) | {"roi": "/".join(key), "date": d.isoformat()})

    # ------------------------------------------------ Copernicus Marine
    cm_plan = {d["key"]: d for d in (plan.get("copernicus") or {}).get("datasets", [])}
    cm_specs = [s for s in cfg["_products"].get("copernicus", []) if s["key"] in cm_plan]
    if cm_specs and cm_opener is None and not auth.copernicus_configured():
        raise auth.AuthError("Copernicus Marine credentials not found (.env or `copernicusmarine login`)")
    for spec in cm_specs:
        d_plan = cm_plan[spec["key"]]
        for roi in rois:
            key = (roi["region_id"], roi["subregion_id"])
            row = next(r for r in d_plan["rois"] if (r["region_id"], r["subregion_id"]) == key)
            if row.get("available") is False:
                checks.append(validate.check(f"{spec['key']}.skipped", None, "unavailable by decision") | {"roi": "/".join(key)})
                continue
            bbox = roi["request"]["bbox_w_s_e_n"]
            log(f"COPERNICUS {spec['key']} {key[0]}/{key[1]}: subsetting")
            ds = copernicus_open(spec, bbox, start, end, opener=cm_opener)
            try:
                validate.copernicus_guard(ds, bbox, d_plan["grid"]["lat_step"], d_plan["grid"]["lon_step"])
            except FetchGuardError:
                raise
            ds = crop_to_cells(ds, bbox, d_plan["grid"]["lat_step"], d_plan["grid"]["lon_step"]).load()
            if "depth" in ds.dims:
                ds = ds.isel(depth=0, drop=False)
            dest = raw_dir / "copernicus" / spec["key"] / key[0] / f"{key[1]}.nc"
            dest.parent.mkdir(parents=True, exist_ok=True)
            part = dest.with_name(dest.name + ".part")
            ds.to_netcdf(part, engine="h5netcdf")
            part.replace(dest)
            sha = hashlib.sha256(dest.read_bytes()).hexdigest()
            manifest.record(f"{spec['key']}/{key[0]}/{key[1]}", status="ok", path=str(dest),
                            bytes=dest.stat().st_size, sha256=sha)
            files.append({"source": spec["key"], "roi": "/".join(key), "file": dest.name,
                          "bytes": dest.stat().st_size, "sha256": sha})
            mem = process.read_membership(membership_dir / f"{spec['key']}__{key[0]}__{key[1]}__v1.csv.gz")
            checks += [c | {"roi": "/".join(key)} for c in validate.copernicus_checks(ds, spec["key"], row, dates, mem)]
            rows += process.aggregate_copernicus(ds, mem, roi, spec["key"], spec["dataset_id"])

    # ------------------------------------------------ report
    mur_bytes = sum(f["bytes"] for f in files if f["source"] == "mur_sst")
    est = {k: sum(r[f"transfer_bytes_{k}"] or 0 for r in plan["pilot"]["rows"]) for k in ("low", "expected", "high")}
    checks.append(validate.check("mur.transfer_vs_estimate", est["low"] * 0.5 <= mur_bytes <= est["high"] * 1.5,
                                 f"actual {mur_bytes} bytes vs plan LOW {est['low']} / EXPECTED {est['expected']} / "
                                 f"HIGH {est['high']}", warn=True))
    status = "FAIL" if any(c["status"] == "FAIL" for c in checks) else "PASS"
    report = {"schema": "seagis.pilot/1", "plan_sha256": plan["plan_sha256"], "started": started,
              "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "period": [start.isoformat(), end.isoformat()], "rois": ["/".join((r["region_id"], r["subregion_id"])) for r in rois],
              "status": status, "mur_bytes_downloaded": mur_bytes, "mur_estimate_bytes": est,
              "harmony_calls": harmony.calls, "budget_bytes": harmony.budget.limit, "files": files,
              "rejected": rejected, "checks": checks, "daily_rows": len(rows)}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pilot_report.json").write_text(json.dumps(report, indent=1, default=str))
    with (out_dir / "pilot_daily.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[c for c, _ in estimate.FINAL_SCHEMA])
        w.writeheader()
        w.writerows(rows)
    (out_dir / "pilot_summary.txt").write_text(summary(report) + "\n")
    return report


def summary(report: dict) -> str:
    L = [f"PILOT {report['period'][0]}..{report['period'][1]}  {', '.join(report['rois'])}  -> {report['status']}",
         f"MUR downloaded {report['mur_bytes_downloaded']} bytes (plan LOW/EXP/HIGH "
         f"{report['mur_estimate_bytes']['low']}/{report['mur_estimate_bytes']['expected']}/{report['mur_estimate_bytes']['high']}), "
         f"{report['harmony_calls']} Harmony calls, {len(report['files'])} files, {report['daily_rows']} daily rows"]
    agg = defaultdict(lambda: defaultdict(int))
    for c in report["checks"]:
        agg[c["check"]][c["status"]] += 1
    for name in sorted(agg):
        L.append(f"  {name:38} " + " ".join(f"{k}={v}" for k, v in sorted(agg[name].items())))
    bad = [c for c in report["checks"] if c["status"] != "PASS"]
    for c in bad[:30]:
        L.append(f"  {c['status']} {c['check']} {c.get('roi', '')} {c.get('date', '')}: {c['detail']}")
    if report["rejected"]:
        L.append(f"  rejected: {report['rejected']}")
    return "\n".join(L)
