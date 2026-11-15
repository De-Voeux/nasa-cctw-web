/**
 * How each water condition on the dashboard relates to ice-ice, and what ice-ice
 * does to the seaweed. Shown in a place's detail panel (sidePanel.js).
 *
 * Every line comes from the three papers below; `cite` names the study and,
 * when the finding is quoted from a review, the review it was read in.
 * Checked against research/corpus/ and the Alimin et al. (2026) PDF on 15 Nov 2026.
 * These are findings from studies, not thresholds the dashboard applies.
 */

export const PAPERS = {
  alimin2026: { short: "Alimin et al. 2026", url: "https://doi.org/10.1007/s10499-026-02486-2" },
  tahiluddin2021: { short: "Tahiluddin & Terzi 2021", url: "https://doi.org/10.33714/masteb.917788" },
  tahiluddin2024: { short: "Tahiluddin & Terzi 2024", url: "https://doi.org/10.3390/plants13152157" },
}

/** In the order a reader meets them in the panel. `key` matches the stressor keys where there is one. */
export const LINKS = [
  {
    key: "sst",
    name: "Sea temperature",
    text: "Warm water is the trigger reported most often. In lab tests, 33–35 °C turned seaweed white like ice-ice, and on farms in Zanzibar outbreaks peaked in the hot season.",
    cite: [["Largo et al., in", "tahiluddin2021"], ["", "alimin2026"]],
  },
  {
    key: "salinity",
    name: "Salinity",
    text: "These seaweeds need salty sea water. In lab tests, a drop to 20 PSU or less for about a week led to ice-ice.",
    cite: [["Largo et al., in", "tahiluddin2021"]],
  },
  {
    key: "rain",
    name: "Rainfall",
    text: "Heavy rain makes coastal water less salty. A study in the Philippines linked ice-ice to monthly rainfall.",
    cite: [["Faisan et al. 2021, in", "alimin2026"]],
  },
  {
    key: "current",
    name: "Water flow",
    text: "Still water was reported with ice-ice on farms in Pangasinan (Philippines) and Kenya.",
    cite: [["", "alimin2026"]],
  },
  {
    key: "light",
    name: "Sunlight",
    text: "Both too little light (crowded lines, seaweed covered by other algae) and too much (very shallow farms) were linked to ice-ice. Not on the map yet.",
    cite: [["", "tahiluddin2021"]],
  },
  {
    key: "nutrients",
    name: "Nutrients",
    text: "Too little nitrogen and phosphorus in the water was reported as a trigger. Not on the map yet.",
    cite: [["Maryunus 2018, in", "tahiluddin2021"]],
  },
]

/** What ice-ice does to the seaweed and the farm. */
export const IMPACTS = [
  { text: "Parts of the seaweed turn white and soft.", cite: [["", "tahiluddin2021"]] },
  { text: "It loses its colour pigments, so it makes less energy from light and grows slower.", cite: [["Ganzon-Fortes et al. 1993, in", "tahiluddin2021"]] },
  { text: "Bacteria then break down the weak parts, and branches fall apart.", cite: [["", "tahiluddin2021"], ["", "alimin2026"]] },
  { text: "Its carrageenan, the gel the seaweed is sold for, gets worse, so it sells for less.", cite: [["", "tahiluddin2021"], ["", "alimin2026"]] },
  { text: "Farms lose harvest. In the Philippines, ice-ice and pests cut Kappaphycus production by about 15% in 2011–2013.", cite: [["Cottier-Cook et al. 2016, in", "tahiluddin2021"]] },
]

/** The honest limit, shown under the list. */
export const CAVEAT = {
  text: "These links come from studies, not a rule for every farm. A year-long study in Tawi-Tawi found no clear link between ice-ice and temperature, salinity or water flow there.",
  cite: [["", "tahiluddin2024"]],
}
