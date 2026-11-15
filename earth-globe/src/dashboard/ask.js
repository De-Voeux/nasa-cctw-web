/**
 * Answers for the "Ask SEAmon" chat. There is no AI backend yet, so this
 * answers a few questions locally from the loaded data and is explicit about
 * what it counts. Replace `answer()` with an API call when the assistant exists;
 * keep the return shape so the chat can still show "Show …" buttons.
 *
 * @returns {{html:string, focus?:any, autoShow?:boolean, actions?:{label:string, loc:any}[]}}
 *   html must already be escaped.
 */
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c])

export function answer(question, locations) {
  const q = question.toLowerCase()

  // "Which area has the most ice-ice …"
  if (/\bmost\b/.test(q) && /(ice|report|case|mention)/.test(q)) {
    const max = Math.max(...locations.map((l) => l.taxa.length))
    const top = locations.filter((l) => l.taxa.length === max)
    const names = top.map((l) => esc(l.name)).join(", ")
    return {
      focus: top[0],
      actions: top.map((l) => ({ label: `Show ${l.name}`, loc: l })),
      html: `<p><b>${names}</b> ${top.length > 1 ? "appear" : "appears"} with the most seaweed types mentioned in research papers (${max}).</p>
        <p class="small muted">This counts mentions, not ice-ice cases.</p>`,
    }
  }

  // A place name or country in the question.
  const hit =
    locations.find((l) => q.includes(l.name.toLowerCase())) ||
    locations.find((l) => q.includes(l.country.toLowerCase()))
  if (hit) {
    const isCountry = !q.includes(hit.name.toLowerCase())
    if (isCountry) {
      const inCountry = locations.filter((l) => l.country === hit.country)
      return {
        focus: hit,
        actions: inCountry.slice(0, 4).map((l) => ({ label: `Show ${l.name}`, loc: l })),
        html: `<p>${esc(hit.country)} has <b>${inCountry.length}</b> places with reported ice-ice.</p>`,
      }
    }
    return { focus: hit, autoShow: true, html: `<p>Here is <b>${esc(hit.name)}</b>, ${esc([hit.area, hit.country].filter(Boolean).join(", "))}.</p>` }
  }

  return {
    html: `<p>I can't answer that yet. Try “Which area has the most ice-ice case?” or “Area in Indonesia that produce cottoni”.</p>`,
  }
}
