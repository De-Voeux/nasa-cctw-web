import test from "node:test"
import assert from "node:assert/strict"
import { assessmentFor, loadEnvironment } from "./environment.js"
import { scoreEnvironment } from "./environmentRules.js"

const payload = {
  latest_date: "2026-11-14",
  as_of_date: "2026-11-15",
  regions: {
    "PH-TAWI": {
      latest_date: "2026-11-14",
      series: {
        sst: {
          key: "sst", name: "Sea surface temperature", unit: "degree_C", digits: 1,
          source: "NASA MUR SST L4", product_version: "4.1",
          dates: ["2026-11-13", "2026-11-14"], values: [29, 30], coverage: [1, 1],
        },
      },
    },
  },
}

test("assessmentFor exposes observed data without assigning a biological level", () => {
  const result = assessmentFor({ dataRegionId: "PH-TAWI" }, payload)
  assert.equal(result.level, "insufficient")
  assert.equal(result.observed, true)
  assert.equal(result.data.items[0].values[1], 30)
  assert.equal(result.data.items[0].baseline, null)
})

test("assessmentFor appends a three-day outlook without scoring it as current", () => {
  const forecastPayload = {
    ...payload,
    regions: {
      "PH-TAWI": {
        ...payload.regions["PH-TAWI"],
        series: {
          ...payload.regions["PH-TAWI"].series,
          sst: {
            ...payload.regions["PH-TAWI"].series.sst,
            forecast_dates: ["2026-11-15", "2026-11-16", "2026-11-17"],
            forecast_values: [30.1, 30.2, 30.3],
            forecast_coverage: [1, 1, 1],
            forecast_source: "Copernicus Marine",
            forecast_product_version: "forecast",
          },
        },
      },
    },
  }
  const result = assessmentFor({ dataRegionId: "PH-TAWI" }, forecastPayload, "Kappaphycus alvarezii")
  const item = result.data.items[0]
  assert.equal(result.data.todayIndex, 1)
  assert.equal(result.data.todayDate.toISOString().slice(0, 10), "2026-11-15")
  assert.deepEqual(item.values, [29, 30, 30.1, 30.2, 30.3])
  assert.equal(item.todayIndex, 1)
  assert.equal(result.data.confidence, "Observed + 3-day outlook")
  assert.equal(result.scored, false)
})

test("assessmentFor keeps missing or unmapped regions insufficient", () => {
  assert.equal(assessmentFor({}, payload).observed, false)
  assert.equal(assessmentFor({ dataRegionId: "ID-MALUKU" }, payload).condition, "No observed data available for this region")
})

test("provisional scoring uses the existing favorable/moderate/elevated levels", () => {
  const items = [
    { key: "sst", values: [28] },
    { key: "salinity", values: [33] },
  ]
  assert.equal(scoreEnvironment(items, "Kappaphycus alvarezii").level, "favorable")
  assert.equal(scoreEnvironment([{ key: "sst", values: [32] }, ...items.slice(1)], "Kappaphycus alvarezii").level, "moderate")
  assert.equal(scoreEnvironment([{ key: "sst", values: [32] }, { key: "salinity", values: [38] }], "Kappaphycus alvarezii").level, "elevated")
  assert.equal(scoreEnvironment(items, "All species").scored, false)
})

test("loadEnvironment rejects non-success responses", async () => {
  await assert.rejects(() => loadEnvironment(async () => new Response("down", { status: 503 })), /environment request failed/)
})

const twoVar = {
  ...payload,
  regions: {
    "PH-TAWI": {
      latest_date: "2026-11-14",
      series: {
        sst: { ...payload.regions["PH-TAWI"].series.sst, values: [29, 30.5] },
        salinity: { key: "salinity", name: "Salinity", unit: "PSU", digits: 1, dates: ["2026-11-13", "2026-11-14"], values: [33, 33], coverage: [1, 1] },
      },
    },
  },
}

test("All species rates a place with the rules of the seaweed reported there, keeping the worst", () => {
  const loc = { dataRegionId: "PH-TAWI", taxa: ["Eucheuma denticulatum", "Kappaphycus alvarezii", "Kappaphycus striatus"] }
  const result = assessmentFor(loc, twoVar, "All species")
  assert.equal(result.scored, true)
  assert.equal(result.level, "moderate") // SST 30.5 is above both ranges
  assert.match(result.condition, /for E\. denticulatum|for K\. alvarezii/)
  assert.ok(["Eucheuma denticulatum", "Kappaphycus alvarezii"].includes(result.ruleSpecies))
})

test("Kappaphycus striatus is rated with the ASEAN/FAO farm-site range", () => {
  const result = assessmentFor({ dataRegionId: "PH-TAWI", taxa: ["Kappaphycus striatus"] }, twoVar, "All species")
  assert.equal(result.scored, true)
  assert.equal(result.ruleSpecies, "Kappaphycus striatus")
  assert.equal(result.level, "moderate") // SST 30.5 is above 25–30
})

test("Gracilaria is rated with the pond range and says the sea values are only a rough guide", () => {
  const loc = { dataRegionId: "PH-TAWI", taxa: ["Gracilaria verrucosa", "Kappaphycus alvarezii"] }
  const picked = assessmentFor(loc, twoVar, "Gracilaria verrucosa")
  assert.equal(picked.scored, true)
  assert.equal(picked.level, "elevated") // SST 30.5 > 29 and salinity 33 > 28
  assert.match(picked.condition, /farmed in coastal ponds/)
  // With All species, the sea-farmed seaweed decides, not the pond one.
  assert.equal(assessmentFor(loc, twoVar, "All species").ruleSpecies, "Kappaphycus alvarezii")
})

test("every species named in the leads has a rule", async () => {
  const { LOCATIONS } = await import("./reportedLocations.js")
  const { ENVIRONMENT_RULES } = await import("./environmentRules.js")
  for (const t of new Set(LOCATIONS.flatMap((l) => l.taxa))) assert.ok(ENVIRONMENT_RULES[t], t)
})

test("a place whose seaweed has no rule stays unrated and says why", () => {
  const result = assessmentFor({ dataRegionId: "PH-TAWI", taxa: ["Caulerpa lentillifera"] }, twoVar, "All species")
  assert.equal(result.scored, false)
  assert.match(result.condition, /No published safe range yet for the seaweed reported here \(Caulerpa lentillifera\)/)
})
