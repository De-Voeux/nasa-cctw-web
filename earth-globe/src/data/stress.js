/**
 * Environmental stress levels shown on the region cards.
 *
 * There is NO biological assessment yet: environmental layers may be connected,
 * but no species rule has been reviewed (see
 * docs/METHODOLOGY.md). Regions without an observed series remain "Insufficient
 * Data"; observed regions are still unassessed biologically. A card must never
 * say Favorable, Moderate Risk or Elevated Risk for a real region until an
 * assessment backs it; replace `assess()` with a lookup of real results when they exist.
 *
 * The mock (see MOCK_DEFAULT below) is available only for an explicit design review.
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

/*
 * Demo levels and conditions are made up for design review. They are not assessments
 * and must never be the default. `?demo=levels` enables them explicitly.
 */
const MOCK_DEFAULT = false
const demoParam = new URLSearchParams(location.search).get("demo")
export const DEMO = demoParam === "levels" || (MOCK_DEFAULT && demoParam !== "off")

const NO_DATA = "No environmental data available for this region"
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
