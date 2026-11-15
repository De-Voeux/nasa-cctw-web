import test from "node:test"
import assert from "node:assert/strict"
import { parseSource, chunkBody, hashBody } from "./corpus.mjs"

// Fixtures below are placeholders for testing the parser. They are not scientific text.
const FM = `---
id: test:one
title: A title
citation: Someone (2026). A title.
license: CC-BY-4.0
species: [Kappaphycus alvarezii, "Eucheuma denticulatum"]
countries: Philippines, Indonesia
---
## Methods
Alpha beta.

Gamma delta.
`

test("parses front matter, lists and body", () => {
  const { meta, body } = parseSource(FM)
  assert.equal(meta.id, "test:one")
  assert.deepEqual(meta.species, ["Kappaphycus alvarezii", "Eucheuma denticulatum"])
  assert.deepEqual(meta.countries, ["Philippines", "Indonesia"])
  assert.match(body, /^## Methods/)
})

test("an unknown key is an error, so a typo cannot leave a source unverified", () => {
  assert.throws(() => parseSource(FM.replace("license:", "verfied_by: X\nlicense:")), /unknown front matter key "verfied_by"/)
})

test("required fields, id shape and the verified pair are enforced", () => {
  assert.throws(() => parseSource(FM.replace("title: A title\n", "")), /needs "title"/)
  assert.throws(() => parseSource(FM.replace("id: test:one", "id: has/slash")), /id "has\/slash"/)
  assert.throws(() => parseSource(FM.replace("license: CC-BY-4.0", "license: x\nverified_by: Me")), /go together/)
  assert.throws(() => parseSource(FM.replace("license: CC-BY-4.0", "license: x\nverified_by: Me\nverified_on: 20/11/2026")), /YYYY-MM-DD/)
  assert.throws(() => parseSource("no front matter"), /missing front matter/)
  assert.throws(() => parseSource("---\nid: a\ntitle: b\ncitation: c\nlicense: d\n---\n"), /no text/)
})

test("a verified source parses with both fields", () => {
  const { meta } = parseSource(FM.replace("license: CC-BY-4.0", "license: x\nverified_by: Me\nverified_on: 2026-11-20"))
  assert.equal(meta.verified_by, "Me")
  assert.equal(meta.verified_on, "2026-11-20")
})

test("chunks keep their section title and stay under the limit", () => {
  const long = Array.from({ length: 40 }, (_, i) => `Sentence number ${i} says something about a topic.`).join(" ")
  const chunks = chunkBody(`## One\n${long}\n\n## Two\nShort section.`, { max: 300, overlap: 40 })
  assert.ok(chunks.length > 3)
  for (const c of chunks) assert.ok(c.content.length <= 300, `chunk ${c.ord} is ${c.content.length} chars`)
  assert.ok(chunks.filter((c) => c.section === "One").every((c) => c.content.startsWith("One\n")))
  assert.equal(chunks.at(-1).section, "Two")
  assert.deepEqual(chunks.map((c) => c.ord), chunks.map((_, i) => i))
})

test("a word longer than the limit does not loop forever or lose text", () => {
  const chunks = chunkBody("x".repeat(2500), { max: 1000, overlap: 0 })
  assert.equal(chunks.map((c) => c.content).join("").length, 2500)
})

test("text before the first heading is kept, and an empty section adds nothing", () => {
  const chunks = chunkBody("Intro line.\n\n## Empty\n\n## Real\nBody.")
  assert.deepEqual(chunks.map((c) => c.section), [null, "Real"])
})

test("hash changes with the text", () => {
  assert.notEqual(hashBody("a"), hashBody("b"))
  assert.equal(hashBody("a"), hashBody("a"))
})
