"""Convert the raw POWER and MUR downloads into tidy long-format CSV.

Raw files are kept untouched so provenance is preserved. This script only reads
them and writes derived tables.

The daily table is skipped by default. It is by far the largest output, roughly
98 MB for 19 sites, and no analysis reads it: trend.py uses the monthly table
and the MUR table only. Pass --with-daily to build it anyway.

Usage: python3 tidy.py [--with-daily]
Writes: data/power_monthly.csv, data/mur_sst.csv (and data/power_daily.csv
        only with --with-daily)
"""
import csv
import json
import os
import re
import sys
from datetime import date, timedelta

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def power_units(path):
    """Read the unit for each parameter from the POWER header block."""
    units = {}
    with open(path) as fh:
        for line in fh:
            if not line.startswith("-BEGIN HEADER-"):
                continue
            for inner in fh:
                if inner.startswith("-END HEADER-"):
                    return units
                m = re.match(r"^([A-Z0-9_]+)\s+.*\(([^()]*)\)\s*$", inner.rstrip())
                if m:
                    units[m.group(1)] = m.group(2)
    return units


def convert_power_monthly(sites, out):
    rows = []
    for s in sites:
        path = f"power/monthly/{s['id']}.csv"
        if not os.path.exists(path) or os.path.getsize(path) < 200:
            print(f"  skip missing {path}")
            continue
        units = power_units(path)
        with open(path) as fh:
            for line in fh:
                parts = line.rstrip("\n").split(",")
                if len(parts) < 15 or not parts[1].isdigit():
                    continue
                param, year = parts[0], int(parts[1])
                for i, mon in enumerate(MONTHS):
                    raw = parts[2 + i]
                    try:
                        val = float(raw)
                    except ValueError:
                        continue
                    if val == -999:
                        continue
                    rows.append({
                        "site_id": s["id"], "country": s["country"],
                        "lat": s["lat"], "lon": s["lon"],
                        "variable": param, "unit": units.get(param, ""),
                        "year": year, "month": i + 1,
                        "date": f"{year}-{i + 1:02d}-01", "value": val,
                    })
    write_rows(out, ["site_id", "country", "lat", "lon", "variable", "unit",
                     "year", "month", "date", "value"], rows)
    return len(rows)


def convert_power_daily(sites, out):
    rows = []
    for s in sites:
        path = f"power/daily/{s['id']}.csv"
        if not os.path.exists(path) or os.path.getsize(path) < 200:
            print(f"  skip missing {path}")
            continue
        units = power_units(path)
        header = None
        with open(path) as fh:
            for line in fh:
                parts = line.rstrip("\n").split(",")
                if parts[:2] == ["YEAR", "DOY"]:
                    header = parts
                    continue
                if not header or len(parts) != len(header):
                    continue
                if not (parts[0].isdigit() and parts[1].isdigit()):
                    continue
                year, doy = int(parts[0]), int(parts[1])
                day = date(year, 1, 1) + timedelta(days=doy - 1)
                for name, raw in zip(header[2:], parts[2:]):
                    try:
                        val = float(raw)
                    except ValueError:
                        continue
                    if val == -999:
                        continue
                    rows.append({
                        "site_id": s["id"], "country": s["country"],
                        "lat": s["lat"], "lon": s["lon"],
                        "variable": name, "unit": units.get(name, ""),
                        "date": day.isoformat(), "value": val,
                    })
    write_rows(out, ["site_id", "country", "lat", "lon", "variable", "unit",
                     "date", "value"], rows)
    return len(rows)


def convert_mur(sites, out):
    rows = []
    for s in sites:
        path = f"mur/{s['id']}.csv"
        if not os.path.exists(path) or os.path.getsize(path) < 100:
            print(f"  skip missing {path}")
            continue
        with open(path) as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if not header or header[0] != "time":
                print(f"  skip malformed {path}")
                continue
            next(reader, None)  # unit row
            for r in reader:
                if len(r) < 4:
                    continue
                try:
                    val = float(r[3])
                except ValueError:
                    continue
                rows.append({
                    "site_id": s["id"], "country": s["country"],
                    "lat": s["lat"], "lon": s["lon"],
                    "variable": "analysed_sst", "unit": "degree_C",
                    "date": r[0][:10], "value": val,
                })
    write_rows(out, ["site_id", "country", "lat", "lon", "variable", "unit",
                     "date", "value"], rows)
    return len(rows)


def write_rows(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    sites = json.load(open("sites.json"))
    print("power monthly rows:", convert_power_monthly(sites, "data/power_monthly.csv"))
    if "--with-daily" in sys.argv:
        print("power daily rows:  ", convert_power_daily(sites, "data/power_daily.csv"))
    else:
        print("power daily rows:   skipped, pass --with-daily to build the derived table")
    print("mur rows:          ", convert_mur(sites, "data/mur_sst.csv"))
