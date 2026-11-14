# SEAGIS NASA Regional Coastal Extractor — Implementation Task

## Mission
Build a reproducible, resumable Python CLI to extract **daily regional coastal sea-surface temperature (SST)** and **chlorophyll-a** for Southeast Asian seaweed-farming study regions, from **2020-01-01 through 2026-11-14 inclusive**. The user will provide credentials when needed. **No historical data download is allowed before a preflight estimate and explicit approval.**

## Non-negotiable acceptance criteria
1. `seagis-extract plan --config config/extraction.yaml` makes **metadata-only** calls and produces `outputs/plan.json`, `outputs/estimate.csv`, and a human-readable summary. It must not download science granules or bulk data.
2. The plan reports **per dataset × ROI × month**: bounding box, grid dimensions, days, expected valid/available days if knowable, estimated transfer bytes (range), expected uncompressed array bytes, peak temporary disk, projected retained raw bytes, projected final Parquet/CSV bytes, API call count, estimate confidence, assumptions and unknowns.
3. `seagis-extract fetch --plan outputs/plan.json --approve-plan <sha256>` refuses to run unless the plan hash matches and approval is explicit. `--max-download-gb` and `--max-disk-gb` are hard limits; fail closed if an upper bound cannot be established, unless an explicit per-batch override is approved.
4. Validate a **7-day, small-area pilot** for Tawi-Tawi and South Sulawesi before permitting full backfill. Verify data units, timestamps, latitude ordering, coastline mask, nulls, and output.
5. No fabricated or unverified farm polygons. Every ROI has provenance and status `candidate`, `literature_verified`, or `field_verified`. Keep candidate coastal zones separate from validated farming sites.
6. Idempotent resume, bounded concurrency, exponential backoff, checksums, manifest, per-batch logs, and error classification. Never commit credentials.
7. Produce one daily row per ROI/subregion/dataset/variable with valid-pixel count, coverage, mean/min/max/std, units, provenance, and QC flags; preserve the distinction between missing data and zero.
8. Add tests with mock HTTP responses; no live credentials or bulk downloads in CI.

## Scope and regions
Normalize 18 unique regions, not 24 repeated literature entries. These are geographic **parent regions** and candidate subregion search targets, not verified farm extents:

| ID | Country | Parent region | Candidate coastal subregions |
|---|---|---|---|
| ID-SEA-SUL | Indonesia | Southeast Sulawesi | Buton, Muna, Wakatobi, Konawe |
| ID-SOUTH-SUL | Indonesia | South Sulawesi | Takalar, Jeneponto, Pangkep, Selayar |
| ID-N-JAVA-SEA | Indonesia | North Java Sea | Must resolve study-specific coastal sectors |
| ID-CENT-SUL | Indonesia | Central Sulawesi | Banggai, Morowali, Tomini Gulf |
| ID-NTB | Indonesia | West Nusa Tenggara | East Lombok, Sumbawa, Bima |
| ID-N-KAL | Indonesia | North Kalimantan | Nunukan, Tarakan, Sebatik |
| ID-MALUKU | Indonesia | Maluku | Seram, Kei, Aru; validate administrative coverage |
| PH-NE-BOHOL | Philippines | Northeastern Bohol | Identify actual study coast |
| PH-TAWI | Philippines | Tawi-Tawi | Bongao, Sitangkai, Sibutu |
| PH-PANG | Philippines | Pangasinan | Bolinao, Lingayen Gulf |
| PH-S-LUZON | Philippines | Southern Luzon | Study-specific extent required |
| PH-PALAWAN | Philippines | Palawan | Coron, Taytay, Roxas |
| PH-ZAMBOANGA | Philippines | Zamboanga City | Study-specific coast |
| PH-DAVAO-N | Philippines | Davao del Norte | Validate coastal extent; Samal is administratively separate |
| PH-E-SAMAR | Philippines | Eastern Samar | Study-specific coastal bays |
| PH-BATANGAS | Philippines | Batangas | Study-specific coastal bays |
| MY-SABAH | Malaysia | Sabah | Semporna / east Sabah; expand only with evidence |
| VN-KHANH-HOA | Vietnam | Khanh Hoa | Nha Trang Bay, Cam Ranh |

Store exact polygons as GeoJSON, with `region_id`, `subregion_id`, `geometry_version`, `source`, `source_date`, `status`, `buffer_km`, `review_notes`. **Do not invent final bounding-box coordinates.** Resolve source boundaries and inspect them before extraction.

