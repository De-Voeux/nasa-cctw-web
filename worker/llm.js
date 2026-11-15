// Chat completions with fallback. Order of attempts:
//   1. Cloudflare Workers AI through the `AI` binding (no API key; billed against the account's
//      Workers AI allocation, see CF_MODELS below), model by model;
//   2. an OpenAI-compatible endpoint (OpenRouter by default), key by key and model by model.
//
// Several API keys and several models can be configured. A request tries them in order and
// moves on when one fails, because free tiers rate-limit hard and free models come and go:
//   401/402/403  that key is bad or out of credit: skip it for the rest of this request
//   400/404      this model does not accept the request (for example no tool calling): skip it
//   429/5xx/timeout/network   try the next key, then the next model
// A 429 is read twice: if its message says a daily/credit/quota limit, the KEY is spent and is
// skipped; otherwise the MODEL is busy upstream (free models are shared) and the next model is
// tried with the same key, not the next key.
// Keys that cannot be OpenRouter keys (no `sk-or-` prefix) are never sent to OpenRouter, so a
// key for another provider is not handed to a third party by mistake.
// A total attempt budget keeps a bad day from turning into a long wait.

const DEFAULT_BASE = "https://openrouter.ai/api/v1"

// Free models on OpenRouter that advertise tool calling (checked 2026-11-15 against
// https://openrouter.ai/api/v1/models). The free list changes often: override with ASK_MODELS.
// Order matters: each request starts at the top. On 2026-11-15 the Gemma model answered 429
// (busy upstream) on every live request and Nemotron answered, so Nemotron goes first and
// Gemma stays as the next fallback. Re-check from the `llm_fallback` log lines now and then.
export const DEFAULT_MODELS = [
  "nvidia/nemotron-3-ultra-550b-a55b:free",
  "google/gemma-4-31b-it:free",
  "inclusionai/ling-3.2-flash:free",
  "openrouter/free",
]

// Workers AI text models that advertise function calling, cheapest first. Checked on 2026-11-15 with
// `wrangler ai models list`: NONE of them is priced at zero. Every Workers AI model has a per-token
// price; "free" only means the account's free daily allocation (10,000 neurons a day on the Workers
// Free plan, after which requests are refused, not billed; on a Workers Paid plan the overage IS
// billed). Prices per million tokens, input / output (USD):
//   qwen3-30b-a3b-fp8 0.0509 / 0.335 · glm-4.7-flash 0.0605 / 0.40 · gemma-4-26b-a4b-it 0.10 / 0.30
// Override with ASK_CF_MODELS (comma list).
export const CF_MODELS = [
  "@cf/qwen/qwen3-30b-a3b-fp8",
  "@cf/zai-org/glm-4.7-flash",
  "@cf/google/gemma-4-26b-a4b-it",
]

const split = (s) => String(s ?? "").split(",").map((x) => x.trim()).filter(Boolean)

/** OPENROUTER_API_KEY, OPENROUTER_API_KEY_2 to _9, and OPENROUTER_API_KEYS (comma separated), de-duplicated. */
export function collectKeys(env) {
  const names = ["OPENROUTER_API_KEY", ...Array.from({ length: 8 }, (_, i) => `OPENROUTER_API_KEY_${i + 2}`)]
  return [...new Set([...names.flatMap((n) => split(env[n])), ...split(env.OPENROUTER_API_KEYS)])]
}

export const cfModelList = (env) => (split(env.ASK_CF_MODELS).length ? split(env.ASK_CF_MODELS) : CF_MODELS)

export const modelList = (env) => (split(env.ASK_MODELS).length ? split(env.ASK_MODELS) : DEFAULT_MODELS)

/** kind: "quota" when a key hit its daily or credit limit, otherwise "down". */
export class LlmError extends Error {
  constructor(message, kind = "down") {
    super(message)
    this.kind = kind
  }
}

const isOpenRouter = (base) => /(^|\/\/)([^/]*\.)?openrouter\.ai(\/|$)/.test(base)
const keyLimit = /per[- ]?day|daily|credit|quota|insufficient|balance/i

/** Keys that may be sent to this endpoint. For OpenRouter only `sk-or-` keys qualify. */
export function usableKeys(env, base) {
  const all = collectKeys(env)
  return isOpenRouter(base) ? all.filter((k) => k.startsWith("sk-or-")) : all
}

/** The provider's own error message, short, for the log. Never contains our key. */
function errorText(text) {
  try {
    const e = JSON.parse(text)?.error
    return String(e?.message ?? e ?? text).slice(0, 160)
  } catch {
    return String(text).slice(0, 160)
  }
}

// Workers AI answers either in the OpenAI chat-completion shape (choices[0].message) or, for some older
// models, as { response, tool_calls: [{ name, arguments }] }. Both become an OpenAI-style message.
export function normalizeCf(out) {
  const m = out?.choices?.[0]?.message
  if (m) return { role: "assistant", content: m.content ?? null, tool_calls: m.tool_calls?.length ? m.tool_calls : undefined }
  if (out && (Array.isArray(out.tool_calls) || typeof out.response === "string")) {
    const calls = (out.tool_calls ?? []).map((tc, i) => ({
      id: tc.id ?? `call_${i}`,
      type: "function",
      function: { name: tc.name ?? tc.function?.name, arguments: typeof tc.arguments === "string" ? tc.arguments : JSON.stringify(tc.arguments ?? tc.function?.arguments ?? {}) },
    }))
    return { role: "assistant", content: out.response ?? null, tool_calls: calls.length ? calls : undefined }
  }
  return null
}

