"""Long-term trends per region for the dashboard (earth-globe/src/data/longTermTrends.json).

Reads the monthly zone files that `monthly.py export` loads into seagis_monthly_metrics
(data/processed_monthly), so the JSON matches the database rows. Nothing is downloaded.

Per region and variable:
- region monthly mean = zone means weighted by valid_pixel_count, the same weighting
  as worker/environment.js. A month counts only when every zone that has data for this
  variable has a value in it, so the mix of zones never changes between months.
- annual mean = mean of 12 complete months (a year with a missing month is left empty).
- Mann-Kendall test and Sen's slope on the annual means (research/data-access/scripts/mk.py),
  with the 95% confidence interval of Sen's slope (Gilbert 1987, rank method).
- monthly climatology (mean of each calendar month) for the seasonal cycle.

Usage: .venv/bin/python scripts/build_trends.py [--start 2003-01-01] [--end 2024-12-31] [--out PATH]
"""
import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / "research" / "data-access" / "scripts"))
from mk import mann_kendall, sens_slope  # noqa: E402

PROCESSED = ROOT / "data" / "processed_monthly"
OUT = REPO / "earth-globe" / "src" / "data" / "longTermTrends.json"
KEY = ["region_id", "subregion_id", "geometry_version", "dataset", "variable", "month"]
MIN_YEARS = 10

# dashboard key -> (dataset, variable, label, display unit, digits, source)
VARIABLES = {
    "sst": ("mur_sst_monthly", "analysed_sst", "Sea surface temperature", "°C", 2,
            "NASA JPL MUR SST L4, monthly mean (NOAA ERD jplMURSST41mday)"),
    "rain": ("gpm_imerg_monthly", "precipitation", "Rainfall", "mm/day", 2,
             "NASA GPM IMERG Final V07 monthly (GPM_3IMERGM)"),
    "air_temp": ("nasa_power_monthly", "T2M", "Air temperature (2 m)", "°C", 2,
                 "NASA POWER monthly (MERRA-2), one point per zone"),
    "salinity": ("cmems_phy_my", "so", "Salinity", "PSU", 2,
                 "Copernicus Marine GLORYS12 multi-year reanalysis, surface"),
    "nitrate": ("cmems_bgc_my", "no3", "Nitrate", "mmol/m³", 4,
                "Copernicus Marine global biogeochemistry multi-year, surface"),
    "phosphate": ("cmems_bgc_my", "po4", "Phosphate", "mmol/m³", 4,
                  "Copernicus Marine global biogeochemistry multi-year, surface"),
    "ph": ("cmems_bgc_my", "ph", "pH", "", 3,
           "Copernicus Marine global biogeochemistry multi-year, surface"),
}


def sen_ci(xs, ts, var_s, z=1.959964):
    """95% CI of Sen's slope: ranks (N - C)/2 and (N + C)/2 + 1 of the sorted pairwise slopes."""
    slopes = sorted((xs[j] - xs[i]) / (ts[j] - ts[i])
                    for i in range(len(xs) - 1) for j in range(i + 1, len(xs)) if ts[j] != ts[i])
    n = len(slopes)
    if n < 2 or var_s <= 0:
        return None
    c = z * math.sqrt(var_s)
    lo, hi = int(round((n - c) / 2)), int(round((n + c) / 2)) + 1
    if lo < 1 or hi > n:
        return None
    return slopes[lo - 1], slopes[hi - 1]


def var_s(xs):
    n = len(xs)
    counts = {}
    for v in xs:
        counts[v] = counts.get(v, 0) + 1
    ties = sum(c * (c - 1) * (2 * c + 5) for c in counts.values() if c > 1)
    return (n * (n - 1) * (2 * n + 5) - ties) / 18.0


def r(v, digits):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), digits)


