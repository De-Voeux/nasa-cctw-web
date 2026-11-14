#!/usr/bin/env node
// Loads source files from research/corpus/ into the RAG tables.
//
//   node scripts/rag/ingest.mjs [--dry-run] [path ...]
//
// Environment (never commit these):
//   SUPABASE_URL                 https://<project-ref>.supabase.co
//   SUPABASE_SERVICE_ROLE_KEY    the legacy service_role JWT (the embed function checks its role claim)
//
// A source may be loaded before it is reviewed: it is stored but is not searchable until
// its front matter has verified_by and verified_on. Run the script again after review;
// the text is only embedded again if it changed.
import { readdir, readFile } from "node:fs/promises"
import { join, resolve } from "node:path"
import { parseSource, chunkBody, hashBody } from "./corpus.mjs"

const args = process.argv.slice(2)
const dry = args.includes("--dry-run")
const targets = args.filter((a) => !a.startsWith("--"))
const dir = resolve(new URL("../../research/corpus", import.meta.url).pathname)

const url = process.env.SUPABASE_URL?.replace(/\/$/, "")
const key = process.env.SUPABASE_SERVICE_ROLE_KEY
if (!dry && (!url || !key)) {
  console.error("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or use --dry-run).")
  process.exit(2)
}

async function call(path, body) {
  const res = await fetch(`${url}${path}`, {
    method: "POST",
    headers: { authorization: `Bearer ${key}`, apikey: key, "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${path} -> ${res.status}: ${text.slice(0, 300)}`)
  return text ? JSON.parse(text) : null
}

async function embed(texts) {
  const out = []
  for (let i = 0; i < texts.length; i += 8) {
    const { embeddings } = await call("/functions/v1/embed", { input: texts.slice(i, i + 8) })
    out.push(...embeddings)
  }
  return out
}

const files = targets.length
  ? targets
  : (await readdir(dir)).filter((f) => f.endsWith(".md") && f.toLowerCase() !== "readme.md").map((f) => join(dir, f))

let failed = 0
for (const file of files) {
  try {
    const { meta, body } = parseSource(await readFile(file, "utf8"), file)
    const chunks = chunkBody(body)
    const sha = hashBody(body)
    const verified = Boolean(meta.verified_by)
    const label = `${meta.id}: ${chunks.length} chunks, ${verified ? "verified" : "NOT verified (stored, not searchable)"}`
    if (dry) {
      console.log(`[dry-run] ${label}`)
      continue
    }
    const source = { ...meta, content_sha256: sha }
    const same = (await call("/rest/v1/rpc/rag_source_hash", { p_id: meta.id })) === sha
    if (same) {
      await call("/rest/v1/rpc/rag_ingest_source", { p_source: source, p_chunks: null })
      console.log(`${label} (text unchanged, metadata updated)`)
    } else {
      const vectors = await embed(chunks.map((c) => c.content))
      const n = await call("/rest/v1/rpc/rag_ingest_source", {
        p_source: source,
        p_chunks: chunks.map((c, i) => ({ ...c, embedding: vectors[i] })),
      })
      console.log(`${label} (embedded and stored ${n})`)
    }
  } catch (e) {
    failed++
    console.error(`FAILED ${file}: ${e.message}`)
  }
}
process.exit(failed ? 1 : 0)
