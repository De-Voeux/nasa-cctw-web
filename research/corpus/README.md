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

## Sources added so far (all UNVERIFIED)

Prepared on 2026-11-15 from open-access papers. None has `verified_by`, so none is searchable yet. A reviewer must check each against the original (citation, species, places, licence, and that the converted text matches) and then add `verified_by` and `verified_on`.

| File | Source | How the text was obtained | Left out |
|---|---|---|---|
| `tahiluddin-2021-ice-ice-review.md` | Tahiluddin & Terzi 2021, *Marine Science and Technology Bulletin* 10(3), a review of causes, occurrence and control of ice-ice | PDF downloaded from the journal's site (dergipark.org.tr), converted column by column with `pdftotext` | Table 1 (bacteria isolated from infected seaweed; tables do not convert reliably), the reference list, author contact details, the ethics and contribution statements |
| `tahiluddin-2024-ice-ice-seasonal-sibutu.md` | Tahiluddin & Terzi 2024, *Plants* 13(15), 2157: a 12-month study of ice-ice prevalence in Sibutu, Tawi-Tawi, and its relation to physicochemical and weather parameters | Full-text XML from Europe PMC (PMC11314110, open-access subset), converted to Markdown | Reference list, acknowledgements and other back matter. Tables are kept as rows of text and figures as captions only |

Things the reviewer should know:

- **Licence of the 2021 paper.** The PDF prints no licence. `CC-BY` comes from the journal's entry in DOAJ and from OpenAlex. Confirm it on the journal page before verifying.
- **PDF conversion can lose hyphens at line ends.** Five compound words were repaired by hand (`ice-ice`, `disease-causing`, `pre-soaking`, `kappa-carrageenan`, `Ganzon-Fortes`); others may remain. Compare numbers and units against the PDF.
- Both papers are by the same authors, from the same research group. They are not independent confirmation of each other.

### Candidates that could not be fetched automatically

Three more CC-BY papers were found but their publishers block automated downloads (bot protection), so they were not fetched. They can be downloaded by hand in a browser and converted the same way:

- Kambey et al. 2021, *J Appl Phycol*, biosecurity measures for ice-ice and pests, doi 10.1007/s10811-021-02530-z
- Ward et al. 2019, *J World Aquaculture Soc*, review of seaweed diseases and pests in Asia, doi 10.1111/jwas.12649
- Lestari et al. 2026, *J Appl Phycol*, pathogenicity of bacteria from ice-ice infected *K. striatus*, doi 10.1007/s10811-025-03776-7

Not usable: the paper cited in the brief (Alimin et al. 2026, *Aquaculture International*, doi 10.1007/s10499-026-02486-2) is under Springer Nature's text-and-data-mining terms, not an open licence, so its text must not be stored here. The Tawi-Tawi prevalence paper of 2023 (doi 10.4194/aquast1137) shows no licence in OpenAlex; check the journal first.