## ROI methodology
- Acquire licensed/attributed administrative polygons, high-resolution coastlines, and land polygons (e.g., geoBoundaries, OSM-derived coastline, or validated local government sources). Document license and version.
- Use an appropriate projected metric CRS for buffering; create a configurable **0–10 km seaward buffer** as an initial *candidate*, intersect with study-specific coastal sectors and a marine mask, exclude land, then visually inspect island groups and inlets.
- Do not assume a coastal buffer proves seaweed cultivation. Maintain separate verified farming polygons when available.
- Dissolve or split as necessary to avoid overlapping ROI double counting. Store a grid-cell membership/weight table per dataset and ROI; account for partial-cell overlap and cell area.
- Chlorophyll-a daily cloud gaps must remain missing; report coverage and observation count. Do not treat a satellite grid cell as a point measurement at a farm.

## Data adapters
### SST
- Target: GHRSST MUR Level 4 v4.1 **daily**, `analysed_sst`; verify current collection ID, provider endpoint, time coordinate, units, fill values, and subset service using authoritative dataset metadata before implementation.
- Prefer NASA PO.DAAC/Harmony spatial + variable + temporal subset if supported; NOAA CoastWatch ERDDAP may be an alternative after validating dataset ID and query syntax.
- Preserve uncertainty/quality variables where provided and useful. Convert Kelvin to Celsius **only when source units are Kelvin**; never convert already-Celsius values.

### Chlorophyll-a
- Target: NASA Ocean Color **Level 3 mapped daily** chlorophyll-a. Choose and document a specific mission/product and resolution (e.g., MODIS Aqua versus VIIRS) based on actual temporal coverage and availability. Do not assume a single mission spans 2020–2026 continuously.
- Verify the current Ocean Color extraction/ordering/API and authentication workflow. Some endpoints may provide granule downloads rather than polygon subsetting: distinguish provider subset from local mask.
- Preserve native missingness, quality flags, and units (typically mg/m³, verify). Record mission/sensor/product changes and do not silently splice incompatible series.

## Preflight size estimation — MUST IMPLEMENT FIRST
The estimator must not fetch full science data. Use catalog metadata, granule inventories, HEAD/Content-Length if supported, HTTP range metadata where safe, dataset shape, chunking, compression metadata, and small **optional, explicitly approved** calibration samples only. If a service cannot predict its subset response size, report a range and `unknown` confidence rather than a precise figure.

For each dataset × ROI × month calculate:
- `n_time`, `n_lat`, `n_lon`, `n_variables`, dtype bytes; `uncompressed_bytes = sum(n_time*n_lat*n_lon*dtype_bytes per variable)` plus coordinate/metadata overhead.
- Estimate bounding-box transfer, which can be much larger than the retained polygon because provider subsets are usually rectangular. Report `bbox_cells`, `roi_ocean_cells`, `mask_efficiency = roi_ocean_cells / bbox_cells`.
- Transfer range from observed compression ratios for representative approved samples, or from known provider metadata. **Never equate uncompressed bytes with transfer bytes**.
- Peak disk includes concurrent in-flight downloads, decompression, intermediate masked files, and final outputs; show working-space assumptions.
- Retained raw strategy: `discard_after_validation` (default), `archive_subsets`, or `archive_all`; estimate each separately.
- Final aggregate size: estimate row count and bytes per row using a transparent schema-based model, with an optional calibration Parquet sample.
- Handle overlapping ROI bounding boxes: report naive sum and deduplicated/shared-fetch estimate if feasible.
- Print `LOW / EXPECTED / HIGH` for transfer and peak disk, plus a confidence label and data gaps.
- Display per-country, per-region, per-product, and grand totals in MiB/GiB/TiB; also show projected row counts and request counts.
- If the provider has no content-length, estimate from shape and compression calibration, label uncertain, and enforce conservative limits during execution.
- Preflight may perform only metadata requests by default. `--calibrate` requires separate consent and an explicit sample byte cap; distinguish its bytes from metadata-only planning.

