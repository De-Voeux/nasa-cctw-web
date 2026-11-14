// Embeds text with Supabase's built-in gte-small model (384 dimensions).
//
// POST { "input": "text" | ["text", ...] }  ->  { "embeddings": [[...384 numbers], ...] }
//
// Callable only with the service-role key: the platform checks the JWT signature
// (verify_jwt = true in config.toml) and this function additionally requires the
// `service_role` claim, so the publishable key cannot spend the model's compute.
// gte-small is mostly an English model and reads about 512 tokens, so callers send
// English queries and chunks of roughly 1,500 characters at most.

const MAX_ITEMS = 16
const MAX_CHARS = 8000

// deno-lint-ignore no-explicit-any
const session = new (globalThis as any).Supabase.ai.Session("gte-small")

function roleOf(req: Request): string | null {
  const token = (req.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "")
  const payload = token.split(".")[1]
  if (!payload) return null
  try {
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")))
    return typeof json.role === "string" ? json.role : null
  } catch {
    return null
  }
}

const reply = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })

Deno.serve(async (req) => {
  if (req.method !== "POST") return reply(405, { error: "POST only" })
  if (roleOf(req) !== "service_role") return reply(403, { error: "service role required" })

  let input: unknown
  try {
    input = (await req.json()).input
  } catch {
    return reply(400, { error: "body must be JSON" })
  }
  const items = Array.isArray(input) ? input : [input]
  if (items.length === 0 || items.length > MAX_ITEMS) return reply(400, { error: `1 to ${MAX_ITEMS} inputs` })
  if (!items.every((s) => typeof s === "string" && s.trim().length > 0 && s.length <= MAX_CHARS)) {
    return reply(400, { error: `each input must be non-empty text of at most ${MAX_CHARS} characters` })
  }

  const embeddings = []
  for (const text of items as string[]) {
    embeddings.push(Array.from(await session.run(text, { mean_pool: true, normalize: true })))
  }
  return reply(200, { embeddings })
})
