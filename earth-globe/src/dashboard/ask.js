/**
 * Ask bar. There is no AI backend yet, so this answers a few questions
 * locally from the loaded data and is explicit about what it counts.
 * Replace `answer()` with an API call when the assistant exists.
 */
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])

export function answer(question, locations) {
  const q = question.toLowerCase()

  // "Which area has the most ice-ice …"
  if (/\bmost\b/.test(q) && /(ice|report|case|mention)/.test(q)) {
    const max = Math.max(...locations.map((l) => l.taxa.length))
    const top = locations.filter((l) => l.taxa.length === max)
    const names = top.map((l) => `<a href="#" class="link" data-goto="${l.id}">${esc(l.name)}</a>`).join(", ")
    return {
      focus: top[0],
      html: `<p><b>${names}</b> ${top.length > 1 ? "appear" : "appears"} with the most host taxa in the candidate leads (${max}: ${top[0].taxa.map((t) => `<i>${esc(t)}</i>`).join(", ")}).</p>
        <p class="muted small">This counts taxon mentions in unverified research leads. It is not a case count, outbreak frequency, or risk ranking.</p>`,
    }
  }

  // A place name or country in the question → go there.
  const hit =
    locations.find((l) => q.includes(l.name.toLowerCase())) ||
    locations.find((l) => q.includes(l.country.toLowerCase()))
  if (hit) {
    const inCountry = locations.filter((l) => l.country === hit.country)
    const isCountry = !q.includes(hit.name.toLowerCase())
    return {
      focus: hit,
      html: isCountry
        ? `<p>${esc(hit.country)} has <b>${inCountry.length}</b> places in the candidate leads: ${inCountry.map((l) => `<a href="#" class="link" data-goto="${l.id}">${esc(l.name)}</a>`).join(", ")}.</p>`
        : `<p>Showing <a href="#" class="link" data-goto="${hit.id}">${esc(hit.name)}</a>.</p>`,
      openDetail: !isCountry,
    }
  }

  return {
    html: `<p>The assistant isn't connected yet. Try “Which area has the most ice-ice reports?” or a place name like “Tawi-Tawi”.</p>`,
  }
}
