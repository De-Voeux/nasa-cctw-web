"""`catalog`: resolve product identifiers, variable schemas, services, coverage and auth hints.

Metadata only. Talks to NASA CMR search, Harmony `/capabilities`, and sends at most one
HEAD (redirects not followed) per product to classify the download endpoint. Never GETs
a science granule.
"""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import json
import re
import urllib.parse
from collections import defaultdict
from pathlib import Path

from .http import MetadataClient, redact

CMR = "https://cmr.earthdata.nasa.gov/search"
HARMONY = "https://harmony.earthdata.nasa.gov"
PAGE_SIZE = 2000
_DATE_RE = re.compile(r"(?<!\d)(\d{8})(?:\d{6})?(?!\d)")


# ---------------------------------------------------------------- product list

def product_targets(products_cfg: dict, enabled: dict) -> list[dict]:
    """Flatten products.yaml into one entry per CMR collection to resolve."""
    out = []
    if enabled.get("mur_sst", {}).get("enabled", True) and "mur_sst" in products_cfg:
        p = products_cfg["mur_sst"]
        out.append({"key": "mur_sst", "group": "sst", "processing": "standard", **p})
    return out


# ---------------------------------------------------------------- CMR lookups

def resolve_collection(client: MetadataClient, short_name: str) -> dict:
    _, d = client.get_json(f"{CMR}/collections.umm_json", {"short_name": short_name})
    items = d.get("items", [])
    if not items:
        raise LookupError(f"CMR has no collection with short_name={short_name}")
    if len(items) > 1:
        provs = sorted(i["meta"]["provider-id"] for i in items)
        raise LookupError(f"{short_name} is ambiguous across providers {provs}")
    meta, umm = items[0]["meta"], items[0]["umm"]
    rng = (umm.get("TemporalExtents") or [{}])[0].get("RangeDateTimes") or [{}]
    assoc = meta.get("associations", {})
    return {
        "concept_id": meta["concept-id"],
        "provider": meta["provider-id"],
        "short_name": umm.get("ShortName"),
        "version": umm.get("Version"),
        "title": umm.get("EntryTitle"),
        "doi": (umm.get("DOI") or {}).get("DOI"),
        "temporal_begin": rng[0].get("BeginningDateTime"),
        "temporal_end": rng[0].get("EndingDateTime"),
        "cloud_region": (umm.get("DirectDistributionInformation") or {}).get("Region"),
        "service_ids": assoc.get("services", []),
        "variable_ids": assoc.get("variables", []),
        "revision_date": meta.get("revision-date"),
    }


def resolve_variables(client: MetadataClient, variable_ids: list[str], wanted: list[str]) -> dict:
    if not variable_ids:
        return {}
    params = [("concept_id[]", v) for v in variable_ids] + [("page_size", "100")]
    _, d = client.get_json(f"{CMR}/variables.umm_json", params)
    found = {}
    for it in d.get("items", []):
        u = it["umm"]
        if u.get("Name") not in wanted:
            continue
        fills = [f.get("Value") for f in u.get("FillValues") or []]
        found[u["Name"]] = {
            "concept_id": it["meta"]["concept-id"],
            "long_name": u.get("LongName"),
            "dtype": u.get("DataType"),
            "units": u.get("Units"),
            "fill_values": fills,
            "scale_factor": u.get("Scale"),
            "add_offset": u.get("Offset"),
            "valid_ranges": u.get("ValidRanges"),
            "dimensions": {x["Name"]: int(x["Size"]) for x in u.get("Dimensions") or []},
        }
    return found


def harmony_capabilities(client: MetadataClient, concept_id: str) -> dict:
    resp = client.request("GET", f"{HARMONY}/capabilities?collectionId={concept_id}")
    if resp.status != 200:
        return {"available": False, "http_status": resp.status}
    d = resp.json()
    services = []
    for s in d.get("services", []):
        sub = s.get("capabilities", {}).get("subsetting", {})
        services.append({
            "name": s.get("name"),
            "subsetting": {k: v for k, v in sub.items() if v},
            "output_formats": [f["name"] for f in s.get("capabilities", {}).get("outputFormats", [])],
        })
    return {"available": True, "services": services}


# ---------------------------------------------------------------- granule inventory

def granule_date(name: str) -> dt.date | None:
    m = _DATE_RE.search(name.split("/")[-1])
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _science_file(umm: dict) -> dict:
    infos = (umm.get("DataGranule") or {}).get("ArchiveAndDistributionInformation") or []
    for a in infos:
        if not str(a.get("Name", "")).endswith((".md5", ".sha256")):
            return a
    return infos[0] if infos else {}


def _https_url(umm: dict) -> str | None:
    for r in umm.get("RelatedUrls") or []:
        if r.get("Type") == "GET DATA" and str(r.get("URL", "")).startswith("https://"):
            return r["URL"]
    return None


