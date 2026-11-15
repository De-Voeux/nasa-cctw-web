import test from "node:test"
import assert from "node:assert/strict"
import { trendChart } from "./trendChart.js"

test("Today marker follows calendar dates when observations skip a day", () => {
  const dates = ["2026-11-13", "2026-11-16", "2026-11-17"].map((d) => new Date(`${d}T00:00:00Z`))
  const html = trendChart(
    { name: "Sea surface temperature", unit: "°C", digits: 1, values: [29, 30, 30.2] },
    dates,
    0,
    1,
    new Date("2026-11-15T00:00:00Z"),
  )
  assert.match(html, /class="t-fc"/)
  assert.match(html, /class="t-today" x1="50" x2="50"/)
  assert.match(html, /style="left:75%/) // selected 16 Nov uses its real date position
})
