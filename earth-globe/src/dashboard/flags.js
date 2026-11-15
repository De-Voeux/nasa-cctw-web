import id from "../assets/ui/flags/id.png"
import idOn from "../assets/ui/flags/id-selected.png"
import my from "../assets/ui/flags/my.png"
import myOn from "../assets/ui/flags/my-selected.png"
import ph from "../assets/ui/flags/ph.png"
import phOn from "../assets/ui/flags/ph-selected.png"
import vn from "../assets/ui/flags/vn.png"
import vnOn from "../assets/ui/flags/vn-selected.png"

/** The four countries in the research leads. `country` matches LOCATIONS[].country. */
export const FLAGS = [
  { country: "Indonesia", src: id, selected: idOn },
  { country: "Malaysia", src: my, selected: myOn },
  { country: "Philippines", src: ph, selected: phOn },
  { country: "Vietnam", src: vn, selected: vnOn },
]

/**
 * Round flag buttons that filter by country. Clicking the selected flag again
 * clears the filter (all countries). The selected image is a larger one with a ring.
 * @param {HTMLElement} root
 * @param {{selected:string|null, onChange:(country:string|null)=>void}} opts
 */
export function mountFlags(root, { selected, onChange }) {
  let current = selected
  root.innerHTML = FLAGS.map(
    (f) => `
    <button type="button" class="flag" data-country="${f.country}" aria-pressed="false" aria-label="${f.country}" title="${f.country}">
      <img alt="" width="42" height="42" src="${f.src}" data-off="${f.src}" data-on="${f.selected}">
    </button>`,
  ).join("")

  function paint() {
    for (const b of root.querySelectorAll(".flag")) {
      const on = b.dataset.country === current
      b.setAttribute("aria-pressed", String(on))
      const img = b.querySelector("img")
      img.src = on ? img.dataset.on : img.dataset.off
    }
  }

  root.addEventListener("click", (e) => {
    const b = e.target.closest(".flag")
    if (!b) return
    current = current === b.dataset.country ? null : b.dataset.country
    paint()
    onChange(current)
  })

  paint()
  return {
    get current() {
      return current
    },
  }
}
