// Chat completions with fallback, for any OpenAI-compatible endpoint (OpenRouter by default).
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

const split = (s) => String(s ?? "").split(",").map((x) => x.trim()).filter(Boolean)

/** OPENROUTER_API_KEY, OPENROUTER_API_KEY_2 to _9, and OPENROUTER_API_KEYS (comma separated), de-duplicated. */
export function collectKeys(env) {
  const names = ["OPENROUTER_API_KEY", ...Array.from({ length: 8 }, (_, i) => `OPENROUTER_API_KEY_${i + 2}`)]
  return [...new Set([...names.flatMap((n) => split(env[n])), ...split(env.OPENROUTER_API_KEYS)])]
}

export const modelList = (env) => (split(env.ASK_MODELS).length ? split(env.ASK_MODELS) : DEFAULT_MODELS)

export class LlmError extends Error {}

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

const parseArgs = (s) => {
  if (s && typeof s === "object") return s
  try {
    return JSON.parse(s || "{}")
  } catch {
    return null
  }
}

export function createLlm(env, fetchImpl = fetch, { timeoutMs = 25000, maxAttempts = 8 } = {}) {
  const base = (env.LLM_BASE_URL || DEFAULT_BASE).replace(/\/$/, "")
  const keys = usableKeys(env, base)
  const skipped = collectKeys(env).length - keys.length
  if (skipped > 0) console.log(JSON.stringify({ event: "llm_keys_skipped", count: skipped, reason: "not an OpenRouter key (no sk-or- prefix)" }))
  const models = modelList(env)
  const deadKeys = new Set()
  const deadModels = new Set()
  let attempts = 0

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
    for (const model of models) {
      if (deadModels.has(model)) continue
      for (const key of keys) {
        if (deadKeys.has(key)) continue
        if (++attempts > maxAttempts) throw new LlmError("attempt budget used up")
        const r = await once(model, key, { messages, tools, tool_choice: "auto", max_tokens: 1200, temperature: 0.2 })
        if (r.message) {
          const toolCalls = (r.message.tool_calls ?? []).map((tc) => ({ id: tc.id, name: tc.function?.name, input: parseArgs(tc.function?.arguments) }))
          return { message: r.message, toolCalls, model }
        }
        console.log(JSON.stringify({ event: "llm_fallback", model, status: r.status, detail: r.detail }))
        if ([401, 402, 403].includes(r.status)) deadKeys.add(key)
        else if (r.status === 429 && keyLimit.test(r.detail ?? "")) deadKeys.add(key)
        else if ([400, 404, 429].includes(r.status)) {
          deadModels.add(model)
          break
        }
      }
    }
    throw new LlmError("no model answered")
  }

  return { chat, configured: keys.length > 0 && models.length > 0 }
}
