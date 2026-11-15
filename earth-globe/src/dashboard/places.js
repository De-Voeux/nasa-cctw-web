/**
 * Which of the dashboard's places does a piece of text name? Used to offer "Show on the globe" buttons under
 * an assistant answer, and to fly there at once when the QUESTION names exactly one place.
 *
 * Plain whole-word matching on the place names (and a few obvious short forms), ignoring case and accents.
 * It never guesses: a country, a species, or a place that is not on the dashboard matches nothing.
 */

// Short forms people actually write. Kept to the ones that cannot mean another place: "Zamboanga" or "Davao" alone
// could be a province or a gulf, so they are NOT aliases (an answer about Zamboanga del Norte must not offer
// a button labelled Zamboanga City).
const ALIASES = {
  "id-ntb": ["ntb"],
  "ph-ne-bohol": ["north-eastern bohol", "north eastern bohol"],
}

const plain = (s) => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")

/**
 * @param {string} text
 * @param {{id:string, name:string}[]} locations
 * @param {number} [max]
 * @returns {object[]} matching locations, in order of first appearance, at most `max`
 */
export function placesIn(text, locations, max = 4) {
  const t = plain(text)
  const hits = []
  for (const loc of locations) {
    for (const name of [loc.name, ...(ALIASES[loc.id] ?? [])]) {
      const re = new RegExp(`(?<![a-z0-9])${escape(plain(name)).replace(/\s+/g, "\\s+")}(?![a-z0-9])`, "g")
      for (const m of t.matchAll(re)) hits.push({ loc, start: m.index, end: m.index + m[0].length })
    }
  }
  // "Bohol" inside "Northeastern Bohol" is the longer place, not both
  const kept = hits.filter((h) => !hits.some((o) => o.loc !== h.loc && o.start <= h.start && o.end >= h.end && o.end - o.start > h.end - h.start))
  kept.sort((a, b) => a.start - b.start)
  const out = []
  for (const h of kept) if (!out.includes(h.loc)) out.push(h.loc)
  return out.slice(0, max)
}
