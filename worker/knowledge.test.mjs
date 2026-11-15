import test from "node:test"
import assert from "node:assert/strict"
import { longTermTrend, safeRanges, variableKey } from "./knowledge.js"
import { handleAsk } from "./ask.js"

test("variable names the model may use map to the trend keys", () => {
  assert.equal(variableKey("analysed_sst"), "sst")
  assert.equal(variableKey("Sea surface temperature"), "sst")
  assert.equal(variableKey("precipitation"), "rain")
  assert.equal(variableKey("so"), "salinity")
  assert.equal(variableKey("chlorophyll"), null)
})

test("one region returns every variable with verdict, slope, CI and p", () => {
  const out = longTermTrend({ region_id: "ph-tawi" })
  assert.equal(out.name, "Tawi-Tawi")
  assert.equal(out.period.from, "2003-01-01")
  assert.equal(out.variables.sst.trend.verdict, "clear rise")
  assert.ok(out.variables.sst.trend.ci95_per_decade.length === 2)
  assert.equal(out.variables.sst.seasonal_cycle.highest_month, "May")
  assert.ok(out.variables.rain.trend.verdict === "no clear trend")
})

test("a variable alone compares every region, largest rise first", () => {
  const out = longTermTrend({ variable: "ph" })
  assert.equal(out.counts.regions, 18)
  assert.ok(out.counts.clear_fall >= 15)
  for (let i = 1; i < out.regions.length; i++) assert.ok(out.regions[i - 1].slope_per_decade >= out.regions[i].slope_per_decade)
  assert.ok(longTermTrend({ variable: "chlorophyll" }).error)
  assert.ok(longTermTrend({ region_id: "XX" }).error)
})

test("safe ranges carry their source, the pond caveat and the unrated variables", () => {
  const all = safeRanges({})
  assert.match(all.note, /not disease thresholds/)
  const ks = safeRanges({ species: "kappaphycus striatus" }).species[0]
  assert.deepEqual([ks.ranges.sst.min, ks.ranges.sst.max], [25, 30])
  assert.match(ks.ranges.sst.source, /ASEAN\/FAO/)
  assert.match(safeRanges({ species: "Gracilaria verrucosa" }).species[0].habitat, /pond/)
  assert.deepEqual(safeRanges({ region_id: "PH-TAWI" }).reported_species.length, 4)
  assert.ok(safeRanges({ species: "Caulerpa" }).error)
})

// The ask loop accepts an answer backed by the new tools.
const ENV = { OPENROUTER_API_KEY: "sk-or-k1", SUPABASE_URL: "https://x.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "s" }
test("an answer from get_long_term_trend and get_safe_ranges is accepted", async () => {
  const script = [
    [{ id: "a", name: "get_long_term_trend", input: { region_id: "PH-TAWI", variable: "sst" } }, { id: "b", name: "get_safe_ranges", input: { species: "Kappaphycus alvarezii" } }],
    [{ id: "c", name: "final_answer", input: { answer_md: "Clear rise, +0.28 °C per decade (2003-01-01 to 2024-12-31); provisional range 27–30 °C.", claims: [], data_used: [{ site_id: "PH-TAWI", variable: "sst" }, { site_id: "safe ranges", variable: "Kappaphycus alvarezii" }], confidence: "moderate", abstained: false } }],
  ]
  const fetchImpl = async (url) => {
    if (url.includes("/chat/completions")) {
      const turn = script.shift()
      const tool_calls = turn.map((u) => ({ id: u.id, type: "function", function: { name: u.name, arguments: JSON.stringify(u.input) } }))
      return new Response(JSON.stringify({ choices: [{ message: { role: "assistant", content: null, tool_calls } }] }), { status: 200 })
    }
    return new Response(JSON.stringify([{ allowed: true, used: 1 }]), { status: 200 })
  }
  const res = await handleAsk(new Request("https://s/api/ask", { method: "POST", body: JSON.stringify({ question: "Is the sea warming in Tawi-Tawi?" }) }), ENV, { fetchImpl })
  const body = await res.json()
  assert.equal(res.status, 200, JSON.stringify(body))
  assert.equal(body.abstained, false)
  assert.deepEqual(body.data_used.map((d) => d.site_id), ["PH-TAWI", "safe ranges"])
  assert.equal(body.data_used[0].from, "2003-01-01")
})
