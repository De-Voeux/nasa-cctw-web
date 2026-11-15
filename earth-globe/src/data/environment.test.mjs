import test from "node:test"
import assert from "node:assert/strict"
import { assessmentFor, loadEnvironment } from "./environment.js"
import { scoreEnvironment } from "./environmentRules.js"

const payload = {
  latest_date: "2026-11-14",
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
