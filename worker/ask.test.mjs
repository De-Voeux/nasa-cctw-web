import test from "node:test"
import assert from "node:assert/strict"
import { handleAsk, validateAnswer, summarize, ABSTAIN } from "./ask.js"

// All sources and numbers below are test fixtures, not scientific data.
const ENV = { ANTHROPIC_API_KEY: "k", SUPABASE_URL: "https://x.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "s" }
const CHUNK = { chunk_id: 7, source_id: "t:one", citation: "Fixture (2026).", doi: null, url: null, section: "S", page: 3, content: "fixture text", similarity: 0.9, keyword_hit: false }
const ask = (q, env = ENV, init = {}) =>
  new Request("https://site/api/ask", { method: "POST", body: JSON.stringify({ question: q }), headers: { "content-type": "application/json" }, ...init })

const use = (name, input, id = name + Math.random()) => ({ type: "tool_use", id, name, input })

/** A fake network: `script` is the list of model turns; rpc maps function names to handlers. */
function net(script, rpc = {}) {
  const calls = { model: [], rpc: [], embed: 0 }
  const fetchImpl = async (url, init) => {
    const body = init?.body ? JSON.parse(init.body) : {}
    if (url.includes("api.anthropic.com")) {
      calls.model.push(body)
      const turn = script.shift()
      assert.ok(turn, "model called more times than scripted")
      return new Response(JSON.stringify({ content: turn }), { status: 200 })
    }
    if (url.endsWith("/functions/v1/embed")) {
      calls.embed++
      return new Response(JSON.stringify({ embeddings: [[0.1, 0.2]] }), { status: 200 })
    }
    const name = url.split("/rpc/")[1]
    calls.rpc.push([name, body])
    const out = rpc[name]?.(body)
    if (out instanceof Error) return new Response(out.message, { status: 400 })
    return new Response(JSON.stringify(out ?? []), { status: 200 })
  }
  return { fetchImpl, calls }
}
const run = async (q, script, rpc, env = ENV) => {
  const n = net(script, rpc)
  const res = await handleAsk(ask(q), env, { fetchImpl: n.fetchImpl })
  return { res, body: await res.json(), ...n }
}

test("rejects the wrong method, bad JSON and bad questions", async () => {
  assert.equal((await handleAsk(new Request("https://s/api/ask"), ENV)).status, 405)
  assert.equal((await handleAsk(new Request("https://s/api/ask", { method: "POST", body: "{" }), ENV)).status, 400)
  assert.equal((await handleAsk(ask("hi"), ENV)).status, 400)
  assert.equal((await handleAsk(ask("x".repeat(501)), ENV)).status, 400)
})

test("is unavailable (503) until its secrets are set, so the page can fall back", async () => {
  assert.equal((await handleAsk(ask("a real question"), {})).status, 503)
  assert.equal((await handleAsk(ask("a real question"), { ...ENV, ANTHROPIC_API_KEY: "" })).status, 503)
})

test("rate limit answers 429 before any model call", async () => {
  const n = net([])
  const env = { ...ENV, ASK_LIMITER: { limit: async () => ({ success: false }) } }
  const res = await handleAsk(ask("a real question"), env, { fetchImpl: n.fetchImpl })
  assert.equal(res.status, 429)
  assert.equal(n.calls.model.length, 0)
})

test("literature question: searches in English, answers with a resolved citation", async () => {
  const { res, body, calls } = await run(
    "Apa kata studi?",
    [
      [use("search_evidence", { query_en: "ice-ice study", species: "Kappaphycus alvarezii" })],
      [use("final_answer", { answer_md: "A fixture claim.", claims: [{ text: "Fixture says X.", chunk_ids: [7] }], data_used: [], confidence: "low", abstained: false })],
    ],
    { rag_search: () => [CHUNK] },
  )
  assert.equal(res.status, 200)
  assert.equal(body.abstained, false)
  assert.deepEqual(body.sources, [{ n: 1, id: "t:one", citation: "Fixture (2026).", doi: null, url: null }])
  assert.deepEqual(body.claims, [{ text: "Fixture says X.", source_ns: [1] }])
  assert.equal(calls.embed, 1)
  assert.equal(calls.rpc[0][1].filter_species, "Kappaphycus alvarezii")
  assert.equal(calls.rpc[0][1].query_text, "ice-ice study")
  // the model is told to use tools every turn, and the tool result carries the chunk text as data
  assert.equal(calls.model[0].tool_choice.type, "any")
})

test("a citation the tools never returned is rejected, then the model may fix it", async () => {
  const { body, calls } = await run(
    "question here",
    [
      [use("search_evidence", { query_en: "q" })],
      [use("final_answer", { answer_md: "x", claims: [{ text: "t", chunk_ids: [999] }], data_used: [], confidence: "high", abstained: false })],
      [use("final_answer", { answer_md: "ok", claims: [{ text: "t", chunk_ids: [7] }], data_used: [], confidence: "low", abstained: false })],
    ],
    { rag_search: () => [CHUNK] },
  )
  assert.equal(body.abstained, false)
  assert.equal(calls.model.length, 3)
  const feedback = JSON.stringify(calls.model[2].messages.at(-1))
  assert.match(feedback, /chunk_id 999 was not retrieved/)
})

test("two bad answers in a row become an abstention, not an invented answer", async () => {
  const bad = () => use("final_answer", { answer_md: "x", claims: [{ text: "t", chunk_ids: [999] }], data_used: [], confidence: "high", abstained: false })
  const { body } = await run("question here", [[use("search_evidence", { query_en: "q" })], [bad()], [bad()]], { rag_search: () => [CHUNK] })
  assert.equal(body.abstained, true)
  assert.deepEqual(body.claims, [])
})

test("nothing retrieved and nothing measured forces an abstention, whatever the model says", async () => {
  const { body } = await run(
    "question here",
    [[use("search_evidence", { query_en: "q" })], [use("final_answer", { answer_md: "Made-up answer.", claims: [{ text: "t", chunk_ids: [] }], data_used: [], confidence: "high", abstained: false })]],
    { rag_search: () => [] },
  )
  assert.equal(body.abstained, true)
  assert.equal(body.confidence, "none")
  assert.notEqual(body.answer_md, "Made-up answer.")
})

test("weak semantic matches without a keyword hit are dropped", async () => {
  const weak = { ...CHUNK, similarity: 0.5, keyword_hit: false }
  const { calls, body } = await run(
    "question here",
    [[use("search_evidence", { query_en: "q" })], [use("final_answer", { answer_md: "x", claims: [{ text: "t", chunk_ids: [7] }], data_used: [], confidence: "low", abstained: false })], [use("final_answer", { answer_md: "none", claims: [], data_used: [], confidence: "none", abstained: true })]],
    { rag_search: () => [weak] },
  )
  const toolResult = JSON.stringify(calls.model[1].messages.at(-1))
  assert.match(toolResult, /No sufficiently relevant verified source/)
  assert.equal(body.abstained, true)
})

test("measurements: the model gets a computed summary and may cite only what was fetched", async () => {
  const rows = [
    { day: "2026-11-01", value: 29, unit: "degree_C", product: "MUR", product_version: "v4.1" },
    { day: "2026-11-02", value: null, unit: "degree_C", product: "MUR", product_version: "v4.1" },
    { day: "2026-11-03", value: 31, unit: "degree_C", product: "MUR", product_version: "v4.1" },
  ]
  const { body, calls } = await run(
    "How warm was Maluku?",
    [
      [use("get_series", { site_id: "maluku", variable: "analysed_sst", from: "2026-11-01", to: "2026-11-03" })],
      [use("final_answer", { answer_md: "Mean 30.", claims: [], data_used: [{ site_id: "maluku", variable: "analysed_sst" }], confidence: "moderate", abstained: false })],
    ],
    { env_get_series: () => rows },
  )
  const summary = JSON.parse(JSON.parse(JSON.stringify(calls.model[1].messages.at(-1).content[0].content))).summary
  assert.equal(summary.mean, 30)
  assert.equal(summary.n_missing, 1)
  assert.deepEqual(summary.latest, { day: "2026-11-03", value: 31 })
  assert.equal(body.data_used[0].site_id, "maluku")
  assert.deepEqual(body.data_used[0].products, ["MUR v4.1"])
})

test("data_used for a series that was never fetched is rejected", () => {
  const ctx = { chunks: new Map([[7, CHUNK]]), series: [] }
  const r = validateAnswer({ answer_md: "x", claims: [{ text: "t", chunk_ids: [7] }], data_used: [{ site_id: "maluku", variable: "sst" }], confidence: "low", abstained: false }, ctx)
  assert.equal(r.ok, false)
  assert.match(r.problem, /was not fetched/)
})

test("the tool call budget stops a looping model", async () => {
  const many = Array.from({ length: 6 }, () => [use("list_sites", {})])
  const { body, calls } = await run("question here", many, { env_list_sites: () => [] })
  assert.ok(calls.rpc.length <= 4)
  assert.equal(body.abstained, true)
})

test("a failing tool does not crash the request or leak its error text", async () => {
  const { res, body, calls } = await run(
    "question here",
    [[use("list_sites", {})], [use("final_answer", { answer_md: "none", claims: [], data_used: [], confidence: "none", abstained: true })]],
    { env_list_sites: () => new Error("secret db detail") },
  )
  assert.equal(res.status, 200)
  assert.equal(body.abstained, true)
  assert.ok(!JSON.stringify(calls.model[1].messages).includes("secret db detail"))
})

test("summarize handles an empty series", () => {
  assert.deepEqual(summarize([], "a", "b"), { n_days_with_value: 0, n_rows: 0, from: "a", to: "b" })
  assert.ok(ABSTAIN.abstained)
})
