import test from "node:test"
import assert from "node:assert/strict"
import { parseCsv, parseSites, toValue, tidyRows, powerDailyRows, assertUnique, expectedCoverage } from "./parse.mjs"

// Fixtures are made-up numbers for exercising the parser, not measurements.
const SITES = parseSites([{ id: "s1", name: "Site 1", country: "Indonesia", lat: -5.6, lon: 132.7 }])

test("CSV: quotes, doubled quotes, CRLF, blank lines and a ragged row", () => {
  assert.deepEqual(parseCsv('a,b\r\n"x, y","say ""hi"""\r\n\r\n1,2\r\n'), [{ a: "x, y", b: 'say "hi"' }, { a: "1", b: "2" }])
  assert.throws(() => parseCsv("a,b\n1\n"), /line 2 has 1 fields/)
  assert.throws(() => parseCsv('a\n"open\n'), /unterminated/)
})

test("sites: validated and unique", () => {
  assert.equal(SITES.length, 1)
  const bad = (patch) => () => parseSites([{ id: "s1", name: "n", country: "c", lat: 1, lon: 2, ...patch }])
  assert.throws(bad({ id: "Bad Id" }), /bad site id/)
  assert.throws(bad({ lat: 91 }), /bad lat/)
  assert.throws(bad({ lon: "x" }), /bad lon/)
  assert.throws(bad({ name: "" }), /missing "name"/)
  assert.throws(() => parseSites([{ id: "a", name: "n", country: "c", lat: 1, lon: 2 }, { id: "a", name: "n", country: "c", lat: 1, lon: 2 }]), /duplicate/)
})

test("values: empty and -999 are missing, junk is an error, nothing is rounded", () => {
  assert.equal(toValue(""), null)
  assert.equal(toValue("-999"), null)
  assert.equal(toValue("-999.0"), null)
  assert.equal(toValue("-99.9"), -99.9)
  assert.equal(toValue("30.173000000000002"), 30.173000000000002)
  assert.throws(() => toValue("NaN", "here"), /here: "NaN" is not a number/)
})

const TIDY = "site_id,country,lat,lon,variable,unit,date,value\ns1,Indonesia,-5.6,132.7,analysed_sst,degree_C,2003-01-01,29.5\ns1,Indonesia,-5.6,132.7,analysed_sst,degree_C,2003-01-31,\n"

test("tidy rows carry the product name and keep a missing value as null", () => {
  const rows = tidyRows(TIDY, "mur", SITES, "f.csv")
  assert.equal(rows.length, 2)
  assert.deepEqual(rows[0], { site_id: "s1", day: "2003-01-01", variable: "analysed_sst", value: 29.5, unit: "degree_C", product: "MUR-30d", product_version: rows[0].product_version })
  assert.equal(rows[1].value, null)
  assert.match(rows[0].product_version, /30 days/)
})

test("tidy rows are rejected for an unknown site, moved coordinates, a bad date or a missing unit", () => {
  assert.throws(() => tidyRows(TIDY.replaceAll("s1,", "zz,"), "mur", SITES, "f"), /unknown site "zz"/)
  assert.throws(() => tidyRows(TIDY.replace("-5.6,132.7", "-5.7,132.7"), "mur", SITES, "f"), /coordinates differ/)
  assert.throws(() => tidyRows(TIDY.replace("2003-01-01", "01/01/2003"), "mur", SITES, "f"), /bad date/)
  assert.throws(() => tidyRows(TIDY.replace("degree_C,2003-01-01", ",2003-01-01"), "mur", SITES, "f"), /variable and unit/)
})

const POWER = `-BEGIN HEADER-
NASA/POWER Source Native Resolution Daily Data
The value for missing source data that cannot be computed or is outside of the sources availability range: -999
parameter(s):
T2M                   MERRA-2 Temperature at 2 Meters (C)
PRECTOTCORR           MERRA-2 Precipitation Corrected (mm/day)
ALLSKY_SFC_SW_DWN     CERES SYN1deg All Sky Surface Shortwave Downward Irradiance (MJ/m^2/day)
-END HEADER-
YEAR,DOY,T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN
2004,59,28.4,1.5,5.9
2004,60,28.3,-999,6.1
2004,366,28.0,0.2,5.0
`

test("POWER daily: units from the header, DOY to date (leap year), -999 to null, variable filter", () => {
  const rows = powerDailyRows(POWER, "s1", ["PRECTOTCORR", "ALLSKY_SFC_SW_DWN"], "p.csv")
  assert.equal(rows.length, 6)
  const p = rows.filter((r) => r.variable === "PRECTOTCORR")
  assert.deepEqual(p.map((r) => [r.day, r.value]), [["2004-02-28", 1.5], ["2004-02-29", null], ["2004-12-31", 0.2]])
  assert.equal(p[0].unit, "mm/day")
  assert.equal(rows.find((r) => r.variable === "ALLSKY_SFC_SW_DWN").unit, "MJ/m^2/day")
  assert.equal(p[0].product, "POWER-daily")
  assert.ok(!rows.some((r) => r.variable === "T2M"))
  assert.equal(powerDailyRows(POWER, "s1", undefined, "p.csv").length, 9)
})

test("POWER daily: a day 366 in a non-leap year, a missing header and a missing unit are errors", () => {
  assert.throws(() => powerDailyRows(POWER.replace("2004,366", "2003,366").replace("2004,59", "2003,59").replace("2004,60", "2003,60"), "s1", undefined, "p"), /outside 2003/)
  assert.throws(() => powerDailyRows("YEAR,DOY\n", "s1", undefined, "p"), /no POWER header/)
  assert.throws(() => powerDailyRows(POWER.replace("(C)", ""), "s1", undefined, "p"), /no unit for T2M/)
})

test("duplicates are refused and coverage counts only real values", () => {
  const rows = tidyRows(TIDY, "mur", SITES, "f")
  assert.throws(() => assertUnique([...rows, rows[0]]), /duplicate row/)
  const cov = expectedCoverage(rows).get("s1|MUR-30d|analysed_sst")
  assert.deepEqual(cov, { n: 1, from: "2003-01-01", to: "2003-01-31" })
})