Example console layout (values are placeholders, **not real estimates**):
```
REGION          DATASET   MONTH     TRANSFER LOW/EXPECTED/HIGH   PEAK DISK   CONFIDENCE
PH-TAWI         MUR       2020-01   unknown / unknown / unknown  unknown     pending metadata
...
TOTAL           ALL       2020-26   ...                          ...         ...
PLAN SHA256: ...
No historical data downloaded. Run fetch only after reviewing and approving the plan.
```

## Execution design
1. `catalog`: resolve product identifiers, versions, variable schemas, API endpoints and authentication requirements; cache metadata.
2. `regions build`: build candidate coastal GeoJSON from verified source geometry and manual study-area configuration. Export QA map and a review manifest.
3. `plan`: calculate exact query geometry and metadata-derived estimates; produce immutable plan hash.
4. `pilot`: with explicit approval, fetch 7 days for **two** small, reviewed subregions; compare returned file size to estimate; update calibration and re-plan.
5. `fetch`: iterate month × ROI × product; enforce budget and concurrency; write to `.part`, validate checksum/content, then atomically rename; resume completed batches.
6. `process`: open xarray datasets lazily; apply marine and ROI masks, area weighting, units conversion, daily grouping, QC, and coverage; write partitioned Parquet.
7. `validate`: report missing dates, duplicates, spatial bounds, outliers, sensor/product changes, coverage, uncertainty and rejected batches.
8. `export`: CSV and optional PostgreSQL/Supabase load via environment variables and upsert keys; do not modify production DB without separate approval.

## Proposed CLI
```
seagis-extract catalog --config config/extraction.yaml
seagis-extract regions build --config config/extraction.yaml
seagis-extract plan --config config/extraction.yaml
seagis-extract plan --config config/extraction.yaml --calibrate --max-sample-mb 20
seagis-extract pilot --plan outputs/plan.json --approve-plan <SHA256>
seagis-extract fetch --plan outputs/plan.json --approve-plan <SHA256> --max-download-gb 20 --max-disk-gb 30
seagis-extract validate --manifest outputs/manifest.jsonl
seagis-extract export --format parquet,csv
```

## Example config (edit after catalog/ROI validation)
```yaml
period:
  start: '2020-01-01'
  end: '2026-11-14'
regions_file: config/regions.yaml
roi_directory: data/roi
products:
  mur_sst:
    enabled: true
    temporal_resolution: daily
    variables: [analysed_sst]
    endpoint: discover_from_catalog
  chlorophyll_a:
    enabled: true
    temporal_resolution: daily
    mission: decide_after_catalog_review
    endpoint: discover_from_catalog
execution:
  batch: monthly
  concurrency: 2
  raw_retention: discard_after_validation
  metadata_only_preflight: true
  require_approval: true
  max_download_gb: 20
  max_disk_gb: 30
  retries: 5
```

## Secrets and credentials
- Ask for the required provider/account type **after** discovering which endpoint actually needs authentication. Support `.env` (gitignored), system keychain, or standard `.netrc`/Earthdata auth where appropriate.
- Never ask the user to paste passwords or tokens into source code, GitHub issues, terminal logs, or chat. Provide local setup instructions with placeholder variable names and secret-safe verification.
- Validate token expiry, redirects, provider auth domain, and error status without leaking secrets.

## Suggested repository structure
```
seagis-nasa-extractor/
  pyproject.toml
  README.md
  .env.example
  .gitignore
  config/{extraction.yaml,regions.yaml,products.yaml}
  data/{boundaries,roi,raw,processed}/
  src/seagis_extractor/{cli.py,catalog.py,roi.py,estimate.py,fetch.py,process.py,validate.py,export.py,auth.py,manifest.py}
  tests/{test_estimate.py,test_roi.py,test_fetch.py,test_process.py,test_auth.py}
  outputs/{plan.json,estimate.csv,manifest.jsonl,qa/}
```

## Deliverables and definition of done
- Working CLI and setup docs; region registry with provenance; reviewed candidate ROI GeoJSON; metadata-only cost/size preflight; explicit approval gate; two-region pilot; tested resume; quality-aware daily Parquet/CSV; manifest and validation report.
- Before any bulk download, present the user with: (1) exact datasets and coverage, (2) estimated transfer LOW/EXPECTED/HIGH, (3) estimated peak disk, (4) estimated retained storage, (5) estimated final aggregate size, (6) known uncertainty and missing coverage, (7) pilot results, (8) the plan hash and approval command.
- **Stop after producing the preflight plan and request approval. Do not automatically run the pilot or backfill.**
