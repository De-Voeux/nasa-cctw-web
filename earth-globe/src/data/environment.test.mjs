import test from "node:test"
import assert from "node:assert/strict"
import { assessmentFor, loadEnvironment } from "./environment.js"

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

test("loadEnvironment rejects non-success responses", async () => {
  await assert.rejects(() => loadEnvironment(async () => new Response("down", { status: 503 })), /environment request failed/)
})
