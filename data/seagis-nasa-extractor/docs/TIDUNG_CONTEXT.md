# Context: Pulau Tidung zone (proposal, 2026-11-15)

Proposal only: nothing has been built or fetched for Tidung yet.

## Goal

Use `seagis-extract` (this repo) to build a **daily historical baseline** for Pulau Tidung, the pilot site of the Seagis iOS app (`~/Documents/Apple/Seagis`, farms Dahlan Lahan 1 and 2). The app judges current conditions; the baseline adds "is this unusual for this time of year" and test data for its condition rules (`docs/condition-rules.md`).

## Sources (same as the current extractor)

| Source | Variables | Resolution | Meaning at Tidung |
|---|---|---|---|
| NASA MUR SST | SST, analysis error | ~1 km | Local; tens of cells around the island |
| Copernicus PHY | salinity, currents (speed, direction, steadiness) | ~9 km | A few cells; surrounding waters |
| GPM IMERG Late | rainfall | ~11 km | 1–4 cells |
| Copernicus BGC | nitrate, phosphate, pH | ~28 km | 1 cell, may include Jakarta Bay influence; **check for a sea cell** |
| NASA POWER | air temp, RH, wind, radiation, PAR, cloud | ~50 km | Regional weather |

Only SST is truly local. Every other source must be labelled **regional model/satellite context**, never field observation (app README rule).

## Decisions needed

1. **Zone shape.** Admin units are too coarse: Kecamatan Kepulauan Seribu Selatan covers many islands. Choose one:
   - the island polygon plus a 2–5 km sea buffer; or
   - the farm coordinates plus a small buffer.

   Either way the extractor needs a small feature: a custom polygon or point ROI source.
2. **Period.** The zone is tiny, so several years cost little. Copernicus ANFC only reaches back a few years; a longer baseline needs the reanalysis products, which are separate datasets.
3. **Units vs the app.** The app rules use currents in **cm/s** and nutrients in **mg/L**; the extractor uses m/s and mmol/m³. Pick one conversion point. The app also has an open question: nitrate as the ion vs as N (about 4.4×).
4. **Target DB.** Either this project's Supabase or the app's own `supabase/`. Do not write to the app DB without explicit confirmation.

## Steps

1. Wait until the current backfill and export are done: a new zone changes the plan hash.
2. Add region `ID-TIDUNG` with the chosen geometry, then run `plan` (metadata only). Check:
   - cells per source;
   - that BGC has a sea cell;
   - the transfer size.
3. Review and approve the hash, run `fetch --region ID-TIDUNG`, then `export`.
4. Hand the app the table, the units and the regional-context labelling.

## Constraints carried over

- Plan-hash approval before any download.
- Only data for the defined zone.
- No synthetic or gap-filled values.
- Credentials stay in `.env` only.
