# Source corpus for Ask SEAmon

One Markdown file per source, with a front matter block. Load with `node scripts/rag/ingest.mjs` (see the script header for the environment it needs). Only **verified** sources are used in answers.

```markdown
---
id: doi:10.1007-s10499-026-02486-2      # letters, digits and . _ : -  (no slashes)
title: Full title of the paper
citation: Authors (year). Title. Journal volume(pages). doi
doi: 10.1007/s10499-026-02486-2
url: https://doi.org/10.1007/s10499-026-02486-2
publisher: Springer
year: 2026
species: [Kappaphycus alvarezii]        # taxa as the paper states them
countries: [Philippines]
evidence_grade: B                       # per research/evidence/README.md
license: CC-BY-4.0                      # what we may store; if unsure, ask before adding text
verified_by: Name                       # leave out until a reviewer has checked the source
verified_on: 2026-11-20                 # YYYY-MM-DD, goes together with verified_by
---
## Section title
Text of the section, copied only as far as the licence allows. Use `##` headings; they
become the section shown with each citation.
```

Rules:

- `id`, `title`, `citation` and `license` are required. A typo in a key name stops the load, so a misspelled `verified_by` cannot leave a source silently unverified.
- Do not mark a source verified until the citation, species, geography and license have been checked against the original (list in `research/evidence/README.md`).
- Unverified sources can be loaded early. They are stored but never retrieved.
- Do not put text here that the licence does not allow us to redistribute. Store a short quoted passage with its page, or ask first.
