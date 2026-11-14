# Copernicus Marine datasets — 2026-11-15

Requested by the user: nitrate (no3), phosphate (po4) and pH from GLOBAL_ANALYSISFORECAST_BGC_001_028, and salinity from GLOBAL_ANALYSISFORECAST_PHY_001_024. The period is **2022-06-01 .. 2026-11-14**. It was first requested from 2021-11-15, then moved by the user to the first day of daily salinity, and MUR was aligned to the same start. Everything below comes from public metadata: the STAC catalogue, Zarr `.zmetadata`, coordinate arrays of a few KB, and one HEAD per data chunk. No science data was downloaded.

## Datasets (verified)

| Key | Dataset | Variables | Grid | Daily coverage in period |
| --- | --- | --- | --- | --- |
| cmems_bgc_nut | `cmems_mod_glo_bgc-nut_anfc_0.25deg_P1D-m_202311` | no3, po4 (mmol m-3) | 0.25° | 1628 / 1628 days (dataset starts 2021-11-01) |
| cmems_bgc_car | `cmems_mod_glo_bgc-car_anfc_0.25deg_P1D-m_202311` | ph (total scale, unitless) | 0.25° | 1628 / 1628 days |
| cmems_phy_so | `cmems_mod_glo_phy-so_anfc_0.083deg_P1D-m_202406` | so (1e-3, i.e. PSU-like) | 1/12° | 1628 / 1628 days (daily salinity starts 2022-06-01, which is why the period starts there) |

- Depth: surface only. This is the shallowest model level, 0.494 m (50 levels exist).
- Time: daily means stamped 00:00 UTC.
- Fill: 9.97e36.
- Storage: float32, blosc-lz4.
- Daily surface salinity does not exist in this product before 2022-06-01 (the merged PHY daily dataset has only bottom salinity `sob`, also from 2022-06-01), which is why every source starts on that date.
- Credit: "E.U. Copernicus Marine Service Information". Licence: Copernicus Marine service licence.

## True transfer size (exact)

Reads go through the ARCO `geoChunked` Zarr store. A subset downloads every chunk it touches, so the true transfer is the sum of those chunks' Content-Length, measured with one HEAD request per chunk.

| Dataset | PH-TAWI | ID-SOUTH-SUL | **Total** | If fetched in monthly batches |
| --- | ---: | ---: | ---: | ---: |
| no3 + po4 | 32.6 MiB | 33.7 MiB | **66.3 MiB** | 386 MiB |
| pH | 11.3 MiB | 11.6 MiB | **22.9 MiB** | 133 MiB |
| salinity | 14.5 MiB | 25.7 MiB | **40.2 MiB** | 209 MiB |
| **Total** | | | **129.4 MiB** | 728 MiB |

- **Batching:** one subset per region × dataset for the whole period. Chunks span 134–156 days, so monthly batches would re-download the same chunks about 6×.
- **Shared chunks:** the 7 ROIs share chunks. Fetching each ROI separately would read the same chunks several times over.
- **Kept data is tiny:** the NetCDF subsets on disk are at most 6.3 MiB, giving 45,584 daily rows.
- **Combined with MUR:** about **481 MiB** in total (MUR expected 352 MiB + Copernicus 129 MiB) for the same 2022-06-01 .. 2026-11-14 period. MUR's figure is still a LOW-confidence estimate.

## Download scope

ARCO chunks are large tiles: 8°×16° for BGC and 2.7°×5.3° for salinity. The service cannot send less than a whole tile, so the bytes on the wire cover more area than the zones. Only cells inside each ROI request box are kept, and nothing else is written to disk. Region boxes touch no chunks beyond those the ROI boxes need. These rules are recorded in `plan.json` → `copernicus.fetch_guards`.

## Update 2026-11-15: all 47 zones

| Dataset | Per region | With shared chunk cache |
| --- | ---: | ---: |
| no3 + po4 | 758 MiB | 332 MiB |
| pH | 266 MiB | 117 MiB |
| salinity | 466 MiB | 354 MiB |
| **Total** | **1.46 GiB** | **803 MiB** |

