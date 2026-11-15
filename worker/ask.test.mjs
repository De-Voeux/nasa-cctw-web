import test from "node:test"
import assert from "node:assert/strict"
import { handleAsk, validateAnswer, summarize, ABSTAIN } from "./ask.js"

// All sources and numbers below are test fixtures, not scientific data.
const ENV = { OPENROUTER_API_KEY: "sk-or-k1", SUPABASE_URL: "https://x.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "s" }
const CHUNK = { chunk_id: 7, source_id: "t:one", citation: "Fixture (2026).", doi: null, url: null, section: "S", page: 3, content: "fixture text", similarity: 0.9, keyword_hit: false }
const ask = (q, env = ENV, init = {}) =>
  new Request("https://site/api/ask", { method: "POST", body: JSON.stringify({ question: q }), headers: { "content-type": "application/json" }, ...init })

const use = (name, input, id = name + Math.random()) => ({ id, name, input })

/** A fake network: `script` is the list of model turns (tool calls each); rpc maps function names to handlers.
 *  A turn may also be { status: 429 } to simulate a failing provider call. */
function net(script, rpc = {}) {
  const calls = { model: [], rpc: [], embed: 0, usage: [], order: [] } // usage: the daily-count RPC, kept apart so tests can count the others
  const fetchImpl = async (url, init) => {
    const body = init?.body ? JSON.parse(init.body) : {}
    if (url.includes("/chat/completions")) {
      calls.order.push("model")
      calls.model.push({ ...body, key: init.headers.authorization })
      const turn = script.shift()
      assert.ok(turn, "model called more times than scripted")
      if (turn.status) return new Response(turn.body ?? JSON.stringify({ error: { message: "fail" } }), { status: turn.status })
      const tool_calls = turn.map((u) => ({ id: u.id, type: "function", function: { name: u.name, arguments: JSON.stringify(u.input) } }))
      return new Response(JSON.stringify({ choices: [{ message: { role: "assistant", content: null, tool_calls: tool_calls.length ? tool_calls : undefined } }] }), { status: 200 })
    }
    if (url.endsWith("/functions/v1/embed")) {
      calls.embed++
      return new Response(JSON.stringify({ embeddings: [[0.1, 0.2]] }), { status: 200 })
    }
    const name = url.split("/rpc/")[1]
    if (name === "rag_usage_hit") (calls.usage.push(body), calls.order.push("usage"))
    else calls.rpc.push([name, body])
    const out = name === "rag_usage_hit" && !rpc.rag_usage_hit ? [{ allowed: true, used: 1 }] : rpc[name]?.(body)
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
  assert.equal((await handleAsk(ask("   "), ENV)).status, 400)
  assert.equal((await handleAsk(ask("x".repeat(501)), ENV)).status, 400)
})

test("is unavailable (503) until its secrets are set, so the page can fall back", async () => {
  assert.equal((await handleAsk(ask("a real question"), {})).status, 503)
  assert.equal((await handleAsk(ask("a real question"), { ...ENV, OPENROUTER_API_KEY: "" })).status, 503)
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
  // OpenAI-style request: system prompt first, tools as functions
  assert.equal(calls.model[0].messages[0].role, "system")
  assert.equal(calls.model[0].tools[0].type, "function")
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
  const summary = JSON.parse(calls.model[1].messages.at(-1).content).summary
  assert.equal(summary.mean, 30)
  assert.equal(summary.n_missing, 1)
  assert.deepEqual(summary.latest, { day: "2026-11-03", value: 31 })
  assert.equal(body.data_used[0].site_id, "maluku")
  assert.deepEqual(body.data_used[0].products, ["MUR"])
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

// ------------------------------------------------------------------ keys, models and fallback
import { collectKeys, modelList, DEFAULT_MODELS } from "./llm.js"

const FINAL_ABSTAIN = [use("final_answer", { answer_md: "none", claims: [], data_used: [], confidence: "none", abstained: true })]

test("keys are collected from every field and de-duplicated", () => {
  const keys = collectKeys({ OPENROUTER_API_KEY: "a", OPENROUTER_API_KEY_2: "b", OPENROUTER_API_KEY_3: " ", OPENROUTER_API_KEYS: "c, a ,d" })
  assert.deepEqual(keys, ["a", "b", "c", "d"])
  assert.deepEqual(collectKeys({}), [])
  assert.deepEqual(modelList({ ASK_MODELS: "m1, m2" }), ["m1", "m2"])
  assert.deepEqual(modelList({}), DEFAULT_MODELS)
})

test("a key that hit its daily limit falls through to the next key", async () => {
  const env = { ...ENV, OPENROUTER_API_KEY_2: "sk-or-k2" }
  const { body, calls } = await run("question here", [{ status: 429, body: JSON.stringify({ error: { message: "Rate limit exceeded: free-models-per-day" } }) }, FINAL_ABSTAIN], {}, env)
  assert.equal(body.abstained, true)
  assert.deepEqual(calls.model.map((m) => m.key), ["Bearer sk-or-k1", "Bearer sk-or-k2"])
  assert.equal(calls.model[0].model, calls.model[1].model) // same model, second key
})

test("a model that rejects the request is skipped, and the next model is tried", async () => {
  const env = { ...ENV, ASK_MODELS: "m1,m2" }
  const { body, calls } = await run("question here", [{ status: 400 }, FINAL_ABSTAIN], {}, env)
  assert.equal(body.abstained, true)
  assert.deepEqual(calls.model.map((m) => m.model), ["m1", "m2"])
})

test("a key refused with 401 is not used again in the same request", async () => {
  const env = { ...ENV, OPENROUTER_API_KEY_2: "sk-or-k2", ASK_MODELS: "m1,m2" }
  const { calls } = await run("question here", [{ status: 401 }, { status: 429 }, FINAL_ABSTAIN], {}, env)
  // k1 dies on m1; k2 gets an upstream 429 on m1 (the model is busy, not the key); m2 uses k2 (k1 skipped)
  assert.deepEqual(calls.model.map((m) => `${m.model}/${m.key}`), ["m1/Bearer sk-or-k1", "m1/Bearer sk-or-k2", "m2/Bearer sk-or-k2"])
})

test("when every model and key fails the request ends in 502, without leaking details", async () => {
  const env = { ...ENV, ASK_MODELS: "m1" }
  const n = net([{ status: 500 }])
  const res = await handleAsk(ask("question here"), env, { fetchImpl: n.fetchImpl })
  assert.equal(res.status, 503)
  assert.deepEqual(await res.json(), { error: "assistant_unavailable", reason: "down" })
})

test("the attempt budget stops a long chain of failures", async () => {
  const env = { ...ENV, OPENROUTER_API_KEYS: "sk-or-a,sk-or-b,sk-or-c,sk-or-d", ASK_MODELS: "m1,m2,m3" }
  const n = net(Array.from({ length: 20 }, () => ({ status: 429 })))
  const res = await handleAsk(ask("question here"), env, { fetchImpl: n.fetchImpl })
  assert.equal(res.status, 503)
  assert.ok(n.calls.model.length <= 8)
})

test("plain text with no tool call is never shown: one nudge, then an abstention", async () => {
  const { body, calls } = await run("question here", [[], []], {})
  assert.equal(body.abstained, true)
  assert.equal(calls.model.length, 2)
  assert.match(JSON.stringify(calls.model[1].messages.at(-1)), /Use the tools/)
})

test("tool arguments that are not valid JSON are reported to the model, not executed", async () => {
  const n = net([FINAL_ABSTAIN])
  const raw = n.fetchImpl
  let first = true
  const fetchImpl = async (url, init) => {
    if (url.includes("/chat/completions") && first) {
      first = false
      return new Response(JSON.stringify({ choices: [{ message: { role: "assistant", content: null, tool_calls: [{ id: "t1", type: "function", function: { name: "get_series", arguments: "{oops" } }] } }] }), { status: 200 })
    }
    return raw(url, init)
  }
  const res = await handleAsk(ask("question here"), ENV, { fetchImpl })
  assert.equal(res.status, 200)
  assert.equal(n.calls.rpc.length, 0)
  assert.match(JSON.stringify(n.calls.model[0].messages.at(-1)), /not valid JSON/)
})

test("SUPABASE_URL pasted with a path still reaches the right endpoints; a bad one is unavailable", async () => {
  const urls = []
  const n = net([[use("list_sites", {})], FINAL_ABSTAIN])
  const fetchImpl = async (url, init) => (urls.push(url), n.fetchImpl(url, init))
  const env = { ...ENV, SUPABASE_URL: " https://abc.supabase.co/rest/v1/ " }
  assert.equal((await handleAsk(ask("question here"), env, { fetchImpl })).status, 200)
  assert.ok(urls.includes("https://abc.supabase.co/rest/v1/rpc/env_list_sites"), urls.join("\n"))
  assert.equal((await handleAsk(ask("question here"), { ...ENV, SUPABASE_URL: "not a url" })).status, 503)
  assert.equal((await handleAsk(ask("question here"), { ...ENV, SUPABASE_URL: "http://abc.supabase.co" })).status, 503)
})

import { usableKeys } from "./llm.js"

test("an upstream 429 moves to the next model with the SAME key, not to the next key", async () => {
  const env = { ...ENV, OPENROUTER_API_KEY_2: "sk-or-k2", ASK_MODELS: "m1,m2" }
  const { body, calls } = await run("question here", [{ status: 429, body: JSON.stringify({ error: { message: "model is temporarily rate-limited upstream" } }) }, FINAL_ABSTAIN], {}, env)
  assert.equal(body.abstained, true)
  assert.deepEqual(calls.model.map((m) => `${m.model}/${m.key}`), ["m1/Bearer sk-or-k1", "m2/Bearer sk-or-k1"])
})

test("keys that are not OpenRouter keys are never sent to OpenRouter", async () => {
  const env = { OPENROUTER_API_KEY: "gsk_not_openrouter", OPENROUTER_API_KEY_2: "sk-or-ok", SUPABASE_URL: "https://x.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "s" }
  assert.deepEqual(usableKeys(env, "https://openrouter.ai/api/v1"), ["sk-or-ok"])
  assert.deepEqual(usableKeys(env, "https://example.org/v1"), ["gsk_not_openrouter", "sk-or-ok"]) // another endpoint: no filter
  const { calls } = await run("question here", [FINAL_ABSTAIN], {}, env)
  assert.deepEqual(calls.model.map((m) => m.key), ["Bearer sk-or-ok"])
  // and with only foreign keys the assistant is simply unavailable
  assert.equal((await handleAsk(ask("question here"), { ...env, OPENROUTER_API_KEY_2: "" })).status, 503)
})

test("an empty search tells the model to stop searching and answer, and the log names the model", async () => {
  const logs = []
  const orig = console.log
  console.log = (m) => logs.push(m)
  try {
    const { body, calls } = await run("question here", [[use("search_evidence", { query_en: "q" })], FINAL_ABSTAIN], { rag_search: () => [] })
    assert.equal(body.abstained, true)
    assert.equal(calls.model.length, 2) // one search, one final answer: no retry loop
    assert.match(JSON.stringify(calls.model[1].messages.at(-1)), /Do NOT search again/)
  } finally {
    console.log = orig
  }
  assert.ok(logs.some((l) => /"event":"ask".*"model":"/.test(l)), logs.join("\n"))
})

// ------------------------------------------------------------------ site coverage and product resolution
import { compactSites, SYSTEM_PROMPT } from "./ask.js"

const COVERAGE = [
  { variable: "analysed_sst", product: "MUR-30d", unit: "degree_C", from: "2003-01-01", to: "2024-12-08", n: 268 },
  { variable: "PRECTOTCORR", product: "POWER-monthly", unit: "mm/day", from: "2003-01-01", to: "2024-12-01", n: 264 },
  { variable: "T2M", product: "POWER-monthly", unit: "C", from: "2003-01-01", to: "2024-12-01", n: 264 },
]

test("compactSites folds the coverage into one entry per product and lists the units once", () => {
  const out = compactSites([{ id: "maluku", name: "Maluku", country: "Indonesia", lat: -5.6, lon: 132.7, coverage: COVERAGE }, { id: "empty", name: "E", country: "X", lat: 0, lon: 0, coverage: [] }])
  assert.deepEqual(out.sites[0].data, [
    { product: "MUR-30d", from: "2003-01-01", to: "2024-12-08", variables: ["analysed_sst"] },
    { product: "POWER-monthly", from: "2003-01-01", to: "2024-12-01", variables: ["PRECTOTCORR", "T2M"] },
  ])
  assert.deepEqual(out.sites[1].data, [])
  assert.deepEqual(out.units, { analysed_sst: "degree_C", PRECTOTCORR: "mm/day", T2M: "C" })
})

test("list_sites gives the model the compact coverage, including where the data ends", async () => {
  const { calls } = await run(
    "question here",
    [[use("list_sites", {})], FINAL_ABSTAIN],
    { env_list_sites: () => [{ id: "maluku", name: "Maluku", country: "Indonesia", lat: -5.6, lon: 132.7, coverage: COVERAGE }] },
  )
  const toolText = calls.model[1].messages.at(-1).content
  assert.match(toolText, /"to":"2024-12-08"/)
  assert.match(toolText, /"units"/)
  assert.ok(!toolText.includes('"n":268'))
})

test("get_series passes the product through and reports it", async () => {
  const rows = [{ day: "2024-10-09", value: 28, unit: "degree_C", product: "MUR-30d", product_version: "v" }]
  const { body, calls } = await run(
    "question here",
    [[use("get_series", { site_id: "maluku", variable: "analysed_sst", from: "2024-10-01", to: "2024-12-31", product: "MUR-30d" })],
     [use("final_answer", { answer_md: "ok", claims: [], data_used: [{ site_id: "maluku", variable: "analysed_sst" }], confidence: "moderate", abstained: false })]],
    { env_get_series: () => rows },
  )
  assert.equal(calls.rpc[0][1].p_product, "MUR-30d")
  assert.deepEqual(body.data_used[0].products, ["MUR-30d"])
})

test("a variable that exists at two resolutions makes the model choose, instead of mixing them", async () => {
  const rows = [
    { day: "2024-01-01", value: 1, unit: "mm/day", product: "POWER-monthly", product_version: "v" },
    { day: "2024-01-01", value: 9, unit: "mm/day", product: "POWER-daily", product_version: "v" },
  ]
  const { calls } = await run(
    "question here",
    [[use("get_series", { site_id: "maluku", variable: "PRECTOTCORR", from: "2024-01-01", to: "2024-01-31" })], FINAL_ABSTAIN],
    { env_get_series: () => rows },
  )
  const toolText = calls.model[1].messages.at(-1).content
  assert.match(toolText, /more than one product \(POWER-monthly, POWER-daily\)/)
  assert.ok(!toolText.includes("summary"))
})

test("the prompt says the data is historical and that resolutions differ", () => {
  assert.match(SYSTEM_PROMPT, /HISTORICAL/)
  assert.match(SYSTEM_PROMPT, /MUR-30d is one sea-surface temperature value every 30 days/)
})

import { smalltalkReply } from "./smalltalk.js"

test("greetings, thanks and help get a fixed reply with no model call and no secrets", async () => {
  for (const q of ["hai", "Hai!", "halo", "hi", "Hello!!", "selamat pagi", "terima kasih", "makasih ya", "thanks", "what can you do?", "kamu siapa?"]) {
    const n = net([])
    const res = await handleAsk(ask(q), {}, { fetchImpl: n.fetchImpl }) // {} = no secrets: still answers
    const body = await res.json()
    assert.equal(res.status, 200, q)
    assert.equal(body.abstained, false, q)
    assert.equal(body.kind, "conversation", q)
    assert.deepEqual([body.claims, body.sources, body.data_used], [[], [], []], q)
    assert.equal(n.calls.model.length + n.calls.rpc.length, 0, q)
  }
})

test("the reply follows the language of the greeting", () => {
  assert.match(smalltalkReply("hai"), /^Hai!/)
  assert.match(smalltalkReply("hello"), /^Hi!/)
  assert.match(smalltalkReply("terima kasih"), /Sama-sama/)
  assert.match(smalltalkReply("thank you"), /welcome/)
})

test("a greeting followed by a real question, or any real question, still goes to the model", async () => {
  assert.equal(smalltalkReply("hai, which area has the most ice-ice case?"), null)
  assert.equal(smalltalkReply("Which area has the most ice-ice case?"), null)
  assert.equal(smalltalkReply("thanks for nothing, what is the temperature at Maluku"), null)
  assert.equal(smalltalkReply("x".repeat(200)), null)
  assert.equal(smalltalkReply(""), null)
  const { body, calls } = await run("hai, which area has the most ice-ice case?", [FINAL_ABSTAIN], {})
  assert.equal(calls.model.length, 1)
  assert.equal(body.kind, undefined)
})

test("when every key has hit its daily limit the answer is a 503 with reason quota, so the page can fall back", async () => {
  const body429 = JSON.stringify({ error: { message: "Rate limit exceeded: free-models-per-day. Add 10 credits" } })
  const env = { ...ENV, OPENROUTER_API_KEY_2: "sk-or-k2" }
  const n = net([{ status: 429, body: body429 }, { status: 429, body: body429 }])
  const res = await handleAsk(ask("question here"), env, { fetchImpl: n.fetchImpl })
  assert.equal(res.status, 503)
  assert.deepEqual(await res.json(), { error: "assistant_unavailable", reason: "quota" })
  assert.equal(n.calls.model.length, 2) // each key tried once, no point retrying a spent key
})

test("not configured stays a plain 503 without a reason", async () => {
  assert.deepEqual(await (await handleAsk(ask("a real question"), {})).json(), { error: "assistant_unavailable" })
})

// ------------------------------------------------------------------ Cloudflare Workers AI
import { cfModelList, CF_MODELS, normalizeCf } from "./llm.js"

/** A fake `env.AI`: `script` entries are objects returned, or Error instances thrown, one per call. */
function fakeAi(script) {
  const calls = []
  return {
    calls,
    run: async (model, input) => {
      calls.push({ model, input })
      const next = script.shift()
      assert.ok(next !== undefined, "Workers AI called more times than scripted")
      if (next instanceof Error) throw next
      return next
    },
  }
}
const cfTurn = (toolCalls) => ({ choices: [{ message: { role: "assistant", content: null, tool_calls: toolCalls.map((u) => ({ id: u.id, type: "function", function: { name: u.name, arguments: JSON.stringify(u.input) } })) } }] })
const CF_ENV = { SUPABASE_URL: "https://x.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "s" } // no OpenRouter keys at all

test("with only the AI binding configured (no keys) the assistant answers through Workers AI", async () => {
  const ai = fakeAi([cfTurn(FINAL_ABSTAIN)])
  const n = net([])
  const res = await handleAsk(ask("question here"), { ...CF_ENV, AI: ai }, { fetchImpl: n.fetchImpl })
  assert.equal(res.status, 200)
  assert.equal((await res.json()).abstained, true)
  assert.equal(ai.calls.length, 1)
  assert.equal(ai.calls[0].model, CF_MODELS[0]) // the cheapest first
  assert.equal(n.calls.model.length, 0) // OpenRouter untouched
  assert.equal(ai.calls[0].input.messages[0].role, "system")
  assert.equal(ai.calls[0].input.tools[0].type, "function")
})

test("both Workers AI response shapes become the same message", () => {
  const a = normalizeCf(cfTurn([{ id: "t1", name: "list_sites", input: { country: "X" } }]))
  assert.equal(a.tool_calls[0].function.name, "list_sites")
  const b = normalizeCf({ response: null, tool_calls: [{ name: "list_sites", arguments: { country: "X" } }] })
  assert.equal(b.tool_calls[0].function.name, "list_sites")
  assert.equal(b.tool_calls[0].function.arguments, JSON.stringify({ country: "X" }))
  assert.equal(b.tool_calls[0].id, "call_0")
  assert.equal(normalizeCf({ response: "plain text" }).content, "plain text")
  assert.equal(normalizeCf({}), null)
  assert.equal(normalizeCf(null), null)
})

test("a Workers AI model that errors is skipped for the request and the next one is tried", async () => {
  const ai = fakeAi([new Error("5006: model unavailable"), cfTurn(FINAL_ABSTAIN)])
  const res = await handleAsk(ask("question here"), { ...CF_ENV, AI: ai }, { fetchImpl: net([]).fetchImpl })
  assert.equal(res.status, 200)
  assert.deepEqual(ai.calls.map((c) => c.model), [CF_MODELS[0], CF_MODELS[1]])
})

test("when the daily Workers AI allocation is used up, every Workers AI model is skipped and OpenRouter takes over", async () => {
  const ai = fakeAi([new Error("AiError: 4006: you have used up your daily free allocation of 10,000 neurons")])
  const n = net([FINAL_ABSTAIN])
  const res = await handleAsk(ask("question here"), { ...CF_ENV, AI: ai, OPENROUTER_API_KEY: "sk-or-k1" }, { fetchImpl: n.fetchImpl })
  assert.equal(res.status, 200)
  assert.equal(ai.calls.length, 1) // one try, then none of the other Workers AI models
  assert.equal(n.calls.model.length, 1)
})

test("allocation used up and nothing else configured: 503 with reason quota, so the page falls back", async () => {
  const ai = fakeAi([new Error("4006: you have used up your daily free allocation of 10,000 neurons")])
  const res = await handleAsk(ask("question here"), { ...CF_ENV, AI: ai }, { fetchImpl: net([]).fetchImpl })
  assert.equal(res.status, 503)
  assert.deepEqual(await res.json(), { error: "assistant_unavailable", reason: "quota" })
})

test("a hung Workers AI call times out and moves on", async () => {
  const hung = { calls: [], run: async (model) => (hung.calls.push(model), hung.calls.length === 1 ? new Promise(() => {}) : cfTurn(FINAL_ABSTAIN)) }
  const { createLlm } = await import("./llm.js")
  const llm = createLlm({ AI: hung }, fetch, { timeoutMs: 30 })
  const out = await llm.chat({ messages: [{ role: "user", content: "x" }], tools: [] })
  assert.equal(out.provider, "workers-ai")
  assert.equal(hung.calls.length, 2)
})

test("ASK_CF_MODELS overrides the Workers AI model list", () => {
  assert.deepEqual(cfModelList({ ASK_CF_MODELS: "@cf/a/b, @cf/c/d" }), ["@cf/a/b", "@cf/c/d"])
  assert.deepEqual(cfModelList({}), CF_MODELS)
  assert.ok(CF_MODELS.every((m) => m.startsWith("@cf/")))
})

test("Workers AI is never sent `content: null` (it rejects it); other providers get the message as it was", async () => {
  const ai = fakeAi([cfTurn([{ id: "t1", name: "list_sites", input: {} }]), cfTurn(FINAL_ABSTAIN)])
  const n = net([], { env_list_sites: () => [] })
  await handleAsk(ask("question here"), { ...CF_ENV, AI: ai }, { fetchImpl: n.fetchImpl })
  assert.equal(ai.calls.length, 2)
  const second = ai.calls[1].input.messages
  assert.ok(second.every((m) => typeof m.content === "string"), JSON.stringify(second.map((m) => [m.role, m.content])))
  assert.equal(second.find((m) => m.role === "assistant").tool_calls[0].function.name, "list_sites") // tool calls kept
})

test("summaries carry the real dates of the minimum and the maximum", () => {
  const rows = [
    { day: "2024-01-01", value: 28, unit: "C", product: "M", product_version: "v1" },
    { day: "2024-02-01", value: 25, unit: "C", product: "M", product_version: "v1" },
    { day: "2024-03-01", value: 31, unit: "C", product: "M", product_version: "v1" },
  ]
  const s = summarize(rows, "2024-01-01", "2024-03-01")
  assert.deepEqual([s.min, s.min_day, s.max, s.max_day], [25, "2024-02-01", 31, "2024-03-01"])
})

test("a date the tools never returned is rejected, then the model may fix it", async () => {
  const rows = [
    { day: "2024-01-13", value: 28, unit: "degree_C", product: "MUR", product_version: "v4.1" },
    { day: "2024-08-10", value: 26, unit: "degree_C", product: "MUR", product_version: "v4.1" },
  ]
  const series = use("get_series", { site_id: "maluku", variable: "analysed_sst", from: "2024-01-01", to: "2024-12-31" })
  const answer = (text) => use("final_answer", { answer_md: text, claims: [], data_used: [{ site_id: "maluku", variable: "analysed_sst" }], confidence: "moderate", abstained: false })
  const { body, calls } = await run("temperature at Maluku?", [[series], [answer("The lowest was 26 on 2024-05-05.")], [answer("The lowest was 26 on 2024-08-10.")]], { env_get_series: () => rows })
  assert.equal(body.abstained, false)
  assert.match(body.answer_md, /2024-08-10/)
  assert.match(JSON.stringify(calls.model[2].messages.at(-1)), /date 2024-05-05 does not appear/)
})

test("dates inside the question window the model asked about are fine when the tool returned them", async () => {
  const rows = [{ day: "2024-01-13", value: 28, unit: "degree_C", product: "MUR", product_version: "v4.1" }]
  const series = use("get_series", { site_id: "maluku", variable: "analysed_sst", from: "2024-01-01", to: "2024-12-31" })
  const final = use("final_answer", { answer_md: "From 2024-01-01 to 2024-12-31 the only value was 28 on 2024-01-13.", claims: [], data_used: [{ site_id: "maluku", variable: "analysed_sst" }], confidence: "low", abstained: false })
  const { body } = await run("q here", [[series], [final]], { env_get_series: () => rows })
  assert.equal(body.abstained, false)
})

test("list_sites: an empty answer for a country filter tells the model to look at all sites", async () => {
  const { calls } = await run("temperature at Maluku", [[use("list_sites", { country: "Maluku" })], FINAL_ABSTAIN], { env_list_sites: (b) => (b.filter_country ? [] : [{ id: "maluku", name: "Maluku" }]) })
  assert.match(JSON.stringify(calls.model[1].messages.at(-1)), /Call list_sites again with no arguments/)
  assert.match(calls.model[0].tools.find((t) => t.function.name === "list_sites").function.description, /COUNTRY name/)
})

// ------------------------------------------------------------------ daily limit
import { dailyLimit, DEFAULT_DAILY_LIMIT } from "./ask.js"

test("ASK_DAILY_LIMIT: default 100, a number, or off", () => {
  assert.equal(dailyLimit({}), DEFAULT_DAILY_LIMIT)
  assert.equal(DEFAULT_DAILY_LIMIT, 100)
  assert.equal(dailyLimit({ ASK_DAILY_LIMIT: "25" }), 25)
  assert.equal(dailyLimit({ ASK_DAILY_LIMIT: " 7.9 " }), 7)
  assert.equal(dailyLimit({ ASK_DAILY_LIMIT: "0" }), 0)
  assert.equal(dailyLimit({ ASK_DAILY_LIMIT: "OFF" }), 0)
  assert.equal(dailyLimit({ ASK_DAILY_LIMIT: "banana" }), DEFAULT_DAILY_LIMIT) // a typo must not switch the cap off
  assert.equal(dailyLimit({ ASK_DAILY_LIMIT: "-5" }), DEFAULT_DAILY_LIMIT)
})

test("a question takes one place from the daily count before any model call", async () => {
  const { calls, res } = await run("question here", [FINAL_ABSTAIN], { rag_usage_hit: () => [{ allowed: true, used: 7 }] })
  assert.equal(res.status, 200)
  assert.deepEqual(calls.usage, [{ p_scope: "ask", p_limit: 100 }])
  assert.equal(calls.order[0], "usage") // taken before the first model call
})

test("when the daily cap is reached: 503 quota, no model is called", async () => {
  const { res, body, calls } = await run("question here", [], { rag_usage_hit: () => [{ allowed: false, used: 100 }] }, { ...ENV, ASK_DAILY_LIMIT: "100" })
  assert.equal(res.status, 503)
  assert.deepEqual(body, { error: "assistant_unavailable", reason: "quota" })
  assert.equal(calls.model.length, 0)
})

test("if the count cannot be read the assistant is unavailable (fails closed, so a fault cannot lift the cap)", async () => {
  const { res, body, calls } = await run("question here", [], { rag_usage_hit: () => new Error("db down") })
  assert.equal(res.status, 503)
  assert.deepEqual(body, { error: "assistant_unavailable", reason: "down" })
  assert.equal(calls.model.length, 0)
})

test("greetings are not counted, and ASK_DAILY_LIMIT=off skips the count", async () => {
  const n = net([])
  const res = await handleAsk(ask("hai"), ENV, { fetchImpl: n.fetchImpl })
  assert.equal(res.status, 200)
  assert.equal(n.calls.rpc.length + n.calls.usage.length, 0)
  const m = net([FINAL_ABSTAIN])
  const res2 = await handleAsk(ask("question here"), { ...ENV, ASK_DAILY_LIMIT: "off" }, { fetchImpl: m.fetchImpl })
  assert.equal(res2.status, 200)
  assert.equal(m.calls.usage.length, 0)
})

test("a greeting followed by a help or thanks phrase is still a fixed reply", () => {
  assert.match(smalltalkReply("hi, what can you do?"), /^I'm the SEAmon assistant\./)
  assert.match(smalltalkReply("Hello! What can I ask you?"), /SEAmon assistant/)
  assert.match(smalltalkReply("halo, kamu bisa apa?"), /^Saya asisten SEAmon\./)
  assert.match(smalltalkReply("hai bisa apa saja"), /^Saya asisten SEAmon\./)
  assert.match(smalltalkReply("hi thanks"), /welcome/)
  assert.match(smalltalkReply("selamat pagi, terima kasih"), /Sama-sama/)
  assert.match(smalltalkReply("hai apa kabar"), /^Hai!/)
  assert.match(smalltalkReply("how can you help me"), /SEAmon assistant/)
})

test("a real question is never mistaken for small talk, with or without a greeting", () => {
  for (const q of [
    "hi, which area has the most ice-ice case?",
    "what can you do about ice-ice in Maluku",
    "can you help me find the temperature at Maluku",
    "halo, suhu laut di Maluku berapa?",
    "hello what is ice-ice",
    "thanks for nothing what is the temperature at Maluku",
  ]) assert.equal(smalltalkReply(q), null, q)
})
