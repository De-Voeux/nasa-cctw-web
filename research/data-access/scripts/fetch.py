"""Download NASA POWER and MUR SST series for candidate Southeast Asian sites.

Every site is a regional grid cell centroid used for comparison, not a farm
location. Coordinates were chosen so the MUR cell is open water; each candidate
was probed once against the MUR griddap endpoint before being added, and any
point that returned NaN (land or masked) was moved offshore.

Site list follows the ice-ice regions recorded in research/evidence/. Entries
there are still unverified against the primary papers; the coordinates are our
choice, not a registry value.

Usage: python3 fetch.py
Writes: power/monthly/<id>.csv, power/daily/<id>.csv, mur/<id>.csv, sites.json
"""
import json
import os
import subprocess
import time

SITES = [
    # Indonesia
    {"id": "se-sulawesi", "name": "Southeast Sulawesi (Konawe coast)", "country": "Indonesia", "lat": -4.0, "lon": 123.0},
    {"id": "s-sulawesi", "name": "South Sulawesi (Takalar coast)", "country": "Indonesia", "lat": -5.6, "lon": 119.2},
    {"id": "c-sulawesi", "name": "Central Sulawesi (Banggai coast)", "country": "Indonesia", "lat": -1.0, "lon": 122.8},
    {"id": "n-kalimantan", "name": "North Kalimantan (Tarakan coast)", "country": "Indonesia", "lat": 3.3, "lon": 117.7},
    {"id": "maluku", "name": "Maluku (Kei Islands)", "country": "Indonesia", "lat": -5.6, "lon": 132.7},
    {"id": "n-java-sea", "name": "North Java Sea (Jepara offshore)", "country": "Indonesia", "lat": -5.8, "lon": 110.5},
    {"id": "wnt", "name": "West Nusa Tenggara (East Lombok)", "country": "Indonesia", "lat": -8.9, "lon": 116.5},
    # Malaysia
    {"id": "sabah", "name": "Sabah (Semporna coast)", "country": "Malaysia", "lat": 4.5, "lon": 118.8},
    # Philippines
    {"id": "tawi-tawi", "name": "Tawi-Tawi (Bongao coast)", "country": "Philippines", "lat": 5.0, "lon": 119.9},
    {"id": "bohol", "name": "Bohol (Bohol Sea)", "country": "Philippines", "lat": 10.0, "lon": 124.5},
    {"id": "ne-bohol", "name": "Northeastern Bohol (Candijay offshore)", "country": "Philippines", "lat": 9.9, "lon": 124.6},
    {"id": "zamboanga", "name": "Zamboanga City (Basilan Strait)", "country": "Philippines", "lat": 6.8, "lon": 122.0},
    {"id": "davao-del-norte", "name": "Davao del Norte (Davao Gulf)", "country": "Philippines", "lat": 7.2, "lon": 125.7},
    {"id": "pangasinan", "name": "Pangasinan (Lingayen Gulf)", "country": "Philippines", "lat": 16.4, "lon": 119.8},
    {"id": "batangas", "name": "Batangas (Calatagan coast)", "country": "Philippines", "lat": 13.8, "lon": 120.4},
    {"id": "southern-luzon", "name": "Southern Luzon (Tayabas Bay)", "country": "Philippines", "lat": 13.7, "lon": 121.6},
    {"id": "eastern-samar", "name": "Eastern Samar (Borongan coast)", "country": "Philippines", "lat": 11.6, "lon": 125.6},
    {"id": "palawan", "name": "Palawan (Sulu Sea)", "country": "Philippines", "lat": 9.8, "lon": 118.3},
    # Vietnam
    {"id": "khanh-hoa", "name": "Khanh Hoa coast", "country": "Vietnam", "lat": 12.2, "lon": 109.3},
]

POWER_VARS = [
    "T2M", "T2M_MAX", "T2M_MIN", "T2MDEW", "RH2M", "QV2M", "PS",
    "WS2M", "WD2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN",
]


def get(url, path, tries=4, pause=4):
    """Download with curl. The system Python has no CA bundle, so urllib fails TLS."""
    for attempt in range(1, tries + 1):
        proc = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", "180", "-o", path, url],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 200:
            with open(path, "rb") as fh:
                head = fh.read(200).decode("utf-8", "replace")
            if "Service Unavailable" not in head:
                return os.path.getsize(path)
        if attempt == tries:
            print(f"  FAILED after {tries}: {proc.stderr.strip()[:120]}")
            return 0
        time.sleep(pause)
    return 0


def main():
    os.makedirs("power/monthly", exist_ok=True)
    os.makedirs("power/daily", exist_ok=True)
    os.makedirs("mur", exist_ok=True)
    json.dump(SITES, open("sites.json", "w"), indent=2)

    for i, s in enumerate(SITES, 1):
        print(f"[{i}/{len(SITES)}] {s['id']} {s['lat']}, {s['lon']}", flush=True)

        u = ("https://power.larc.nasa.gov/api/temporal/monthly/point"
             f"?parameters={','.join(POWER_VARS)}&community=AG"
             f"&longitude={s['lon']}&latitude={s['lat']}"
             "&start=2003&end=2024&format=CSV")
        n = get(u, f"power/monthly/{s['id']}.csv")
        print(f"  POWER monthly 2003-2024: {n} bytes", flush=True)

        u = ("https://power.larc.nasa.gov/api/temporal/daily/point"
             f"?parameters={','.join(POWER_VARS)}&community=AG"
             f"&longitude={s['lon']}&latitude={s['lat']}"
             "&start=20030101&end=20241231&format=CSV")
        n = get(u, f"power/daily/{s['id']}.csv")
        print(f"  POWER daily 2003-2024: {n} bytes", flush=True)

        u = ("https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.csv"
             "?analysed_sst%5B(2003-01-01T09:00:00Z):30:(2024-12-31T09:00:00Z)%5D"
             f"%5B({s['lat']}):1:({s['lat']})%5D%5B({s['lon']}):1:({s['lon']})%5D")
        n = get(u, f"mur/{s['id']}.csv")
        print(f"  MUR SST sampled every 30 days: {n} bytes", flush=True)

        # ERDDAP returns 503 when hit back to back; pace the requests.
        time.sleep(3)


if __name__ == "__main__":
    main()
