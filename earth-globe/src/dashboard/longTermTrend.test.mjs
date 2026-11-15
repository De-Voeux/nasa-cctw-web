import test from "node:test"
import assert from "node:assert/strict"
import { longTermChart, longTermSection, verdict, seasonLine, signed } from "./longTermTrend.js"

const years = [2003, 2004, 2005, 2006]
const series = (trend) => ({
  name: "Sea surface temperature", unit: "°C", digits: 2, source: "NASA JPL MUR", product_version: null,
  annual: [28.6, null, 28.9, 29.0],
  climatology: [28, 28.2, 28.5, 29, 29.6, 29.4, 29, 28.8, 28.9, 29.1, 28.9, 28.4],
  trend,
})
const sig = { n_years: 22, first_year: 2003, last_year: 2024, p: 0.0004, significant: true, slope_per_decade: 0.3, ci95_per_decade: [0.18, 0.44] }

test("verdict separates a clear rise from no clear trend", () => {
  assert.equal(verdict(series(sig)).label, "Rising")
  assert.match(verdict(series(sig)).detail, /\+0\.30 °C per decade \(95% CI \+0\.18 to \+0\.44\), p < 0\.001/)
  assert.equal(verdict(series({ ...sig, p: 0.3, significant: false })).label, "No clear trend")
  assert.equal(verdict(series({ ...sig, slope_per_decade: -0.02 })).label, "Falling")
  assert.equal(verdict(series(null)).label, "Not enough years to test")
})

test("small slopes keep significant digits", () => {
  assert.equal(signed(0.000038, 4), "+0.000038")
  assert.equal(signed(-0.0173, 3), "-0.017")
})

test("chart breaks the line at an incomplete year and draws the trend line", () => {
  const html = longTermChart(series(sig), years)
  assert.equal((html.match(/class="t-annual"/g) || []).length, 1) // 2003 alone is not a line; 2005–2006 is
  assert.match(html, /class="t-sen sig"/)
  assert.equal((html.match(/class="t-pt"/g) || []).length, 3)
})

test("season line names the warmest and coolest months", () => {
  assert.equal(seasonLine(series(sig)), "Usually highest in May (29.60 °C) and lowest in Jan (28.00 °C).")
})

test("section is empty for a region without long-term data", () => {
  const doc = { years, regions: { "PH-TAWI": { series: { sst: series(sig) } } } }
  assert.equal(longTermSection(doc, "PH-NE-BOHOL"), "")
  assert.match(longTermSection(doc, "PH-TAWI"), /Long-term change, 2003–2006/)
})
