/**
 * Fits the globe canvas into the space the dashboard chrome leaves free, and
 * owns the mobile bottom sheet (the side panel becomes a sheet under 860px).
 *
 * On wide screens the globe is full-bleed and the panel floats over it, which
 * is the intended look. On narrow screens the panel is a bottom sheet and the
 * date/ask bars sit over the map, so the canvas is shrunk to the band between
 * them: the globe stays centred in what the user can actually see. The star
 * field is painted on the page, so the smaller canvas leaves no seam.
 */
const SHEET_QUERY = "(max-width: 860px)"
const SHORT_QUERY = "(max-height: 520px)"
// Below this many pixels of map height the place names no longer fit.
const COMPACT_BAND = 340

export function initLayout() {
  const root = document.documentElement
  const dateBar = document.querySelector(".date-bar")
  const askBar = document.querySelector(".ask-bar")
  const layersBtn = document.querySelector("#layers-btn")
  const toggle = document.querySelector(".sheet-toggle")
  const sheetMQ = window.matchMedia(SHEET_QUERY)
  const shortMQ = window.matchMedia(SHORT_QUERY)

  // Landscape phones have almost no height to spare: start with the sheet
  // collapsed so the globe is visible, until the user opens it.
  let collapsed = shortMQ.matches

  function apply() {
    root.classList.toggle("sheet-layout", sheetMQ.matches)
    root.classList.toggle("short-viewport", shortMQ.matches)
    root.classList.toggle("sheet-collapsed", collapsed)
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(!collapsed))
      toggle.setAttribute("aria-label", collapsed ? "Show locations" : "Hide locations")
    }
    if (!sheetMQ.matches) {
      root.style.setProperty("--globe-top", "0px")
      root.style.setProperty("--globe-bottom", "0px")
      root.style.setProperty("--controls-top", "0px")
      root.classList.remove("map-compact")
      return
    }
    const vh = window.innerHeight
    const top = dateBar ? dateBar.getBoundingClientRect().bottom : 0
    const bottom = askBar ? vh - askBar.getBoundingClientRect().top : 0
    root.style.setProperty("--globe-top", `${Math.max(0, Math.round(top))}px`)
    root.style.setProperty("--globe-bottom", `${Math.max(0, Math.round(bottom))}px`)
    // the map controls start below the date bar, whatever height it has
    root.style.setProperty("--controls-top", `${Math.round(top) + 12}px`)
    // the layers menu opens under its button and stops above the ask bar
    const menuTop = layersBtn ? layersBtn.getBoundingClientRect().bottom + 8 : top
    const menuBottom = askBar ? vh - askBar.getBoundingClientRect().top + 8 : 60
    root.style.setProperty("--menu-top", `${Math.round(menuTop)}px`)
    root.style.setProperty("--menu-bottom", `${Math.round(Math.min(vh - menuTop - 60, menuBottom))}px`)
    // A short map band cannot carry the place names: they would sit on top of
    // each other and of the markers.
    root.classList.toggle("map-compact", vh - top - bottom < COMPACT_BAND)
  }

  toggle?.addEventListener("click", () => {
    collapsed = !collapsed
    apply()
  })

  // The chrome moves when the sheet opens, collapses or the window changes.
  const ro = new ResizeObserver(() => apply())
  for (const el of [dateBar, askBar, document.querySelector(".side-panel")]) if (el) ro.observe(el)

  window.addEventListener("resize", apply)
  window.addEventListener("orientationchange", apply)
  sheetMQ.addEventListener("change", apply)
  shortMQ.addEventListener("change", () => {
    collapsed = shortMQ.matches
    apply()
  })

  apply()
  return { apply }
}
