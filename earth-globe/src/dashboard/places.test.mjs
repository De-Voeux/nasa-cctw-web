import test from "node:test"
import assert from "node:assert/strict"
import { placesIn } from "./places.js"

const L = [
  { id: "id-maluku", name: "Maluku" },
  { id: "id-s-sulawesi", name: "South Sulawesi" },
  { id: "id-se-sulawesi", name: "Southeast Sulawesi" },
  { id: "ph-bohol", name: "Bohol" },
  { id: "ph-ne-bohol", name: "Northeastern Bohol" },
  { id: "ph-zamboanga", name: "Zamboanga City" },
  { id: "ph-davao-norte", name: "Davao del Norte" },
  { id: "ph-tawi-tawi", name: "Tawi-Tawi" },
  { id: "my-sabah", name: "Sabah" },
  { id: "vn-khanh-hoa", name: "Khanh Hoa" },
  { id: "id-ntb", name: "West Nusa Tenggara" },
]
const ids = (t, max) => placesIn(t, L, max).map((l) => l.id)

test("finds places by whole name, ignoring case, in order of first appearance", () => {
  assert.deepEqual(ids("Outbreaks in tawi-tawi and then MALUKU."), ["ph-tawi-tawi", "id-maluku"])
  assert.deepEqual(ids("Sea temperature at Maluku (Kei Islands)"), ["id-maluku"])
})

test("a longer place name wins over the shorter one inside it", () => {
  assert.deepEqual(ids("Reports from Northeastern Bohol"), ["ph-ne-bohol"])
  assert.deepEqual(ids("Reports from Northeastern Bohol and from Bohol itself"), ["ph-ne-bohol", "ph-bohol"])
  assert.deepEqual(ids("Southeast Sulawesi and South Sulawesi"), ["id-se-sulawesi", "id-s-sulawesi"])
})

test("accents, short forms and spacing", () => {
  assert.deepEqual(ids("Khánh Hòa province"), ["vn-khanh-hoa"])
  assert.deepEqual(ids("Zamboanga City and Davao del   Norte"), ["ph-zamboanga", "ph-davao-norte"])
  assert.deepEqual(ids("NTB and North-eastern Bohol"), ["id-ntb", "ph-ne-bohol"])
})

test("it never guesses: countries, species, other places and partial words match nothing", () => {
  assert.deepEqual(ids("Indonesia, the Philippines and Kappaphycus alvarezii"), [])
  assert.deepEqual(ids("Sabahan culture and Malukuan food"), [])
  assert.deepEqual(ids("Camarines Norte, Calaguas Is."), [])
  assert.deepEqual(ids("Zamboanga del Norte, the gulf of Davao"), []) // a different place than the dashboard's Zamboanga City / Davao del Norte
  assert.deepEqual(ids(""), [])
})

test("at most four places", () => {
  assert.equal(placesIn("Maluku Sabah Bohol Tawi-Tawi Zamboanga", L).length, 4)
  assert.equal(placesIn("Maluku Sabah Bohol", L, 2).length, 2)
})