def list_granules(client: MetadataClient, short_name: str, pattern: str,
                  start: dt.date, end: dt.date, concept_id: str | None = None) -> list[dict]:
    params = [
        ("collection_concept_id", concept_id) if concept_id else ("short_name", short_name),
        ("temporal", f"{start.isoformat()}T00:00:00Z,{end.isoformat()}T23:59:59Z"),
        ("readable_granule_name", pattern),
        ("options[readable_granule_name][pattern]", "true"),
        ("sort_key", "start_date"),
        ("page_size", str(PAGE_SIZE)),
    ]
    url = f"{CMR}/granules.umm_json?{urllib.parse.urlencode(params)}"
    out: list[dict] = []
    search_after = None
    while True:
        hdrs = {"CMR-Search-After": search_after} if search_after else None
        resp, d = client.get_json(url, headers=hdrs)
        for it in d.get("items", []):
            umm, meta = it["umm"], it["meta"]
            f = _science_file(umm)
            ext = umm.get("TemporalExtent", {}).get("RangeDateTime", {})
            out.append({
                "granule_ur": umm["GranuleUR"],
                "date": (granule_date(umm["GranuleUR"]) or granule_date(f.get("Name", "")) or None),
                "begin": ext.get("BeginningDateTime"),
                "end": ext.get("EndingDateTime"),
                "file_name": f.get("Name"),
                "size_bytes": f.get("SizeInBytes"),
                "checksum": (f.get("Checksum") or {}).get("Value"),
                "checksum_algorithm": (f.get("Checksum") or {}).get("Algorithm"),
                "https_url": _https_url(umm),
                "revision_date": meta.get("revision-date"),
            })
        nxt = resp.header("CMR-Search-After")
        if not d.get("items") or len(d["items"]) < PAGE_SIZE or not nxt:
            break
        search_after = nxt
    return out


def dedupe_by_date(granules: list[dict], start: dt.date, end: dt.date):
    """One granule per calendar date; latest CMR revision wins. Returns (kept, duplicates)."""
    by_date: dict[dt.date, list[dict]] = defaultdict(list)
    for g in granules:
        if g["date"] and start <= g["date"] <= end:
            by_date[g["date"]].append(g)
    kept, dups = {}, []
    for d, gs in sorted(by_date.items()):
        gs = sorted(gs, key=lambda g: (g.get("revision_date") or "", g["granule_ur"]), reverse=True)
        kept[d] = gs[0]
        for other in gs[1:]:
            dups.append({"date": d.isoformat(), "kept": gs[0]["granule_ur"], "dropped": other["granule_ur"]})
    return kept, dups


def month_keys(start: dt.date, end: dt.date) -> list[str]:
    keys, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return keys


def monthly_inventory(kept: dict, start: dt.date, end: dt.date) -> dict:
    out = {}
    for key in month_keys(start, end):
        y, m = map(int, key.split("-"))
        first = max(start, dt.date(y, m, 1))
        last = min(end, dt.date(y, m, calendar.monthrange(y, m)[1]))
        days = [first + dt.timedelta(n) for n in range((last - first).days + 1)]
        present = [kept[d] for d in days if d in kept]
        sizes = [g["size_bytes"] for g in present if g.get("size_bytes")]
        out[key] = {
            "days_in_period": len(days),
            "granules": len(present),
            "missing_dates": [d.isoformat() for d in days if d not in kept],
            "bytes_total": sum(sizes) if sizes else None,
            "bytes_min": min(sizes) if sizes else None,
            "bytes_max": max(sizes) if sizes else None,
            "sizes_known": len(sizes),
        }
    return out


# ---------------------------------------------------------------- endpoint / auth probe

def probe_endpoint(client: MetadataClient, url: str | None) -> dict:
    """HEAD without following redirects. Records only status and redirect host (no signed query)."""
    if not url:
        return {"probed": False, "reason": "no https GET DATA url in granule metadata"}
    resp = client.request("HEAD", url)
    loc = resp.header("Location")
    host = urllib.parse.urlsplit(loc).netloc if loc else None
    if resp.status in (301, 302, 303, 307) and host and "urs.earthdata.nasa.gov" in host:
        cls = "earthdata_login_redirect"
    elif resp.status in (301, 302, 303, 307):
        cls = "redirect_to_signed_url"
    elif resp.status in (401, 403):
        cls = "auth_required"
    elif resp.status == 200:
        cls = "anonymous_ok"
    else:
        cls = f"http_{resp.status}"
    path = urllib.parse.urlsplit(url).path.strip("/").split("/")
    return {
        "probed": True,
        "url": redact(url),
        "bucket": path[0] if path else None,
        "head_status": resp.status,
        "redirect_host": host,
        "classification": cls,
        "content_length": resp.header("Content-Length"),
        "note": "HEAD only; anonymous GET was not attempted. Treat data access as requiring "
                "Earthdata Login until a credentialed pilot proves otherwise.",
    }


