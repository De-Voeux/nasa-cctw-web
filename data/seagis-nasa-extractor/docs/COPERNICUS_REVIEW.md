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

## Scientific caveats

- **Resolution vs zone width.** At 0.25° (about 28 km), the BGC grid touches only 3–8 model cells per ROI, and **no BGC cell lies mostly inside any 5 km zone**. no3, po4 and pH therefore describe the waters around the zone, not the zone itself. Salinity at 1/12° (about 9 km) touches 11–43 cells per ROI.
- Coastal model cells may be land (fill). The count is unknown until data is read.
- Copernicus has 2026-11-14 but MUR does not (not yet published); that day is missing for SST only.
- Analysis-forecast (ANFC) values for recent weeks are revised as the system re-analyses. The product versions are 202311 (BGC) and 202406 (PHY).
- These are model outputs, not observations, and they should not be spliced with MUR or other sources.

## Access

Fetch needs a free **Copernicus Marine account** (Copernicus Marine Toolbox login). Do not paste the password into chat. Placeholders are in `.env.example`.
