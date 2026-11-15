import { thermometerIcon, dropletIcon as dropIcon, rainIcon } from "./icons.js"

/**
 * Environmental layers that colour the sea, one at a time (see oceanLayer.js).
 * The ids must match OCEAN_LAYERS there.
 */
export const DATA_LAYERS = [
  { id: "sst", name: "Sea temperature", source: "NASA satellite (MUR)", icon: thermometerIcon },
  { id: "salinity", name: "Salinity", source: "NASA satellite (SMAP)", icon: dropIcon },
  { id: "rain", name: "Rainfall", source: "NASA satellite (GPM IMERG)", icon: rainIcon },
]

/** Where NASA publishes the base map; the globe credit links here (see earth/README.md). */
export const BLUE_MARBLE_URL = "https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map"

export function mountLayersMenu(btn, menu, { onChange } = {}) {
  let active = null
  const render = () => {
    menu.innerHTML = `
      <h2>Layers</h2>
      <ul>${DATA_LAYERS.map(
        (l) => `<li><button type="button" class="layer-item" data-layer="${l.id}" aria-pressed="${l.id === active}">
          ${l.icon}<span><span class="layer-name">${l.name}</span><span class="layer-src">${l.source}</span></span></button></li>`,
      ).join("")}</ul>
      <p class="layer-status">${active ? "Tap it again to hide the colours." : "Pick one to colour the sea."}</p>
      <p class="layer-credit">Globe surface: <a href="${BLUE_MARBLE_URL}" target="_blank" rel="noopener noreferrer">NASA Earth Observatory, Blue Marble Next Generation</a>. Ocean, relief and lights: NASA, via franky-adl/threejs-earth.</p>`
  }
  render()

  const setOpen = (open) => {
    menu.hidden = !open
    btn.setAttribute("aria-expanded", String(open))
  }
  btn.addEventListener("click", () => setOpen(menu.hidden))
  menu.addEventListener("click", (e) => {
    const b = e.target.closest("[data-layer]")
    if (!b) return
    active = active === b.dataset.layer ? null : b.dataset.layer
    render()
    menu.querySelector(`[data-layer="${b.dataset.layer}"]`).focus()
    onChange && onChange(active)
  })
  document.addEventListener("click", (e) => {
    if (!menu.hidden && !menu.contains(e.target) && !btn.contains(e.target)) setOpen(false)
  })
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !menu.hidden) setOpen(false), btn.focus()
  })
}