def main():
    import pandas as pd

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2003-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    files = sorted(PROCESSED.rglob("*.parquet"))
    if not files:
        raise SystemExit("nothing in data/processed_monthly")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["month"] = df["month"].astype(str).str[:10]
    df = df[(df["month"] >= args.start) & (df["month"] <= args.end)]
    df = df.drop_duplicates(KEY, keep="first")          # same rule as monthly.py export
    y0, y1 = int(args.start[:4]), int(args.end[:4])
    years = list(range(y0, y1 + 1))

    regions = {}
    for key, (dataset, variable, label, unit, digits, source) in VARIABLES.items():
        sub = df[(df["dataset"] == dataset) & (df["variable"] == variable)].copy()
        if sub.empty:
            continue
        product = sub["product_version"].dropna().iloc[0] if sub["product_version"].notna().any() else None
        sub["w"] = sub["valid_pixel_count"].fillna(0).clip(lower=1)
        for region_id, g in sub.groupby("region_id"):
            have = g[g["mean"].notna()]
            zones = set(have["subregion_id"])           # zones with no sea cell for this source drop out
            if not zones:
                continue
            monthly = {}
            for month, m in have.groupby("month"):
                if set(m["subregion_id"]) != zones:
                    continue                            # a zone is missing this month: leave the month empty
                monthly[month] = float((m["mean"] * m["w"]).sum() / m["w"].sum())
            annual = []
            for y in years:
                vals = [monthly.get(f"{y}-{mo:02d}-01") for mo in range(1, 13)]
                annual.append(sum(vals) / 12 if all(v is not None for v in vals) else None)
            clim = []
            for mo in range(1, 13):
                vals = [v for k, v in monthly.items() if int(k[5:7]) == mo]
                clim.append(sum(vals) / len(vals) if vals else None)
            pts = [(y, v) for y, v in zip(years, annual) if v is not None]
            trend = None
            if len(pts) >= MIN_YEARS:
                ts, xs = [p[0] for p in pts], [p[1] for p in pts]
                test = mann_kendall(xs)
                slope = sens_slope(xs, ts)
                ci = sen_ci(xs, ts, var_s(xs))
                trend = {
                    "n_years": test["n"],
                    "first_year": ts[0],
                    "last_year": ts[-1],
                    "S": test["S"],
                    "Z": round(test["Z"], 3),
                    "p": round(test["p"], 4),
                    "significant": test["p"] < 0.05,
                    "slope_per_decade": r(slope * 10, digits + 2),
                    "ci95_per_decade": [r(ci[0] * 10, digits + 2), r(ci[1] * 10, digits + 2)] if ci else None,
                    "change_over_period": r(slope * (ts[-1] - ts[0]), digits + 1),
                }
            regions.setdefault(region_id, {"zones": {}, "series": {}})
            regions[region_id]["zones"][key] = sorted(zones)
            regions[region_id]["series"][key] = {
                "name": label,
                "unit": unit,
                "digits": digits,
                "source": source,
                "product_version": product,
                "months_with_data": len(monthly),
                "annual": [r(v, digits + 1) for v in annual],
                "climatology": [r(v, digits + 1) for v in clim],
                "trend": trend,
            }

    doc = {
        "generated": dt.date.today().isoformat(),
        "window": {"start": args.start, "end": args.end},
        "years": years,
        "method": ("Mann-Kendall test and Sen's slope on annual means of complete years; 95% CI of "
                   "Sen's slope by the rank method (Gilbert 1987). Region value = zone means weighted "
                   "by valid pixel count. Satellite and model values, not field measurements."),
        "regions": dict(sorted(regions.items())),
    }
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"wrote {args.out}: {len(regions)} regions, {Path(args.out).stat().st_size // 1024} KB")
    for rid, reg in doc["regions"].items():
        line = []
        for k, s in reg["series"].items():
            t = s["trend"]
            line.append(f"{k} " + (f"{t['slope_per_decade']:+g}/dec p={t['p']:.3f}{'*' if t['significant'] else ''}"
                                   if t else "n/a"))
        print(f"  {rid}: " + "; ".join(line))


if __name__ == "__main__":
    main()
