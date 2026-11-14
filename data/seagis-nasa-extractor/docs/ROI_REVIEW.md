# Candidate ROI review — 2026-11-15 (geometry v1)

Built with `seagis-extract regions build` for the two pilot regions. All ROIs have `status: candidate`. They are coastal zones near administrative units and **do not show where seaweed is farmed**.

- GeoJSON: [`data/roi/roi_candidates_v1.geojson`](../data/roi/roi_candidates_v1.geojson), 6.2 MB, EPSG:4326
- QA maps and review sheet (gitignored, regenerate with the command): `outputs/qa/roi_PH-TAWI.png`, `outputs/qa/roi_ID-SOUTH-SUL.png`, `outputs/qa/roi_review_manifest.csv`

## Inputs

- Boundaries: geoBoundaries gbOpen PHL ADM3 (2020) and IDN ADM2 (2020), CC BY 3.0 IGO. URLs, commits and SHA-256 are in [`config/boundary_sources.yaml`](../config/boundary_sources.yaml). PHL ADM2 was also downloaded but is not used yet.
- Unit names: [`config/roi_sources.yaml`](../config/roi_sources.yaml). Each name matched exactly one feature.
- Buffer: 5 km seaward (agreed 2026-11-15), computed in UTM 50N or 50S.

## Method

1. Buffer each admin unit 5 km.
2. Subtract the land mask, which is the union of all admin polygons from the same file near the unit.
3. For the archipelagic regencies Pangkep and Selayar, keep only the polygon parts near the unit's largest landmass (agreed 2026-11-15). The distance limits sit in natural gaps measured on the source polygons. **Pangkep: 60 km.** The nearest 45 of 117 parts lie within 57.5 km, and the next one is at 118.7 km, so the Spermonde group is kept. **Selayar: 35 km.** The nearest 16 of 98 parts lie within 30.0 km, and the next one is at 45.8 km, so Takabonerate and the southern islands are dropped. Dropped islands still count as land and as neighbouring coast.
4. Split the sea by nearest coast among the selected units and their unselected admin neighbours. Sibling ROIs therefore never overlap, and no ROI takes water off a neighbouring unit's coast (for example, Takalar no longer extends into the waters off Makassar).

## Results

| Region | Subregion | Area km² | Before split | Parts | Note |
| --- | --- | ---: | ---: | ---: | --- |
| PH-TAWI | bongao | 277.9 | 330.0 | 1 | Proposed pilot unit |
| PH-TAWI | sitangkai | 656.6 | 742.6 | 3 | Western circles sit around tiny islets |
| PH-TAWI | sibutu | 375.2 | 462.2 | 1 | |
| ID-SOUTH-SUL | takalar | 654.0 | 699.0 | 1 | Proposed pilot unit; includes the Tanakeke islands |
| ID-SOUTH-SUL | jeneponto | 352.8 | 399.5 | 1 | |
| ID-SOUTH-SUL | pangkep | 1602.1 | 1674.8 | 4 | Spermonde group only; bbox 118.91–119.60°E, 5.00–4.44°S (was 117.0–119.6°E) |
| ID-SOUTH-SUL | selayar | 1496.6 | 1507.4 | 3 | Main island and nearby islets; bbox 120.22–120.61°E, 6.76–5.70°S (Takabonerate dropped) |

## Known limitations / to review

- Coastline accuracy comes from the admin polygons (NAMRIA/PSA, BPS). They have not been compared with an independent coastline such as OSM. The MUR `mask` will be compared during the pilot.
- Pangkep and Selayar are limited by distance from the main landmass, not by study evidence. If a paper places farms on the dropped islands (for example Takabonerate), raise the limit in `config/roi_sources.yaml`.
- Parent-level (province) ROIs are not built yet. The other 16 regions still need unit names, boundary files (MY, VN), and sources for the study-specific coasts.
- Reprojection leaves land/zone slivers of tens of m², far below one MUR cell (~1 km²).
- Visual review: fill in `review_status`, `reviewer` and `review_date` in the review sheet.


## All regions (added 2026-11-15)

Built with the rules agreed on 2026-11-15:

- Names are matched exactly as written in the research (no Buton/Muna/Konawe variants).
- Gulfs and islands are mapped to the admin units that hold their coast:
  - Tomini Gulf → Parigi Moutong, Poso, Tojo Una-Una
  - Lingayen Gulf → Pangasinan shore municipalities
  - Seram → Seram Bagian Barat + Timur
  - Kei → Maluku Tenggara + Kota Tual
  - Aru → Kepulauan Aru
  - Nha Trang Bay → Nha Trang city
- Regions with no named site use the whole provincial or city coast and are marked **PROVISIONAL**: NE Bohol, Zamboanga City, Davao del Norte, Eastern Samar and Batangas.
- Southern Luzon stays **pending** because it is not an administrative unit.

New boundary files: geoBoundaries MYS ADM2 and VNM ADM2, pinned to commit 9469f09 with their SHA-256 in `config/boundary_sources.yaml`. Philippine municipalities with duplicate names (Roxas, Taytay, Anda) are matched inside their province polygon, not by coordinates. The full mapping and notes per region are in `config/roi_sources.yaml`.

Result: 47 zones, listed in `outputs/qa/roi_review_manifest.csv` with maps in `outputs/qa/roi_<region>.png`. All are `candidate` / `pending_visual_review`.

Points to review:

- **Mangaldan** was removed from Lingayen Gulf. Its admin polygon gets no sea of its own after the nearest-coast split.
- **Davao del Norte** includes the Island Garden City of Samal, which the research notes as administratively separate.
- **Sebatik** has no separate zone. The Indonesian half lies inside the Nunukan regency polygon.
- **Seram Bagian Barat** includes small islets near 1.5° S, far north of Seram. Check whether they belong to the study.
- **Kepulauan Aru** includes the channels between the Aru islands, which count as sea in the admin data.
- **Labrador, Lingayen and Binmaley** have no sea cell in the 0.25° Copernicus BGC grid, so their no3/po4/pH are left empty and flagged (decision 2026-11-15). SST and salinity are available.
