/**
 * DUMMY stressor data for the region detail panel. For designing the UI only.
 *
 * Nothing here comes from NASA, Copernicus or Open-Meteo. Each region with a
 * demo stress level (see stress.js) gets a made-up daily series for
 * 7 to about 92 observed days + 3 forecast days, shaped to match its level. Replace
 * `driversFor()` with the pipeline's output when it exists; keep the shape.
 *
 * Species reference ranges have not been reviewed, so the ranges used here to
 * decide "driver / not a driver" are placeholders too.
 */

export const DUMMY_NOTE = "Sample numbers for design, not real satellite data yet."

export const PAST_DAYS = 14
export const FORECAST_DAYS = 3

const DAY_MS = 86400000

/** Variables the panel knows about, in display order. */
const VARS = {
  sst: {
    name: "Sea temperature",
    unit: "°C",
    digits: 1,
    source: "Source: NASA satellite (MUR)",
  },
  current: {
    name: "Water flow",
    unit: "m/s",
    digits: 2,
    source: "Source: Copernicus ocean model",
  },
  salinity: {
    name: "Salinity",
    unit: "PSU",
    digits: 1,
    source: "Source: Copernicus ocean model",
  },
  rain: {
    name: "Rainfall",
    unit: "mm/day",
    digits: 0,
    source: "Source: NASA satellite (GPM), Open-Meteo forecast",
  },
}

/** What isn't measured at this scale, and why. */
export const NOT_ASSESSED = [
  { name: "Nutrients", why: "No satellite data for this yet." },
  { name: "Sunlight reaching the seaweed", why: "Needs water clarity data, not connected yet." },
]

/**
 * Dummy profile per stress level, matching the demo conditions in stress.js
 * ("Normal condition", "Warm water", "Warm water, high salinity"):
 * today's value, the baseline, and whether it drives the level.
 */
const PROFILES = {
  favorable: {
    sst: { base: 29.0, now: 29.2 },
    current: { base: 0.18, now: 0.19 },
    salinity: { base: 33.6, now: 33.5 },
    rain: { base: 5, now: 4 },
  },
  moderate: {
    sst: { base: 29.3, now: 30.1, driver: true },
    current: { base: 0.16, now: 0.14 },
    salinity: { base: 34.0, now: 33.9 },
    rain: { base: 3, now: 2 },
  },
  elevated: {
    sst: { base: 29.6, now: 31.0, driver: true },
    current: { base: 0.14, now: 0.12 },
    salinity: { base: 34.2, now: 35.6, driver: true },
    rain: { base: 4, now: 1 },
  },
}

/** Baseline band half-width per variable (placeholder). */
const BAND = { sst: 0.4, current: 0.04, salinity: 0.6, rain: 6 }

// small seeded random so every region keeps the same dummy line
function rng(seed) {
  let h = 2166136261
  for (const c of seed) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507)
    h = Math.imul(h ^ (h >>> 13), 3266489909)
    return ((h ^= h >>> 16) >>> 0) / 4294967296
  }
}

function series(seed, p, key, pastDays) {
  const n = pastDays + FORECAST_DAYS
  const today = pastDays - 1
  const noise = BAND[key] * 0.25
  const phase = rng(seed + key + "phase")() * 2 * Math.PI
  const out = []
  for (let i = 0; i < n; i++) {
    const t = i - today // days from today, so a day keeps its value whatever the range
    const rand = rng(`${seed}${key}${t}`)
    // slow wobble around the baseline, then a ramp to `now` over the last 6 days; forecast eases back a little
    const ramp = Math.min(1, Math.max(0, (t + 6) / 6))
    let v = p.base + BAND[key] * 0.45 * Math.sin((2 * Math.PI * t) / 23 + phase) * (1 - ramp)
    v += (p.now - p.base) * ramp
    if (t > 0) v = p.now - (p.now - p.base) * 0.12 * t
    if (t !== 0) v += (rand() - 0.5) * 2 * noise
    out.push(Math.max(0, v))
  }
  return out
}

function headline(key, p, monthName) {
  const d = p.now - p.base
  const fmt = (x, n) => `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(n)}`
  switch (key) {
    case "sst":
      return p.driver ? `${Math.abs(d).toFixed(1)} °C warmer than a usual ${monthName}` : `Normal for ${monthName}`
    case "current":
      return p.driver ? "Water barely moving for 4 days" : "Normal"
    case "salinity":
      return p.driver ? `${d > 0 ? "Saltier" : "Less salty"} than the safe range` : "Normal"
    case "rain":
      return p.driver ? "Heavy rain for 3 days" : "Normal"
  }
}

/**
 * Dummy stressors for one region, or null when it has no sample level.
 * @param {string} locId
 * @param {"favorable"|"moderate"|"elevated"|"insufficient"} level
 * @param {number} [pastDays]  observed days, today included
 */
export function driversFor(locId, level, pastDays = PAST_DAYS) {
  if (level === "insufficient") return null
  // shift each region's numbers a little so the regions don't look identical
  const jitter = rng(locId)
  const profile = Object.fromEntries(
    Object.entries(PROFILES[level]).map(([k, p]) => {
      const d = (jitter() - 0.5) * BAND[k]
      return [k, { ...p, base: p.base + d, now: p.now + d }]
    }),
  )
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const start = new Date(now)
  start.setDate(now.getDate() - (pastDays - 1))
  const dates = Array.from({ length: pastDays + FORECAST_DAYS }, (_, i) => {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    return d
  })
  const monthName = now.toLocaleString("en", { month: "long" })

  const items = Object.entries(VARS).map(([key, v]) => {
    const p = profile[key]
    return {
      key,
      ...v,
      driver: !!p.driver,
      headline: headline(key, p, monthName),
      baseline: [p.base - BAND[key], p.base + BAND[key]],
      values: series(locId, p, key, pastDays),
    }
  })
  // drivers first, keep the rest in their usual order
  items.sort((a, b) => Number(b.driver) - Number(a.driver))
  return { dates, todayIndex: pastDays - 1, items, confidence: level === "favorable" ? "High" : "Medium" }
}