const cfQuota = /daily free allocation|4006|neurons|quota|limit exceeded|upgrade/i

const parseArgs = (s) => {
  if (s && typeof s === "object") return s
  try {
    return JSON.parse(s || "{}")
  } catch {
    return null
  }
}

export function createLlm(env, fetchImpl = fetch, { timeoutMs = 25000, maxAttempts = 10 } = {}) {
  const base = (env.LLM_BASE_URL || DEFAULT_BASE).replace(/\/$/, "")
  const keys = usableKeys(env, base)
  const skipped = collectKeys(env).length - keys.length
  if (skipped > 0) console.log(JSON.stringify({ event: "llm_keys_skipped", count: skipped, reason: "not an OpenRouter key (no sk-or- prefix)" }))
  const models = modelList(env)
  const cfModels = env.AI && typeof env.AI.run === "function" ? cfModelList(env) : []
  let cfSpent = false // the Workers AI allocation is used up: skip every Workers AI model for the rest of the request
  const deadKeys = new Set()
  const deadModels = new Set()
  let attempts = 0
  let quotaHit = false

  async function onceCf(model, payload) {
    let timer
    try {
      const out = await Promise.race([
        env.AI.run(model, payload),
        new Promise((_, reject) => (timer = setTimeout(() => reject(new Error("timeout")), timeoutMs))),
      ])
      const message = normalizeCf(out)
      return message ? { message } : { error: "unexpected response shape" }
    } catch (e) {
      return { error: String(e?.message ?? e).slice(0, 700) }
    } finally {
      clearTimeout(timer)
    }
  }

  async function once(model, key, payload) {
    const ctl = new AbortController()
    const timer = setTimeout(() => ctl.abort(), timeoutMs)
    try {
      const res = await fetchImpl(`${base}/chat/completions`, {
        method: "POST",
        signal: ctl.signal,
        headers: {
          authorization: `Bearer ${key}`,
          "content-type": "application/json",
          "http-referer": env.SITE_URL || "https://seamon.seagis.app",
          "x-title": "SEAmon",
        },
        body: JSON.stringify({ model, ...payload }),
      })
      const text = await res.text()
      if (!res.ok) return { status: res.status, detail: errorText(text) }
      const data = JSON.parse(text)
      const message = data?.choices?.[0]?.message
      if (data?.error || !message) return { status: data?.error?.code ?? 502, detail: errorText(text) } // a 200 with an error body
      return { message }
    } catch {
      return { status: 0 } // timeout or network
    } finally {
      clearTimeout(timer)
    }
  }

  /**
   * @param {{system:string, tools:object[], messages:object[]}} p  tools in OpenAI "function" format
   * @returns {Promise<{message:object, toolCalls:{id:string,name:string,input:object|null}[], model:string}>}
   */
  async function chat({ messages, tools }) {
    for (const model of cfModels) {
      if (cfSpent || deadModels.has(model)) continue
      if (++attempts > maxAttempts) throw new LlmError("attempt budget used up", quotaHit ? "quota" : "down")
      // Workers AI rejects `content: null` (which the API gives an assistant turn that only calls tools): send "".
      const clean = messages.map((m) => (m.content == null ? { ...m, content: "" } : m))
      const r = await onceCf(model, { messages: clean, tools, max_tokens: 1200, temperature: 0.2 })
      if (r.message) {
        const toolCalls = (r.message.tool_calls ?? []).map((tc) => ({ id: tc.id, name: tc.function?.name, input: parseArgs(tc.function?.arguments) }))
        return { message: r.message, toolCalls, model, provider: "workers-ai" }
      }
      console.log(JSON.stringify({ event: "llm_fallback", provider: "workers-ai", model, detail: r.error }))
      if (cfQuota.test(r.error ?? "")) {
        cfSpent = true
        quotaHit = true
      } else deadModels.add(model)
    }
    for (const model of models) {
      if (deadModels.has(model)) continue
      for (const key of keys) {
        if (deadKeys.has(key)) continue
        if (++attempts > maxAttempts) throw new LlmError("attempt budget used up", quotaHit ? "quota" : "down")
        const r = await once(model, key, { messages, tools, tool_choice: "auto", max_tokens: 1200, temperature: 0.2 })
        if (r.message) {
          const toolCalls = (r.message.tool_calls ?? []).map((tc) => ({ id: tc.id, name: tc.function?.name, input: parseArgs(tc.function?.arguments) }))
          return { message: r.message, toolCalls, model, provider: "openrouter" }
        }
        console.log(JSON.stringify({ event: "llm_fallback", provider: "openrouter", model, status: r.status, detail: r.detail }))
        if (r.status === 402 || (r.status === 429 && keyLimit.test(r.detail ?? ""))) quotaHit = true
        if ([401, 402, 403].includes(r.status)) deadKeys.add(key)
        else if (r.status === 429 && keyLimit.test(r.detail ?? "")) deadKeys.add(key)
        else if ([400, 404, 429].includes(r.status)) {
          deadModels.add(model)
          break
        }
      }
    }
    throw new LlmError("no model answered", quotaHit ? "quota" : "down")
  }

  return { chat, configured: cfModels.length > 0 || (keys.length > 0 && models.length > 0) }
}
