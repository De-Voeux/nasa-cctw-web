import test from "node:test"
import assert from "node:assert/strict"
import { aggregate, handleEnvironment } from "./environment.js"

const ENV = { SUPABASE_URL: "https://example.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "secret" }

test("aggregate combines subregions with valid-pixel weights", () => {
  const regions = aggregate([
    { region_id: "ID-SOUTH-SUL", dataset: "mur_sst", variable: "analysed_sst", date: "2026-11-14", units: "degree_C", mean: 28, valid_pixel_count: 1, coverage_fraction: 0.5, product_version: "4.1" },
    { region_id: "ID-SOUTH-SUL", dataset: "mur_sst", variable: "analysed_sst", date: "2026-11-14", units: "degree_C", mean: 30, valid_pixel_count: 3, coverage_fraction: 1, product_version: "4.1" },
  ], "2026-11-14")
  assert.equal(regions["ID-SOUTH-SUL"].series.sst.values[0], 29.5)
  assert.equal(regions["ID-SOUTH-SUL"].series.sst.coverage[0], 0.875)
  assert.match(regions["ID-SOUTH-SUL"].series.sst.source, /NASA MUR/)
})

test("aggregate keeps three-day forecast separate from observed values", () => {
  const regions = aggregate([
    { region_id: "PH-TAWI", dataset: "cmems_phy_so", variable: "so", data_type: "observed", date: "2026-11-14", units: "PSU", mean: 34, valid_pixel_count: 1, coverage_fraction: 1, product_version: "analysis" },
    { region_id: "PH-TAWI", dataset: "cmems_phy_so", variable: "so", data_type: "forecast", date: "2026-11-15", units: "PSU", mean: 34.2, valid_pixel_count: 1, coverage_fraction: 1, product_version: "forecast" },
    { region_id: "PH-TAWI", dataset: "cmems_phy_so", variable: "so", data_type: "forecast", date: "2026-11-16", units: "PSU", mean: 34.4, valid_pixel_count: 1, coverage_fraction: 1, product_version: "forecast" },
  ], "2026-11-14")
  const item = regions["PH-TAWI"].series.salinity
  assert.deepEqual(item.dates, ["2026-11-14"])
  assert.deepEqual(item.values, [34])
  assert.deepEqual(item.forecast_dates, ["2026-11-15", "2026-11-16"])
  assert.deepEqual(item.forecast_values, [34.2, 34.4])
  assert.match(item.forecast_source, /Copernicus/)
})

test("endpoint pages measurements and never exposes the service key", async () => {
  const calls = []
  const fetchImpl = async (url, init) => {
    calls.push({ url, init })
    if (url.includes("limit=1")) return new Response(JSON.stringify([{ date: "2026-11-14" }]), { status: 200 })
    return new Response(JSON.stringify([
      { region_id: "PH-TAWI", dataset: "cmems_phy_so", variable: "so", date: "2026-11-14", units: "PSU", mean: 34, valid_pixel_count: 2, coverage_fraction: 1, product_version: "2026" },
    ]), { status: 200 })
  }
  const res = await handleEnvironment(new Request("https://site/api/environment"), ENV, { fetchImpl })
  const body = await res.json()
  assert.equal(res.status, 200)
  assert.equal(body.regions["PH-TAWI"].series.salinity.values[0], 34)
  assert.ok(calls.some((c) => c.url.includes("variable=in.(analysed_sst,thetao,so,no3,po4,ph)")))
  assert.ok(calls.every((c) => c.init.headers.authorization === "Bearer secret"))
  assert.ok(!JSON.stringify(body).includes("secret"))
})

test("endpoint rejects writes and degrades safely when unconfigured", async () => {
  assert.equal((await handleEnvironment(new Request("https://site/api/environment", { method: "POST" }), ENV)).status, 405)
  assert.equal((await handleEnvironment(new Request("https://site/api/environment"), {})).status, 503)
})
