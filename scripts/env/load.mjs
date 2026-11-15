#!/usr/bin/env node
// Loads Eca's data-access files into env.sites and env.daily (see supabase/README.md).
//
//   node scripts/env/load.mjs [--dry-run] [--dir research/data-access] [--daily VAR,VAR]
//
// By default: sites.json, the monthly POWER table (11 variables) and the MUR sea-surface
// temperature table (one value every 30 days), about 60,000 rows. Daily POWER is opt-in
// because it is large: 19 sites x 8,036 days is about 153,000 rows PER VARIABLE.
//
// Environment (never commit these): SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (legacy
// service_role JWT). The script is safe to run again: rows are upserted.
import { readFile } from "node:fs/promises"
import { join, resolve } from "node:path"
import { parseSites, tidyRows, powerDailyRows, assertUnique, expectedCoverage } from "./parse.mjs"

const args = process.argv.slice(2)
const flag = (n) => args.includes(n)
const opt = (n) => (args.includes(n) ? args[args.indexOf(n) + 1] : undefined)
const dry = flag("--dry-run")
const dir = resolve(opt("--dir") ?? new URL("../../research/data-access", import.meta.url).pathname)
const dailyVars = opt("--daily")?.split(",").map((s) => s.trim()).filter(Boolean)

const url = process.env.SUPABASE_URL?.trim()
const key = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim()
let origin
if (!dry) {
  try {
    origin = new URL(url).origin // only the origin: a pasted ".../rest/v1/" still works
  } catch {
    console.error("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or use --dry-run).")
    process.exit(2)
  }
  if (!key) {
    console.error("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or use --dry-run).")
    process.exit(2)
  }
}

async function rpc(name, body) {
  const res = await fetch(`${origin}/rest/v1/rpc/${name}`, {
    method: "POST",
    headers: { authorization: `Bearer ${key}`, apikey: key, "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${name} -> ${res.status}: ${text.slice(0, 300)}`)
  return text ? JSON.parse(text) : null
}

const read = (p) => readFile(join(dir, p), "utf8")
const sites = parseSites(JSON.parse(await read("sites.json")))
const rows = [
  ...tidyRows(await read("data/power_monthly.csv"), "power_monthly", sites, "data/power_monthly.csv"),
  ...tidyRows(await read("data/mur_sst.csv"), "mur", sites, "data/mur_sst.csv"),
]
if (dailyVars?.length) {
  for (const s of sites) rows.push(...powerDailyRows(await read(`power/daily/${s.id}.csv`), s.id, dailyVars, `power/daily/${s.id}.csv`))
}
assertUnique(rows)

const missing = rows.filter((r) => r.value === null).length
const byProduct = {}
for (const r of rows) byProduct[r.product] = (byProduct[r.product] ?? 0) + 1
console.log(`${sites.length} sites, ${rows.length} rows (${missing} missing values kept as null)`)
for (const [p, n] of Object.entries(byProduct)) console.log(`  ${p}: ${n}`)
if (dry) process.exit(0)

await rpc("env_ingest", { p_sites: sites, p_rows: null })
const BATCH = 1000
let written = 0
for (let i = 0; i < rows.length; i += BATCH) {
  written += await rpc("env_ingest", { p_sites: null, p_rows: rows.slice(i, i + BATCH) })
  if ((i / BATCH) % 10 === 0) process.stdout.write(`\r  loaded ${written}/${rows.length}`)
}
console.log(`\r  loaded ${written}/${rows.length}`)

// Check the database against what was read: the same count of values for every site, product and variable.
const want = expectedCoverage(rows)
const have = new Map()
for (const s of await rpc("env_list_sites", { filter_country: null })) {
  for (const c of s.coverage) have.set(`${s.id}|${c.product}|${c.variable}`, c)
}
let bad = 0
for (const [k, w] of want) {
  const h = have.get(k)
  if (!h || h.n !== w.n || h.from !== w.from || h.to !== w.to) {
    bad++
    if (bad <= 5) console.error(`MISMATCH ${k}: expected ${w.n} values ${w.from}..${w.to}, database has ${h ? `${h.n} ${h.from}..${h.to}` : "nothing"}`)
  }
}
if (bad) {
  console.error(`${bad} of ${want.size} series do not match`)
  process.exit(1)
}
console.log(`verified: ${want.size} series match the files`)
