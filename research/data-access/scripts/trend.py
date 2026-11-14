"""Trend analysis for every site and variable.

Primary result: Mann-Kendall and Sen's slope on annual means, because 22 annual
values are far less autocorrelated than 264 monthly values.

Secondary result: the same tests on monthly anomalies after removing the
monthly climatology. The p-value there is optimistic because consecutive months
are correlated; it is reported for direction only.

Output: results/trends.csv and a printed table.
"""
import csv
import os
from collections import defaultdict

from mk import mann_kendall, sens_slope


def load(path, key="variable"):
    """Return {(site, variable, country, lat, lon): {(year, month): value}}."""
    series = defaultdict(dict)
    meta = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            if "month" in row and row["month"]:
                ym = (int(row["year"]), int(row["month"]))
            else:
                y, m, _ = row["date"].split("-")
                ym = (int(y), int(m))
            k = (row["site_id"], row[key])
            meta[k] = (row["country"], row["lat"], row["lon"], row.get("unit", ""))
            series[k][ym] = float(row["value"])
    return series, meta


def annual_means(monthly):
    by_year = defaultdict(list)
    for (y, m), v in monthly.items():
        by_year[y].append(v)
    return [(y, sum(v) / len(v)) for y, v in sorted(by_year.items()) if len(v) >= 10]


def deseasonalised(monthly):
    by_month = defaultdict(list)
    for (y, m), v in monthly.items():
        by_month[m].append(v)
    clim = {m: sum(v) / len(v) for m, v in by_month.items()}
    return [(y * 12 + m, v - clim[m]) for (y, m), v in sorted(monthly.items())]


def main():
    series, meta = load("data/power_monthly.csv")
    mur, mur_meta = load("data/mur_sst.csv")
    series.update(mur)
    meta.update(mur_meta)

    rows = []
    for key in sorted(series):
        site, var = key
        country, lat, lon, unit = meta[key]
        monthly = series[key]
        if len(monthly) < 60:
            continue

        annual = annual_means(monthly)
        mk_a = mann_kendall([v for _, v in annual])
        sl_a = sens_slope([v for _, v in annual], [y for y, _ in annual])

        anom = deseasonalised(monthly)
        mk_m = mann_kendall([v for _, v in anom])
        sl_m = sens_slope([v for _, v in anom])

        rows.append({
            "site_id": site, "country": country, "lat": lat, "lon": lon,
            "variable": var, "unit": unit,
            "n_years": len(annual), "n_months": len(monthly),
            "annual_sens_slope_per_year": round(sl_a, 6),
            "annual_mk_z": round(mk_a["Z"], 3),
            "annual_mk_p": round(mk_a["p"], 4),
            "monthly_anom_sens_slope_per_month": round(sl_m, 6),
            "monthly_anom_mk_p": round(mk_m["p"], 4),
        })

    os.makedirs("results", exist_ok=True)
    out = "results/trends.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}\n")

    print(f"{'site':14s} {'variable':18s} {'n':>3s} {'Sen/yr':>11s} {'p':>8s}  verdict")
    for r in rows:
        if r["annual_mk_p"] < 0.05:
            v = "SIGNIFIKAN"
        else:
            v = "-"
        print(f"{r['site_id']:14s} {r['variable']:18s} {r['n_years']:3d} "
              f"{r['annual_sens_slope_per_year']:+11.5f} {r['annual_mk_p']:8.4f}  {v}")


if __name__ == "__main__":
    main()