- **Why the two columns differ.** BGC chunks are 8°×16° tiles, so one tile serves several regions; Tawi-Tawi, Sabah and Zamboanga, for example, share tiles. Reading every chunk once, through a shared chunk cache, is the cheaper path, and fetch should be built that way.
- **Sea cells per zone:**
  - no3/po4/pH: median 5, maximum 25.
  - salinity: minimum 2, median 19, maximum 112.
- **Accepted exceptions.** Labrador, Lingayen and Binmaley (PH-PANG) have **no sea cell for BGC** because the inner Lingayen Gulf is land at 0.25°. They are listed in `config/extraction.yaml` → `no_sea_accepted` and recorded in `plan.json` → `copernicus.unavailable_by_decision`. Their no3/po4/pH are left empty, with no filling and no proxy. Any other zone without sea still blocks `plan`.
- The tables below describe the first 7 zones.

## Sea cells per zone (verified with the static mask)

Each model has a fixed land/sea mask (1 = sea, 0 = land). Its surface level was read for the region boxes only: BGC `cmems_mod_glo_bgc_anfc_0.25deg_static_202311--ext--mask` chunk `mask/49.0.0` (38,714 bytes) and PHY `cmems_mod_glo_phy_anfc_0.083deg_static_202211--ext--bathy` chunk `mask/49.1.3` (26,276 bytes). Both are cached in `data/raw/static/copernicus/` (gitignored), and their SHA-256 values are in `plan.json`. The plan checks that each mask grid is identical to its data grid.

"Sea weight" is the sum of overlap fractions of the sea cells: roughly how many full model cells of sea the zone covers.

| ROI | BGC touched | BGC sea | BGC sea weight | Salinity touched | Salinity sea | Salinity sea weight |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PH-TAWI/bongao | 4 | 3 | 0.36 | 11 | 8 | 2.97 |
| PH-TAWI/sitangkai | 7 | 7 | 0.86 | 20 | 16 | 5.30 |
| PH-TAWI/sibutu | 3 | 3 | 0.49 | 15 | 11 | 3.31 |
| ID-SOUTH-SUL/takalar | 5 | 3 | 0.68 | 20 | 18 | 7.65 |
| ID-SOUTH-SUL/jeneponto | 6 | 3 | 0.38 | 16 | 12 | 4.04 |
| ID-SOUTH-SUL/pangkep | 8 | 6 | 1.45 | 39 | 39 | 18.79 |
| ID-SOUTH-SUL/selayar | 8 | 7 | 1.51 | 43 | 38 | 16.90 |

- **Every zone has at least 3 sea cells for no3/po4/pH and at least 8 for salinity.** `zones_without_sea` is empty. `plan` exits with code 3 and lists the zones if any zone ever has none.
- Land cells are dropped. Each membership table (`outputs/membership/cmems_*.csv.gz`) has a `sea` column, and fetch/process must use only the cells marked sea.
- Bongao and Jeneponto are the weakest for BGC: the sea cells cover only about a third of one model cell in total, so their no3/po4/pH comes almost entirely from cells centred outside the zone.
- The mask says where the model has ocean. It does not prove that every daily value is non-null; the pilot checks this.

## Scientific caveats

- **Resolution vs zone width.** At 0.25° (about 28 km), the BGC grid touches only 3–8 model cells per ROI. Only one BGC cell (in Pangkep) lies mostly inside a 5 km zone; everywhere else no3, po4 and pH describe the waters around the zone, not the zone itself. Salinity at 1/12° (about 9 km) touches 11–43 cells per ROI.
- Copernicus has 2026-11-14 but MUR does not (not yet published); that day is missing for SST only.
- Analysis-forecast (ANFC) values for recent weeks are revised as the system re-analyses. The product versions are 202311 (BGC) and 202406 (PHY).
- These are model outputs, not observations, and they should not be spliced with MUR or other sources.

## Access

Fetch needs a free **Copernicus Marine account** (Copernicus Marine Toolbox login). Do not paste the password into chat. Placeholders are in `.env.example`.
