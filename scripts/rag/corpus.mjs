// Reading a source file and cutting it into chunks. No network, no dependencies: the
// ingest script (ingest.mjs) does the I/O, so this part can be tested on its own.
import { createHash } from "node:crypto"

/** Fields the front matter must carry. A source without them is rejected, not guessed. */
export const REQUIRED = ["id", "title", "citation", "license"]
const LIST_FIELDS = new Set(["species", "countries"])
const FIELDS = new Set([...REQUIRED, ...LIST_FIELDS, "doi", "url", "publisher", "year", "evidence_grade", "verified_by", "verified_on"])

/**
 * Parses `---` front matter of `key: value` lines. Lists are `[a, b]` or `a, b`.
 * Throws on unknown keys, so a typo like `verfied_by` cannot silently leave a source
 * unverified (or worse, look verified).
 */
export function parseSource(text, file = "source") {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(text)
  if (!m) throw new Error(`${file}: missing front matter (--- block at the top)`)
  const meta = {}
  for (const line of m[1].split(/\r?\n/)) {
    if (!line.trim() || line.trim().startsWith("#")) continue
    const i = line.indexOf(":")
    if (i < 1) throw new Error(`${file}: cannot read front matter line "${line}"`)
    const key = line.slice(0, i).trim()
    let val = line.slice(i + 1).trim()
    if (!FIELDS.has(key)) throw new Error(`${file}: unknown front matter key "${key}"`)
    if (LIST_FIELDS.has(key)) {
      val = val.replace(/^\[|\]$/g, "").split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean)
    } else {
      val = val.replace(/^["']|["']$/g, "")
    }
    meta[key] = val
  }
  for (const k of REQUIRED) if (!meta[k]) throw new Error(`${file}: front matter needs "${k}"`)
  if (!/^[a-z0-9][a-z0-9._:-]*$/i.test(meta.id)) throw new Error(`${file}: id "${meta.id}" may only use letters, digits and . _ : -`)
  if (meta.year && !/^\d{4}$/.test(meta.year)) throw new Error(`${file}: year must be four digits`)
  if (Boolean(meta.verified_by) !== Boolean(meta.verified_on)) {
    throw new Error(`${file}: verified_by and verified_on go together (both or neither)`)
  }
  if (meta.verified_on && !/^\d{4}-\d{2}-\d{2}$/.test(meta.verified_on)) throw new Error(`${file}: verified_on must be YYYY-MM-DD`)
  const body = m[2].trim()
  if (!body) throw new Error(`${file}: no text after the front matter`)
  meta.species ??= []
  meta.countries ??= []
  return { meta, body }
}

/** Hash of the text that gets embedded, so an unchanged source is not embedded again. */
export const hashBody = (body) => createHash("sha256").update(body).digest("hex")

/**
 * Splits Markdown into chunks of at most `max` characters (gte-small reads about 512
 * tokens). Splits on headings first, then on blank lines; a paragraph longer than `max`
 * is cut at sentence ends. Each chunk starts with its section title so it makes sense alone.
 * `overlap` characters of the previous chunk are repeated when a section had to be cut.
 */
export function chunkBody(body, { max = 1200, overlap = 150 } = {}) {
  const sections = []
  let current = { title: "", lines: [] }
  for (const line of body.split(/\r?\n/)) {
    const h = /^#{1,4}\s+(.*)$/.exec(line)
    if (h) {
      sections.push(current)
      current = { title: h[1].trim(), lines: [] }
    } else current.lines.push(line)
  }
  sections.push(current)

  const out = []
  for (const sec of sections) {
    const paras = sec.lines.join("\n").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
    const prefix = sec.title ? `${sec.title}\n` : ""
    const room = max - prefix.length
    let buf = ""
    const flush = () => {
      if (buf.trim()) out.push({ section: sec.title || null, content: prefix + buf.trim() })
    }
    const pieces = paras.flatMap((p) => (p.length <= room ? [p] : splitSentences(p, room)))
    for (const piece of pieces) {
      if (buf && buf.length + piece.length + 2 > room) {
        flush()
        buf = buf.slice(Math.max(0, buf.length - overlap)).replace(/^\S*\s/, "") // overlap on a word boundary
        if (buf.length + piece.length + 2 > room) buf = "" // no room for it next to this piece
      }
      buf += (buf ? "\n\n" : "") + piece
    }
    flush()
  }
  return out.map((c, ord) => ({ ord, ...c }))
}

function splitSentences(text, room) {
  const parts = []
  let buf = ""
  for (const s of text.split(/(?<=[.!?])\s+/)) {
    if (s.length > room) {
      if (buf) parts.push(buf), (buf = "")
      for (let i = 0; i < s.length; i += room) parts.push(s.slice(i, i + room))
      continue
    }
    if (buf && buf.length + s.length + 1 > room) parts.push(buf), (buf = "")
    buf += (buf ? " " : "") + s
  }
  if (buf) parts.push(buf)
  return parts
}
