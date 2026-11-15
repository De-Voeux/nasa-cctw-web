/**
 * Environmental stress levels shown on the region cards.
 *
 * There is NO assessment yet: the NASA, Copernicus and Open-Meteo layers are not
 * connected to this dashboard and no species rule has been reviewed (see
 * docs/METHODOLOGY.md). So every region is "Insufficient Data". A card must never
 * say Favorable, Moderate Risk or Elevated Risk for a real region until an
 * assessment backs it; replace `assess()` with a lookup of real results when they exist.
 *
 * The mock (see MOCK_DEFAULT below) hands out made-up levels so the four card designs
 * can be reviewed. The panel then says the values are demo values; none is real data.
 */
import favorable from "../assets/ui/levels/favorable.svg"
import moderate from "../assets/ui/levels/moderate.svg"
import elevated from "../assets/ui/levels/elevated.svg"
import insufficient from "../assets/ui/levels/insufficient-data.svg"

export const LEVELS = {
  favorable: { label: "Good conditions", icon: favorable, rank: 0 },
  moderate: { label: "Moderate stress", icon: moderate, rank: 1 },
  elevated: { label: "High stress", icon: elevated, rank: 2 },
  insufficient: { label: "Not enough data", icon: insufficient, rank: 3 },
}

/** Order used by the Stress Level filter. */
export const LEVEL_ORDER = ["favorable", "moderate", "elevated", "insufficient"]

/*
 * MOCK ON BY DEFAULT (decided with Radit, 2026-11-15, to match the design mock).
 * The levels and conditions below are made up for the design review. They are NOT
 * assessments and must not ship to a public site as if they were. The panel shows a
 * banner saying so while this is on. Before real use: set MOCK_DEFAULT to false (or
 * delete the demo branch of assess()) so every region reads "Insufficient Data"
 * until real results exist. `?demo=off` turns the mock off, `?demo=levels` forces it on.
 */
const MOCK_DEFAULT = true
const demoParam = new URLSearchParams(location.search).get("demo")
export const DEMO = demoParam === "levels" || (MOCK_DEFAULT && demoParam !== "off")

const NO_DATA = "No ocean data yet"
const DEMO_CONDITION = {
  favorable: "Normal conditions",
  moderate: "Warm water",
  elevated: "Warm, salty water",
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
