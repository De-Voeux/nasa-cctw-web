// GET /api/environment: compact observed environmental series for the dashboard.
// The Worker keeps the Supabase service-role key server-side. The browser receives
// only public science measurements and provenance, never credentials.

const PAGE_SIZE = 1000
const MAX_PAGES = 10
const DAYS = 14

const json = (status, body, cache = "no-store") =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": cache },
  })

function supabaseOrigin(value) {
  const u = new URL(String(value || "").trim())
  if (u.protocol !== "https:") throw new Error("Supabase URL must use HTTPS")
  return u.origin
}

async function readJson(res) {
  if (!res.ok) throw new Error(`database request failed (${res.status})`)
  return res.json()
}

function dayBefore(date, days) {
  const d = new Date(`${date}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - days)
  return d.toISOString().slice(0, 10)
}

async function getRows(base, headers, path, fetchImpl) {
  const rows = []
  for (let page = 0; page < MAX_PAGES; page++) {
    const from = page * PAGE_SIZE
    const res = await fetchImpl(`${base}/rest/v1/${path}`, {
      headers: { ...headers, range: `${from}-${from + PAGE_SIZE - 1}` },
    })
    const part = await readJson(res)
    rows.push(...part)
    if (part.length < PAGE_SIZE) return rows
  }
  throw new Error("database response exceeded the dashboard limit")
}

const VARIABLES = {
  analysed_sst: { key: "sst", name: "Sea surface temperature", digits: 1 },
  so: { key: "salinity", name: "Salinity", digits: 1 },
  no3: { key: "nitrate", name: "Nitrate", digits: 3 },
  po4: { key: "phosphate", name: "Phosphate", digits: 3 },
  ph: { key: "ph", name: "pH", digits: 2 },
}

function sourceLabel(row) {
  if (row.dataset === "mur_sst") return "NASA MUR SST L4 · daily area-weighted zone mean"
  return "Copernicus Marine · daily area-weighted zone mean · surface layer"
}

export function aggregate(rows, latestDate) {
  const grouped = new Map()
  for (const row of rows) {
    const meta = VARIABLES[row.variable]
    if (!meta || row.mean == null) continue
    const key = `${row.region_id}\u0000${row.variable}\u0000${row.date}`
    const weight = Number(row.valid_pixel_count) || 1
    const current = grouped.get(key) || { ...row, weighted: 0, weight: 0, coverWeighted: 0 }
    current.weighted += Number(row.mean) * weight
    current.coverWeighted += (Number(row.coverage_fraction) || 0) * weight
    current.weight += weight
    grouped.set(key, current)
  }

  const regions = {}
  for (const row of grouped.values()) {
    const meta = VARIABLES[row.variable]
    const region = (regions[row.region_id] ||= { latest_date: latestDate, series: {} })
    const item = (region.series[meta.key] ||= {
      key: meta.key,
      name: meta.name,
      unit: row.units,
      digits: meta.digits,
      source: sourceLabel(row),
      product_version: row.product_version,
      dates: [],
      values: [],
      coverage: [],
    })
    item.dates.push(row.date)
    item.values.push(row.weighted / row.weight)
    item.coverage.push(row.coverWeighted / row.weight)
  }

  for (const region of Object.values(regions)) {
    for (const item of Object.values(region.series)) {
      const order = item.dates.map((date, i) => ({ date, value: item.values[i], coverage: item.coverage[i] }))
        .sort((a, b) => a.date.localeCompare(b.date))
      item.dates = order.map((x) => x.date)
      item.values = order.map((x) => x.value)
      item.coverage = order.map((x) => x.coverage)
    }
  }
  return regions
}

export async function handleEnvironment(request, env, { fetchImpl = fetch } = {}) {
  if (request.method !== "GET") return json(405, { error: "method_not_allowed" })
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) return json(503, { error: "environment_unavailable" })

  let base
  try {
    base = supabaseOrigin(env.SUPABASE_URL)
  } catch {
    return json(503, { error: "environment_unavailable" })
  }
  const headers = {
    authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    apikey: env.SUPABASE_SERVICE_ROLE_KEY,
  }

  try {
    const latest = await readJson(await fetchImpl(
      `${base}/rest/v1/seagis_daily_metrics?select=date&order=date.desc&limit=1`,
      { headers },
    ))
    const latestDate = latest[0]?.date ?? null
    if (!latestDate) return json(200, { latest_date: null, days: DAYS, regions: {} }, "public, max-age=300")

    const from = dayBefore(latestDate, DAYS - 1)
    const select = "region_id,subregion_id,dataset,variable,date,units,mean,valid_pixel_count,coverage_fraction,product_version"
    const variables = "analysed_sst,so,no3,po4,ph"
    const path = `seagis_daily_metrics?select=${select}&date=gte.${from}&date=lte.${latestDate}&variable=in.(${variables})&order=region_id.asc,variable.asc,date.asc`
    const rows = await getRows(base, headers, path, fetchImpl)
    return json(200, { latest_date: latestDate, days: DAYS, regions: aggregate(rows, latestDate) }, "public, max-age=900")
  } catch (error) {
    console.error(JSON.stringify({ event: "environment", error: String(error.message).slice(0, 160) }))
    return json(502, { error: "environment_unavailable" })
  }
}
