/**
 * What a measurement means for the seaweed, shown under each chart in a place's
 * detail panel (sidePanel.js), plus what ice-ice does to the seaweed.
 *
 * Every statement comes from the three papers below; `cite` names the study and,
 * when the finding is quoted from a review, the review it was read in.
 * Checked against research/corpus/ and the Alimin et al. (2026) PDF on 15 Nov 2026.
 * The numbers (33 °C, 29.5 °C, 20 and 25–35 PSU) are what those studies observed,
 * mostly in lab tests. They describe the research, they are not rules the dashboard
 * scores with (those are in environmentRules.js).
 */

export const PAPERS = {
  alimin2026: { short: "Alimin et al. 2026", url: "https://doi.org/10.1007/s10499-026-02486-2" },
  tahiluddin2021: { short: "Tahiluddin & Terzi 2021", url: "https://doi.org/10.33714/masteb.917788" },
  tahiluddin2024: { short: "Tahiluddin & Terzi 2024", url: "https://doi.org/10.3390/plants13152157" },
}

const LARGO = [["Largo et al., in", "tahiluddin2021"]]
const NUTRIENTS = {
  cite: [["Maryunus 2018, in", "tahiluddin2021"], ["", "tahiluddin2024"]],
  text: () =>
    "Too little nitrogen and phosphorus was reported as a trigger for ice-ice. A year-long study in Tawi-Tawi found no clear link, so no safe level has been set yet.",
}

/**
 * Per measurement key: `text(value)` says what this value means for the seaweed,
 * using what the studies found. Keys match the stressor keys (live and sample data).
 * @type {Record<string, {text:(v:number)=>string, cite:[string,string][]}>}
 */
export const INSIGHTS = {
  sst: {
    cite: [...LARGO, ["", "alimin2026"]],
    text: (v) =>
      v >= 33
        ? "Very hot for seaweed. In lab tests, 33–35 °C turned it white like ice-ice."
        : v >= 29.5
          ? "Warm. On farms in Zanzibar, water from 29.5 °C up was a main trigger of ice-ice, and outbreaks peaked in the hot season."
          : "Below the hot range that studies link to ice-ice outbreaks.",
  },
  salinity: {
    cite: LARGO,
    text: (v) =>
      v <= 20
        ? "Too fresh. In lab tests, a week at 20 PSU or less led to ice-ice."
        : v < 25
          ? "Fresher than the 25–35 PSU that seaweed handled well in lab tests. A week at 20 PSU or less led to ice-ice."
          : v <= 35
            ? "Within 25–35 PSU, the range seaweed handled well in lab tests."
            : "Saltier than the 25–35 PSU range tested in the lab.",
  },
  rain: {
    cite: [["Faisan et al. 2021, in", "alimin2026"]],
    text: () => "Heavy rain makes coastal water less salty. A study in the Philippines linked ice-ice to monthly rainfall.",
  },
  current: {
    cite: [["", "alimin2026"]],
    text: () => "Low water flow was reported with ice-ice on farms in Pangasinan (Philippines) and Kenya.",
  },
  nitrate: NUTRIENTS,
  phosphate: NUTRIENTS,
  ph: {
    cite: [["", "alimin2026"], ["", "tahiluddin2024"]],
    text: () =>
      "More acidic water is named as a growing stress on seaweed farms, but the Tawi-Tawi study found no clear link between pH and ice-ice.",
  },
}

/** What ice-ice does to the seaweed and the farm. */
export const IMPACTS = [
  { text: "Parts of the seaweed turn white and soft.", cite: [["", "tahiluddin2021"]] },
  { text: "It loses its colour pigments, so it makes less energy from light and grows slower.", cite: [["Ganzon-Fortes et al. 1993, in", "tahiluddin2021"]] },
  { text: "Bacteria then break down the weak parts, and branches fall apart.", cite: [["", "tahiluddin2021"], ["", "alimin2026"]] },
  { text: "Its carrageenan, the gel the seaweed is sold for, gets worse, so it sells for less.", cite: [["", "tahiluddin2021"], ["", "alimin2026"]] },
  { text: "Farms lose harvest. In the Philippines, ice-ice and pests cut Kappaphycus production by about 15% in 2011–2013.", cite: [["Cottier-Cook et al. 2016, in", "tahiluddin2021"]] },
]

/** The honest limit, shown under the impacts. */
export const CAVEAT = {
  text: "These are findings from studies, not a rule for every farm. Ice-ice usually starts when the water stresses the seaweed, and bacteria then attack the weak parts.",
  cite: [["", "tahiluddin2021"], ["", "alimin2026"]],
}
