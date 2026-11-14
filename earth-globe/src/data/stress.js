/**
 * Environmental stress levels shown on the region cards.
 *
 * There is NO assessment yet: the NASA, Copernicus and Open-Meteo layers are not
 * connected to this dashboard and no species rule has been reviewed (see
 * docs/METHODOLOGY.md). So every region is "Insufficient Data". A card must never
 * say Favorable, Moderate Risk or Elevated Risk for a real region until an
 * assessment backs it; replace `assess()` with a lookup of real results when they exist.
 *
 * `?demo=levels` hands out made-up levels so the four card designs can be reviewed.
 * The panel then says the values are demo values, and nothing here is real data.
 */
import favorable from "../assets/ui/levels/favorable.svg"
import moderate from "../assets/ui/levels/moderate.svg"
import elevated from "../assets/ui/levels/elevated.svg"
import insufficient from "../assets/ui/levels/insufficient-data.svg"

export const LEVELS = {
  favorable: { label: "Favorable", icon: favorable, rank: 0 },
  moderate: { label: "Moderate Risk", icon: moderate, rank: 1 },
  elevated: { label: "Elevated Risk", icon: elevated, rank: 2 },
  insufficient: { label: "Insufficient Data", icon: insufficient, rank: 3 },
}

/** Order used by the Stress Level filter. */
export const LEVEL_ORDER = ["favorable", "moderate", "elevated", "insufficient"]

export const DEMO = new URLSearchParams(location.search).get("demo") === "levels"

const NO_DATA = "Environmental layers not connected yet"
const DEMO_CONDITION = {
  favorable: "Normal condition",
  moderate: "Warm water",
  elevated: "Warm water, high salinity",
  insufficient: NO_DATA,
}

// Same id always gets the same demo level, so a reload does not reshuffle the cards.
const demoLevel = (id) => LEVEL_ORDER[[...id].reduce((s, c) => s + c.charCodeAt(0), 0) % LEVEL_ORDER.length]

/**
 * @param {{id:string}} loc
 * @returns {{level:keyof typeof LEVELS, condition:string, demo:boolean}}
 */
export function assess(loc) {
  if (DEMO) {
    const level = demoLevel(loc.id)
    return { level, condition: DEMO_CONDITION[level], demo: true }
  }
  return { level: "insufficient", condition: NO_DATA, demo: false }
}
