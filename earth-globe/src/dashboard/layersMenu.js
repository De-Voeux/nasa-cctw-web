import { thermometerIcon, dropletIcon as dropIcon, rainIcon } from "./icons.js"

/**
 * Environmental layers the atlas will show, one at a time. None is connected
 * to the globe yet: picking one only marks it as chosen and says so.
 */
export const DATA_LAYERS = [
  { id: "sst", name: "Sea Water Temperature", source: "NASA GHRSST MUR L4 · 0.01°", icon: thermometerIcon },
  { id: "salinity", name: "Salinity", source: "Copernicus Global Ocean Physics · 0.083°", icon: dropIcon },
  { id: "rain", name: "Rainfall", source: "NASA GPM IMERG · Open-Meteo forecast", icon: rainIcon },
]

export function mountLayersMenu(btn, menu, { onChange } = {}) {
  let active = null
  const render = () => {
    menu.innerHTML = `
      <h2>Layers</h2>
      <ul>${DATA_LAYERS.map(
        (l) => `<li><button type="button" class="layer-item" data-layer="${l.id}" aria-pressed="${l.id === active}">
          ${l.icon}<span><span class="layer-name">${l.name}</span><span class="layer-src">${l.source}</span></span></button></li>`,
      ).join("")}</ul>
      <p class="layer-status">${active ? "This layer isn't connected to the globe yet." : "Layers aren't connected to the globe yet."}</p>`
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
