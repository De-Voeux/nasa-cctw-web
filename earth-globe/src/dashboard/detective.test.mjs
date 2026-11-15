import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import { conclusion, compareRows, compareHtml, QUESTIONS, EXAMPLES } from "./detective.js"

const doc = JSON.parse(fs.readFileSync(new URL("../data/longTermTrends.json", import.meta.url), "utf8"))
const s = (trend) => ({ name: "Sea surface temperature", unit: "°C", digits: 2, trend })

test("conclusion says yes only for a significant trend", () => {
  const sig = { first_year: 2003, last_year: 2024, p: 0.0004, significant: true, slope_per_decade: 0.28, change_over_period: 0.588 }
  assert.match(conclusion(s(sig), "Tawi-Tawi"), /^Yes, a clear trend in Tawi-Tawi: sea surface temperature has risen by about 0\.59 °C from 2003 to 2024/)
  assert.match(conclusion(s({ ...sig, p: 0.4, significant: false }), "Tawi-Tawi"), /^No clear trend in Tawi-Tawi/)
  assert.match(conclusion(s(null), "X"), /not enough complete years/)
})

test("comparison lists every place, largest rise first, and counts directions", () => {
  const rows = compareRows(doc, "sst", {})
  assert.ok(rows.length >= 18)
  for (let i = 1; i < rows.length; i++) assert.ok(rows[i - 1].s.trend.slope_per_decade >= rows[i].s.trend.slope_per_decade)
  assert.match(compareHtml(rows, "PH-TAWI"), /\d+ of \d+ places show a clear rise/)
  assert.match(compareHtml(rows, "PH-TAWI"), /class="is-current"/)
})

test("every question and example has data", () => {
  for (const q of QUESTIONS) assert.ok(Object.values(doc.regions).some((r) => r.series[q.key]), q.key)
  for (const e of EXAMPLES) assert.ok(doc.regions[e.region]?.series[e.key]?.trend, e.label)
})
