import { ALL_SPECIES, scoreEnvironment } from "./environmentRules.js"

const NOT_ASSESSED = [
  { name: "Disease-linked biological risk", why: "Environmental screening is not a validated disease or pathogen assessment." },
  { name: "Disease presence", why: "Environmental observations cannot diagnose ice-ice or identify a pathogen." },
  { name: "Forecast", why: "The current extractor response contains observations/analysis, not a validated 10-day forecast." },
]

const dateValue = (s) => new Date(`${s}T00:00:00Z`)

export async function loadEnvironment(fetchImpl = fetch) {
  const response = await fetchImpl("/api/environment", { headers: { accept: "application/json" } })
  if (!response.ok) throw new Error(`environment request failed (${response.status})`)
  const body = await response.json()
  if (!body || typeof body !== "object" || typeof body.regions !== "object") throw new Error("invalid environment response")
  return body
}

export function assessmentFor(loc, payload, species = ALL_SPECIES) {
  const region = loc.dataRegionId ? payload?.regions?.[loc.dataRegionId] : null
  const series = region?.series ? Object.values(region.series) : []
  if (!series.length) {
    return { level: "insufficient", condition: "No observed data available for this region", demo: false, observed: false }
  }

  const items = series.map((item) => ({
    ...item,
    dates: item.dates.map(dateValue),
    headline: `Observed through ${region.latest_date}`,
    driver: false,
    baseline: null,
  }))
  const score = scoreEnvironment(items, species)
  for (const item of items) item.driver = score.evaluated?.some((x) => x.key === item.key && x.outside) || false
  const dates = items.reduce((out, item) => {
    for (const date of item.dates) if (!out.some((x) => x.getTime() === date.getTime())) out.push(date)
    return out.sort((a, b) => a - b)
  }, [])
  return {
    level: score.scored ? score.level : "insufficient",
    condition: score.scored ? score.condition : `Observed data available through ${region.latest_date}`,
    demo: false,
    observed: true,
    scored: score.scored,
    data: {
      dates,
      todayIndex: Math.max(0, dates.length - 1),
      items,
      confidence: score.scored ? "Provisional rule-based" : "Observed",
      notAssessed: score.scored
        ? [...NOT_ASSESSED, { name: "Rule provenance", why: `${score.evaluated.map((x) => x.rule.source).join("; ")}. Rules are provisional.` }]
        : NOT_ASSESSED,
      latestDate: region.latest_date,
    },
  }
}

export { NOT_ASSESSED }
