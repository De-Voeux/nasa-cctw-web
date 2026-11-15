// Provisional environmental screening rules. These are not disease thresholds.
// Keep each rule traceable to a published source before changing its values.
export const ALL_SPECIES = "All species"

export const ENVIRONMENT_RULES = {
  "Kappaphycus alvarezii": {
    sst: { min: 27, max: 30, source: "Impact of elevated temperature on Kappaphycus alvarezii (2020)" },
    salinity: { min: 30, max: 35, source: "Seaweed farming water-quality guidance" },
  },
  "Eucheuma denticulatum": {
    sst: { min: 25, max: 30, source: "PNS/BAFS 208:2021" },
    salinity: { min: 27, max: 35, source: "PNS/BAFS 208:2021" },
  },
}

const levelFor = (outside) => outside === 0 ? "favorable" : outside === 1 ? "moderate" : "elevated"

export function scoreEnvironment(items, species) {
  const rules = ENVIRONMENT_RULES[species]
  if (!rules) return { scored: false, level: "insufficient", reason: "Species-specific rules are not active." }

  const evaluated = []
  for (const [key, rule] of Object.entries(rules)) {
    const item = items.find((candidate) => candidate.key === key)
    const value = item?.values?.[item.values.length - 1]
    if (!Number.isFinite(value)) continue
    evaluated.push({ key, value, rule, outside: value < rule.min || value > rule.max })
  }
  if (evaluated.length < Object.keys(rules).length) {
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
