// Structured knowledge for the Ask SEAmon tools that does not live in the database:
// - long-term trends 2003–2024 per region (earth-globe/src/data/longTermTrends.json, built by
//   data/seagis-nasa-extractor/scripts/build_trends.py from seagis_monthly_metrics);
// - the provisional safe ranges the dashboard rates with (earth-globe/src/data/environmentRules.js).
// The same files feed the dashboard, so the assistant and the page cannot disagree.

import LONG_TERM from "../earth-globe/src/data/longTermTrends.json" with { type: "json" }
import { ENVIRONMENT_RULES } from "../earth-globe/src/data/environmentRules.js"
import { LOCATIONS } from "../earth-globe/src/data/reportedLocations.js"

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
const NAMES = Object.fromEntries(LOCATIONS.filter((l) => l.dataRegionId).map((l) => [l.dataRegionId, { name: l.name, country: l.country, taxa: l.taxa }]))
// Names the model may use for a variable, mapped to the keys of longTermTrends.json.
const ALIASES = {
  sst: "sst", analysed_sst: "sst", sea_surface_temperature: "sst", temperature: "sst",
  air_temp: "air_temp", t2m: "air_temp", air_temperature: "air_temp",
  rain: "rain", precipitation: "rain", rainfall: "rain",
  salinity: "salinity", so: "salinity",
  ph: "ph",
  nitrate: "nitrate", no3: "nitrate",
  phosphate: "phosphate", po4: "phosphate",
}
const PERIOD = { from: LONG_TERM.window.start, to: LONG_TERM.window.end }
const r3 = (x) => (x == null ? null : Math.round(x * 1000) / 1000)

export const variableKey = (v) => ALIASES[String(v ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_")] ?? null

function climate(s) {
  const c = (s.climatology || []).map((v, i) => [v, i]).filter(([v]) => v != null)
  if (c.length < 12) return null
  const hi = c.reduce((a, b) => (b[0] > a[0] ? b : a))
  const lo = c.reduce((a, b) => (b[0] < a[0] ? b : a))
  return { highest_month: MONTHS[hi[1]], highest_month_mean: r3(hi[0]), lowest_month: MONTHS[lo[1]], lowest_month_mean: r3(lo[0]) }
}

function firstLast(s, n = 5) {
  const pts = LONG_TERM.years.map((y, i) => [y, s.annual[i]]).filter(([, v]) => v != null)
  if (pts.length < 2 * n) return null
  const avg = (xs) => r3(xs.reduce((a, p) => a + p[1], 0) / xs.length)
  const head = pts.slice(0, n)
  const tail = pts.slice(-n)
  return { first_years: head.map((p) => p[0]), first_mean: avg(head), last_years: tail.map((p) => p[0]), last_mean: avg(tail) }
}

/** One variable of one region, in the shape the model reads. */
function describe(s) {
  const t = s.trend
  return {
    name: s.name,
    unit: s.unit,
    source: s.source,
    trend: t
      ? {
          verdict: !t.significant ? "no clear trend" : t.slope_per_decade > 0 ? "clear rise" : "clear fall",
          slope_per_decade: t.slope_per_decade,
          ci95_per_decade: t.ci95_per_decade,
          change_over_period: t.change_over_period,
          p_value: t.p,
          significant_at_0_05: t.significant,
          years_used: t.n_years,
          first_year: t.first_year,
          last_year: t.last_year,
        }
      : null,
    five_year_means: firstLast(s),
    seasonal_cycle: climate(s),
  }
}

/**
 * get_long_term_trend. With region_id: every variable of that region (or one, with variable).
 * Without region_id: one variable across every region, largest rise first.
 */
export function longTermTrend(input) {
  const region = input?.region_id ? String(input.region_id).trim().toUpperCase() : null
  const key = input?.variable ? variableKey(input.variable) : null
  if (input?.variable && !key) return { error: `unknown variable "${input.variable}"; use one of sst, air_temp, rain, salinity, ph, nitrate, phosphate` }
  const method = LONG_TERM.method
  if (region) {
    const reg = LONG_TERM.regions[region]
    if (!reg) return { error: `no long-term data for region "${region}"`, regions: Object.keys(LONG_TERM.regions) }
    const keys = key ? [key] : Object.keys(reg.series)
    const variables = Object.fromEntries(keys.filter((k) => reg.series[k]).map((k) => [k, describe(reg.series[k])]))
    return { region_id: region, ...NAMES[region], period: PERIOD, method, variables }
  }
  if (!key) return { error: "give region_id, or a variable to compare every region" }
  const rows = Object.entries(LONG_TERM.regions)
    .filter(([, r]) => r.series[key]?.trend)
    .map(([id, r]) => ({ region_id: id, name: NAMES[id]?.name ?? id, country: NAMES[id]?.country ?? null, ...describe(r.series[key]).trend }))
    .sort((a, b) => b.slope_per_decade - a.slope_per_decade)
  const up = rows.filter((x) => x.significant_at_0_05 && x.slope_per_decade > 0).length
  const down = rows.filter((x) => x.significant_at_0_05 && x.slope_per_decade < 0).length
  const any = Object.values(LONG_TERM.regions).find((r) => r.series[key])?.series[key]
  return {
    variable: key, name: any?.name, unit: any?.unit, source: any?.source, period: PERIOD, method,
    counts: { regions: rows.length, clear_rise: up, clear_fall: down, no_clear_trend: rows.length - up - down },
    regions: rows,
  }
}

/** get_safe_ranges: the provisional ranges per species, with their source, or those of one species / region. */
export function safeRanges(input) {
  const species = input?.species ? String(input.species).trim() : null
  const region = input?.region_id ? String(input.region_id).trim().toUpperCase() : null
  let names = Object.keys(ENVIRONMENT_RULES)
  if (species) names = names.filter((n) => n.toLowerCase() === species.toLowerCase())
  if (region) names = names.filter((n) => NAMES[region]?.taxa?.includes(n))
  const out = names.map((n) => {
    const r = ENVIRONMENT_RULES[n]
    return {
      species: n,
      habitat: r.habitat === "pond" ? "brackish pond culture; the atlas values are for the open sea nearby, so a comparison is only a rough guide" : "sea farm",
      ranges: Object.fromEntries(Object.entries(r).filter(([, v]) => v && typeof v === "object" && "min" in v)
        .map(([k, v]) => [k, { min: v.min, max: v.max, unit: k === "sst" ? "°C" : k === "salinity" ? "PSU" : null, source: v.source }])),
    }
  })
  return {
    note: "Provisional farm-site ranges used by the SEAmon dashboard to rate water conditions. They are not disease thresholds. pH, nitrate and phosphate have no validated range and are not rated.",
    ...(region ? { region_id: region, reported_species: NAMES[region]?.taxa ?? [] } : {}),
    species: out,
    ...(out.length ? {} : { error: species ? `no range for "${species}"; ranges exist for: ${Object.keys(ENVIRONMENT_RULES).join(", ")}` : "no range for the species reported in that region" }),
  }
}

/** Region ids with names, for the model to resolve a place name. */
export const REGION_LIST = Object.keys(LONG_TERM.regions).map((id) => `${id} (${NAMES[id]?.name ?? id}, ${NAMES[id]?.country ?? "?"})`).join("; ")
