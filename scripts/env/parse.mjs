// Reading Eca's data-access files into rows for env.sites and env.daily. Pure functions, no
// network and no dependencies; load.mjs does the I/O. Nothing here fills, interpolates or
// converts a value: a missing value stays missing (null), and units are kept as the source
// states them.

export const PRODUCTS = {
  // Names carry the time resolution, because the assistant reads them (see migration 3).
  power_monthly: { product: "POWER-monthly", version: "NASA POWER API, community AG, source native resolution, pulled 2026-11-15" },
  power_daily: { product: "POWER-daily", version: "NASA POWER API, community AG, source native resolution, pulled 2026-11-15" },
  mur: { product: "MUR-30d", version: "jplMURSST41 via NOAA ERDDAP, one value every 30 days, pulled 2026-11-15" },
}

const DATE = /^\d{4}-\d{2}-\d{2}$/
const SITE_ID = /^[a-z0-9][a-z0-9-]*$/

/** Minimal CSV: quoted fields, doubled quotes, CRLF. Returns objects keyed by the header row. */
export function parseCsv(text, file = "csv") {
  const rows = []
  let row = [], field = "", quoted = false
  const s = text.replace(/^﻿/, "")
  for (let i = 0; i < s.length; i++) {
    const c = s[i]
    if (quoted) {
      if (c === '"' && s[i + 1] === '"') (field += '"'), i++
      else if (c === '"') quoted = false
      else field += c
    } else if (c === '"') quoted = true
    else if (c === ",") (row.push(field), (field = ""))
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && s[i + 1] === "\n") i++
      row.push(field), (field = "")
      if (row.some((x) => x !== "")) rows.push(row)
      row = []
    } else field += c
  }
  if (field !== "" || row.length) (row.push(field), row.some((x) => x !== "") && rows.push(row))
  if (quoted) throw new Error(`${file}: unterminated quote`)
  const [head, ...body] = rows
  if (!head) throw new Error(`${file}: empty`)
  return body.map((r, i) => {
    if (r.length !== head.length) throw new Error(`${file}: line ${i + 2} has ${r.length} fields, header has ${head.length}`)
    return Object.fromEntries(head.map((h, j) => [h.trim(), r[j]]))
  })
}

/** sites.json -> rows for env.sites. */
export function parseSites(json, file = "sites.json") {
  if (!Array.isArray(json) || json.length === 0) throw new Error(`${file}: expected a non-empty array`)
  const seen = new Set()
  return json.map((s) => {
    for (const k of ["id", "name", "country"]) if (typeof s[k] !== "string" || !s[k].trim()) throw new Error(`${file}: a site is missing "${k}"`)
    if (!SITE_ID.test(s.id)) throw new Error(`${file}: bad site id "${s.id}"`)
    if (seen.has(s.id)) throw new Error(`${file}: duplicate site id "${s.id}"`)
    seen.add(s.id)
    if (!Number.isFinite(s.lat) || s.lat < -90 || s.lat > 90) throw new Error(`${file}: ${s.id} has a bad lat`)
    if (!Number.isFinite(s.lon) || s.lon < -180 || s.lon > 180) throw new Error(`${file}: ${s.id} has a bad lon`)
    return { id: s.id, name: s.name, country: s.country, lat: s.lat, lon: s.lon }
  })
}

/** "" and the POWER sentinel -999 mean missing; anything else must be a finite number. */
export function toValue(raw, where) {
  const t = String(raw ?? "").trim()
  if (t === "" || /^-999(\.0+)?$/.test(t)) return null
  const v = Number(t)
  if (!Number.isFinite(v)) throw new Error(`${where}: "${raw}" is not a number`)
  return v
}

/**
 * Eca's tidy tables (data/power_monthly.csv, data/mur_sst.csv):
 * site_id, country, lat, lon, variable, unit, [year, month,] date, value.
 * Checks the site exists in sites.json and that its coordinates agree with it.
 */
export function tidyRows(text, productKey, sites, file) {
  const { product, version } = PRODUCTS[productKey]
  const byId = new Map(sites.map((s) => [s.id, s]))
  return parseCsv(text, file).map((r, i) => {
    const where = `${file}: row ${i + 2}`
    const site = byId.get(r.site_id)
    if (!site) throw new Error(`${where}: unknown site "${r.site_id}"`)
    if (Math.abs(Number(r.lat) - site.lat) > 1e-6 || Math.abs(Number(r.lon) - site.lon) > 1e-6) {
      throw new Error(`${where}: coordinates differ from sites.json for ${r.site_id}`)
    }
    if (!DATE.test(r.date) || Number.isNaN(Date.parse(r.date))) throw new Error(`${where}: bad date "${r.date}"`)
    if (!r.variable || !r.unit) throw new Error(`${where}: variable and unit are required`)
    return { site_id: r.site_id, day: r.date, variable: r.variable, value: toValue(r.value, where), unit: r.unit, product, product_version: version }
  })
}

/**
 * A raw POWER daily file: a header block with the parameter list ("NAME   description (unit)"),
 * then YEAR,DOY and one column per parameter. Only `variables` are kept (all when omitted).
 */
export function powerDailyRows(text, siteId, variables, file) {
  const m = /-BEGIN HEADER-\r?\n([\s\S]*?)-END HEADER-\r?\n([\s\S]*)$/.exec(text)
  if (!m) throw new Error(`${file}: no POWER header block`)
  const units = {}
  for (const line of m[1].split(/\r?\n/)) {
    const u = /^([A-Z0-9_]+)\s+.*\(([^()]*)\)\s*$/.exec(line)
    if (u) units[u[1]] = u[2].trim()
  }
  const { product, version } = PRODUCTS.power_daily
  const out = []
  for (const r of parseCsv(m[2], file)) {
    const year = Number(r.YEAR), doy = Number(r.DOY)
    if (!Number.isInteger(year) || !Number.isInteger(doy) || doy < 1 || doy > 366) throw new Error(`${file}: bad YEAR/DOY "${r.YEAR}/${r.DOY}"`)
    const day = new Date(Date.UTC(year, 0, doy)).toISOString().slice(0, 10)
    if (!day.startsWith(String(year))) throw new Error(`${file}: DOY ${doy} is outside ${year}`)
    for (const [variable, raw] of Object.entries(r)) {
      if (variable === "YEAR" || variable === "DOY") continue
      if (variables && !variables.includes(variable)) continue
      if (!units[variable]) throw new Error(`${file}: no unit for ${variable} in the header`)
      out.push({ site_id: siteId, day, variable, value: toValue(raw, `${file}: ${day} ${variable}`), unit: units[variable], product, product_version: version })
    }
  }
  return out
}

/** A (site, day, variable, product) must be unique, or an upsert would silently overwrite one of them. */
export function assertUnique(rows) {
  const seen = new Set()
  for (const r of rows) {
    const k = `${r.site_id}|${r.day}|${r.variable}|${r.product}`
    if (seen.has(k)) throw new Error(`duplicate row ${k}`)
    seen.add(k)
  }
}

/** Counts of non-missing values per site, product and variable; what the database must report after a load. */
export function expectedCoverage(rows) {
  const m = new Map()
  for (const r of rows) {
    const k = `${r.site_id}|${r.product}|${r.variable}`
    const c = m.get(k) ?? { n: 0, from: r.day, to: r.day }
    if (r.value !== null) c.n++
    if (r.day < c.from) c.from = r.day
    if (r.day > c.to) c.to = r.day
    m.set(k, c)
  }
  return m
}
