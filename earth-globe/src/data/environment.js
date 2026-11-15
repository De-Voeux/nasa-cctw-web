import { ALL_SPECIES, ENVIRONMENT_RULES, scoreEnvironment } from "./environmentRules.js"

const NOT_ASSESSED = [
  { name: "Disease-linked biological risk", why: "Environmental screening is not a validated disease or pathogen assessment." },
  { name: "Disease presence", why: "Environmental observations cannot diagnose ice-ice or identify a pathogen." },
  { name: "Forecast interpretation", why: "Three-day Copernicus outlook values are environmental forecasts, not a disease diagnosis." },
]

const dateValue = (s) => new Date(`${s}T00:00:00Z`)

const LEVEL_RANK = { favorable: 0, moderate: 1, elevated: 2 }
const short = (name) => name.replace(/^(\w)\w+ /, "$1. ")

const withPondNote = (score, species) =>
  score.scored && ENVIRONMENT_RULES[species]?.habitat === "pond"
    ? { ...score, condition: `${score.condition}. ${short(species)} is farmed in coastal ponds; these values are for the open sea nearby, so treat this as a rough guide` }
    : score

/**
 * Score with the picked species' rules. When it has none ("All species", or a taxon
 * without published ranges), use the rules of the species reported at this place and
 * keep the worst result. Returns the species whose rules decided the level.
 */
export function scoreFor(loc, items, species) {
  if (ENVIRONMENT_RULES[species]) return { score: withPondNote(scoreEnvironment(items, species), species), ruleSpecies: species }
  // Pond species are judged by open-sea values only when nothing else is farmed here.
  const withRules = (loc.taxa || []).filter((t) => ENVIRONMENT_RULES[t])
  const atSea = withRules.filter((t) => ENVIRONMENT_RULES[t].habitat !== "pond")
  const candidates = atSea.length ? atSea : withRules
  const scored = candidates.map((t) => ({ t, s: scoreEnvironment(items, t) })).filter((x) => x.s.scored)
  if (!scored.length) {
    const reason = species !== ALL_SPECIES
      ? `No published safe range for ${species} yet`
      : candidates.length ? null : `No published safe range yet for the seaweed reported here (${(loc.taxa || []).join(", ")})`
    return { score: { scored: false, level: "insufficient", reason }, ruleSpecies: null }
  }
  const worst = scored.reduce((a, b) => (LEVEL_RANK[b.s.level] > LEVEL_RANK[a.s.level] ? b : a))
  return {
    score: withPondNote({ ...worst.s, condition: `${worst.s.condition} for ${short(worst.t)}, the reported seaweed here` }, worst.t),
    ruleSpecies: worst.t,
  }
}

export async function loadEnvironment(fetchImpl = fetch) {
  const response = await fetchImpl("/api/environment", { cache: "no-store", headers: { accept: "application/json" } })
  if (!response.ok) throw new Error(`environment request failed (${response.status})`)
  const body = await response.json()
  if (!body || typeof body !== "object" || typeof body.regions !== "object") throw new Error("invalid environment response")
  return body
}

const todayDate = (payload) => dateValue(payload?.as_of_date || new Date().toISOString().slice(0, 10))

export function assessmentFor(loc, payload, species = ALL_SPECIES) {
  const region = loc.dataRegionId ? payload?.regions?.[loc.dataRegionId] : null
  const series = region?.series ? Object.values(region.series) : []
  if (!series.length) {
    return { level: "insufficient", condition: "No observed data available for this region", demo: false, observed: false }
  }

  const items = series.map((item) => {
    const observedDates = (item.dates || []).map(dateValue)
    const forecastDates = (item.forecast_dates || []).map(dateValue)
    const observedValues = item.values || []
    const forecastValues = item.forecast_values || []
    return {
      ...item,
      dates: [...observedDates, ...forecastDates],
      values: [...observedValues, ...forecastValues],
      coverage: [...(item.coverage || []), ...(item.forecast_coverage || [])],
      todayIndex: Math.max(0, observedDates.length - 1),
      observedCount: observedDates.length,
      todayDate: todayDate(payload),
      headline: `Observed through ${region.latest_date}`,
      forecastHeadline: forecastDates.length ? `Forecast through ${forecastDates[forecastDates.length - 1].toISOString().slice(0, 10)}` : null,
      forecastSource: item.forecast_source || null,
      forecastProductVersion: item.forecast_product_version || null,
      driver: false,
      baseline: null,
    }
  })
  const scoreItems = items.map((item) => ({ ...item, values: item.values.slice(0, item.observedCount) }))
  const { score, ruleSpecies } = scoreFor(loc, scoreItems, species)
  for (const item of items) item.driver = score.evaluated?.some((x) => x.key === item.key && x.outside) || false
  const dates = items.reduce((out, item) => {
    for (const date of item.dates) if (!out.some((x) => x.getTime() === date.getTime())) out.push(date)
    return out.sort((a, b) => a - b)
  }, [])
  return {
    level: score.scored ? score.level : "insufficient",
    condition: score.scored ? score.condition : (score.reason || `Observed data available through ${region.latest_date}`),
    ruleSpecies,
    demo: false,
    observed: true,
    scored: score.scored,
    data: {
      dates,
      todayIndex: Math.max(0, items.reduce((latest, item) => Math.max(latest, item.todayIndex ?? 0), 0)),
      items,
      confidence: score.scored ? (items.some((item) => item.forecast_dates?.length) ? "Provisional rule-based · 3-day outlook" : "Provisional rule-based")
        : (items.some((item) => item.forecast_dates?.length) ? "Observed + 3-day outlook" : "Observed"),
      notAssessed: score.scored
        ? [...NOT_ASSESSED, { name: "Rule provenance", why: `${score.evaluated.map((x) => x.rule.source).join("; ")}. Rules are provisional.` }]
        : NOT_ASSESSED,
      latestDate: region.latest_date,
      todayDate: todayDate(payload),
    },
  }
}

export { NOT_ASSESSED }
