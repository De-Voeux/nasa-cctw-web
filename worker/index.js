import { handleAsk } from "./ask.js"
import { handleEnvironment } from "./environment.js"

// Only /api/* reaches this Worker (assets.run_worker_first in wrangler.jsonc); every other
// path is answered by the static assets without running any code.
export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url)
    if (pathname === "/api/ask") return handleAsk(request, env)
    if (pathname === "/api/environment") return handleEnvironment(request, env)
    if (pathname.startsWith("/api/")) return new Response(JSON.stringify({ error: "not_found" }), { status: 404, headers: { "content-type": "application/json" } })
    return env.ASSETS.fetch(request)
  },
}
