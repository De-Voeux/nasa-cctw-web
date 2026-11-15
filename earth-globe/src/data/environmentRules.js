// Provisional environmental screening rules. These are not disease thresholds.
// Keep each rule traceable to a published source before changing its values.
export const ALL_SPECIES = "All species"

// Farm-site range for the eucheumatoid group, from Juanich (1988), Manual on Seaweed Farming 1:
// Eucheuma spp., ASEAN/UNDP/FAO, https://www.fao.org/4/ac416e/AC416E00.htm. The manual names
// Eucheuma striatum, now Kappaphycus striatus, as a main cultivated species. It is a site-suitability
// range for farming, not a disease threshold.
const ASEAN_FAO_1988 = "ASEAN/FAO Manual on Seaweed Farming: Eucheuma spp. (1988), farm-site range"
const EUCHEUMATOID_SITE = {
  sst: { min: 25, max: 30, source: ASEAN_FAO_1988 },
  salinity: { min: 27, max: 35, source: ASEAN_FAO_1988 },
}

// Gracilaria is farmed in brackish ponds (tambak), not in the open sea. Range from Trono (1988),
// Manual on Seaweed Culture: Pond culture of Caulerpa and pond culture of Gracilaria, ASEAN/UNDP/FAO,
// https://www.fao.org/4/ac417e/AC417E00.htm, which names G. "verrucosa" as the most cultured species:
// salinity 20–28 ppt (site selection), water 20–25 (29) °C (pond management; 29 used as the upper limit).
// The dashboard's values are for the sea off the coast, so they say little about pond water.
const TRONO_1988 = "ASEAN/FAO Manual on Seaweed Culture: Gracilaria pond culture (1988), pond range"
const GRACILARIA_POND = {
  habitat: "pond",
  sst: { min: 20, max: 29, source: TRONO_1988 },
  salinity: { min: 20, max: 28, source: TRONO_1988 },
}

export const ENVIRONMENT_RULES = {
  "Kappaphycus alvarezii": {
    sst: { min: 27, max: 30, source: "Impact of elevated temperature on Kappaphycus alvarezii (2020)" },
    salinity: { min: 30, max: 35, source: "Seaweed farming water-quality guidance" },
  },
  "Eucheuma denticulatum": {
    sst: { min: 25, max: 30, source: "PNS/BAFS 208:2021" },
    salinity: { min: 27, max: 35, source: "PNS/BAFS 208:2021" },
  },
  "Kappaphycus striatus": EUCHEUMATOID_SITE,
  "Kappaphycus spp.": EUCHEUMATOID_SITE,
  "Gracilaria verrucosa": GRACILARIA_POND,
}

const levelFor = (outside) => outside === 0 ? "favorable" : outside === 1 ? "moderate" : "elevated"

export function scoreEnvironment(items, species) {
  const rules = ENVIRONMENT_RULES[species]
  if (!rules) return { scored: false, level: "insufficient", reason: "Species-specific rules are not active." }

  const evaluated = []
  const ranges = Object.entries(rules).filter(([, rule]) => rule && typeof rule === "object" && "min" in rule)
  for (const [key, rule] of ranges) {
    const item = items.find((candidate) => candidate.key === key)
    const value = item?.values?.[item.values.length - 1]
    if (!Number.isFinite(value)) continue
    evaluated.push({ key, value, rule, outside: value < rule.min || value > rule.max })
  }
  if (evaluated.length < ranges.length) {
    return { scored: false, level: "insufficient", reason: "Required environmental observations are incomplete." }
  }

  const outside = evaluated.filter((x) => x.outside).length
  return {
    scored: true,
    provisional: true,
    level: levelFor(outside),
    evaluated,
    outside,
    condition: outside === 0
      ? "All active indicators are within provisional reference ranges"
      : `${outside} active indicator${outside === 1 ? " is" : "s are"} outside provisional reference ranges`,
  }
}