# ---------------------------------------------------------------- orchestration

def build_catalog(client: MetadataClient, products_cfg: dict, enabled: dict,
                  start: dt.date, end: dt.date, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    products = []
    for t in product_targets(products_cfg, enabled):
        entry: dict = {"key": t["key"], "group": t["group"], "role": t.get("role"),
                       "processing": t.get("processing")}
        try:
            coll = resolve_collection(client, t["short_name"])
        except LookupError as e:
            entry["error"] = str(e)
            products.append(entry)
            continue
        entry["collection"] = coll
        entry["variables"] = resolve_variables(client, coll["variable_ids"], t.get("variables", []))
        entry["missing_variables"] = sorted(set(t.get("variables", [])) - set(entry["variables"]))
        entry["harmony"] = harmony_capabilities(client, coll["concept_id"])
        grans = list_granules(client, t["short_name"], t["granule_pattern"], start, end)
        kept, dups = dedupe_by_date(grans, start, end)
        inv = monthly_inventory(kept, start, end)
        entry["inventory"] = {
            "granule_pattern": t["granule_pattern"],
            "records_returned": len(grans),
            "unique_dates": len(kept),
            "first_date": min(kept).isoformat() if kept else None,
            "last_date": max(kept).isoformat() if kept else None,
            "duplicates": dups,
            "months": inv,
            "missing_days_total": sum(len(m["missing_dates"]) for m in inv.values()),
        }
        entry["granules"] = [
            {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in g.items() if k != "https_url"}
            | {"https_url": redact(g["https_url"]) if g.get("https_url") else None}
            for _, g in sorted(kept.items())
        ]
        first = next(iter(kept.values()), None)
        entry["endpoint"] = probe_endpoint(client, first and first.get("https_url"))
        products.append(entry)
    return {
        "schema": "seagis.catalog/1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "metadata_requests": client.calls,
        "science_bytes_downloaded": 0,
        "products": products,
    }


def summarize(cat: dict) -> str:
    lines = [f"CATALOG  period {cat['period']['start']} .. {cat['period']['end']}  "
             f"({cat['metadata_requests']} metadata requests, 0 science bytes)", ""]
    hdr = f"{'PRODUCT':28} {'COLLECTION':24} {'DAYS':>5} {'MISS':>5} {'DUP':>4} {'FIRST':10} {'LAST':10} {'GiB(full granules)':>18}"
    lines += [hdr, "-" * len(hdr)]
    for p in cat["products"]:
        if "error" in p:
            lines.append(f"{p['key']:28} ERROR {p['error']}")
            continue
        inv = p["inventory"]
        total = sum(m["bytes_total"] or 0 for m in inv["months"].values())
        lines.append(f"{p['key']:28} {p['collection']['concept_id']:24} {inv['unique_dates']:>5} "
                     f"{inv['missing_days_total']:>5} {len(inv['duplicates']):>4} {inv['first_date'] or '-':10} "
                     f"{inv['last_date'] or '-':10} {total / 2**30:>18.1f}")
    lines += ["", "Full-granule GiB is the size of whole global files, NOT the subset transfer estimate.",
              "Variables/units/fills, Harmony services and endpoint probes are in outputs/catalog.json."]
    return "\n".join(lines)


INVENTORY_COLUMNS = ["product", "collection_id", "month", "days_in_period", "granules_available",
                     "missing_days", "missing_dates", "full_granule_bytes_total", "full_granule_mib_total",
                     "granule_bytes_min", "granule_bytes_max"]


def inventory_rows(cat: dict) -> list[dict]:
    """One row per product x month. Sizes are whole global files, not subset transfer."""
    rows = []
    for p in cat["products"]:
        if "error" in p:
            continue
        for month, m in p["inventory"]["months"].items():
            total = m["bytes_total"]
            rows.append({
                "product": p["key"],
                "collection_id": p["collection"]["concept_id"],
                "month": month,
                "days_in_period": m["days_in_period"],
                "granules_available": m["granules"],
                "missing_days": len(m["missing_dates"]),
                "missing_dates": ";".join(m["missing_dates"]),
                "full_granule_bytes_total": "" if total is None else total,
                "full_granule_mib_total": "" if total is None else round(total / 2**20, 1),
                "granule_bytes_min": "" if m["bytes_min"] is None else m["bytes_min"],
                "granule_bytes_max": "" if m["bytes_max"] is None else m["bytes_max"],
            })
    return rows


def write_inventory_csv(cat: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "catalog_inventory.csv"
    tmp = path.with_suffix(".csv.part")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INVENTORY_COLUMNS)
        w.writeheader()
        w.writerows(inventory_rows(cat))
    tmp.replace(path)
    return path


def write_catalog(cat: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "catalog.json"
    tmp = path.with_suffix(".json.part")
    tmp.write_text(json.dumps(cat, indent=2, default=str))
    tmp.replace(path)
    return path
