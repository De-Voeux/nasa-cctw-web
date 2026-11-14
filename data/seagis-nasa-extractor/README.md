# SEAGIS NASA regional coastal extractor

**Status (2026-11-15):** `catalog`, `regions build`, `plan` and `pilot` are implemented.

- `catalog` has been run against live NASA metadata ([docs/CATALOG_REVIEW.md](docs/CATALOG_REVIEW.md)).
- `regions build` has produced 47 candidate zones in 17 regions ([docs/ROI_REVIEW.md](docs/ROI_REVIEW.md)).
- `plan` has produced a metadata-only preflight ([docs/PLAN_REVIEW.md](docs/PLAN_REVIEW.md)).
- `pilot` was run with the user's approval and PASSED (7 days, 2 zones).
- `plan` was re-generated with the pilot calibration.
- `fetch` is built and tested against fakes, but the full backfill has not been run.
- `process`, `validate` and `export` (to the database) are not implemented.

Only pilot data (~1 MB) has been downloaded. Pilot/fetch dependencies install with `uv pip install --python .venv '.[fetch]'`. Full specification: [TASK.md](TASK.md).

```bash
uv venv .venv && uv pip install --python .venv '.[dev]'   # reinstall after code changes
.venv/bin/python -m pytest -q
.venv/bin/seagis-extract catalog --config config/extraction.yaml   # metadata only, ~1 min
.venv/bin/seagis-extract regions build                              # needs data/boundaries (config/boundary_sources.yaml)
.venv/bin/seagis-extract plan                                       # metadata only; outputs/plan.json, estimate.csv
```

Install non-editable: in this iCloud-synced folder macOS keeps flagging `.pth` files hidden, and Python then skips them, so an editable install breaks (`No module named 'seagis_extractor'`). Without installing: `PYTHONPATH=src .venv/bin/python -m seagis_extractor catalog`.

Python CLI that will extract daily regional coastal SST (GHRSST MUR L4) and Copernicus Marine surface no3, po4, pH and salinity ([docs/COPERNICUS_REVIEW.md](docs/COPERNICUS_REVIEW.md)) for the candidate seaweed regions, over the period set in [config/extraction.yaml](config/extraction.yaml) (currently 2022-06-01 to 2026-11-14 for all sources). It is the NASA ingestion piece of the [roadmap](../../docs/ROADMAP.md) ("Data foundation") and must follow the project [methodology guardrails](../../docs/METHODOLOGY.md).

## Ground rules

- **Scope:** NASA MUR SST plus Copernicus Marine no3, po4, pH and salinity. Chlorophyll-a was dropped on 2026-11-15; [TASK.md](TASK.md) still describes it, and those parts no longer apply.
- `plan` is metadata-only. No pilot or backfill runs without an approved plan hash.
- Regions in [config/regions.yaml](config/regions.yaml) are **candidate** leads from [CANDIDATE_HOST_REGIONS.md](../../research/evidence/CANDIDATE_HOST_REGIONS.md); none is a verified farm. No invented coordinates.
- Missing data stays missing (never zero). Units are converted only when the source says so.
- Secrets live in `.env` or `~/.netrc` (both gitignored); see [.env.example](.env.example).

## Layout

```
config/          extraction.yaml, regions.yaml, products.yaml
data/            boundaries/ roi/ raw/ processed/   (contents gitignored)
src/seagis_extractor/   cli, catalog, roi, estimate, fetch, process, validate, export, auth, manifest
tests/           mock-HTTP tests only
outputs/         plan.json, estimate.csv, manifest.jsonl, qa/   (gitignored)
```

## Order of work

1. `catalog` — verify collection IDs, endpoints, units, auth.
2. `regions build` — candidate coastal ROI GeoJSON from licensed boundaries.
3. `plan` — size/cost preflight, plan hash. **Stop and request approval.**
4. `pilot` (Tawi-Tawi + South Sulawesi, 7 days) → `fetch` → `process` → `validate` → `export`.
