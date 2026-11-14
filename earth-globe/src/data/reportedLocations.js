/**
 * Ice-ice report locations for the dashboard markers.
 *
 * Source: research/evidence/CANDIDATE_HOST_REGIONS.md (user-provided leads,
 * 14 Nov 2026). Every row there is UNVERIFIED: it records places said to be
 * mentioned in a paper, not confirmed cultivation, local disease occurrence,
 * or case counts. Keep `verification: "pending"` until a row is checked
 * against the original publication.
 *
 * lat/lon are approximate display anchors for the named province/region
 * (placed on nearby water so markers don't sit inland). They are NOT farm
 * or sampling coordinates.
 */

export const SOURCE = {
  label: "Candidate host & region leads",
  file: "research/evidence/CANDIDATE_HOST_REGIONS.md",
  status: "unverified",
}

const KA = "Kappaphycus alvarezii"
const KS = "Kappaphycus striatus"
const KSPP = "Kappaphycus spp."
const ED = "Eucheuma denticulatum"
const GV = "Gracilaria verrucosa"

/** @type {{id:string,name:string,country:string,lat:number,lon:number,taxa:string[],concern:string,verification:"pending"}[]} */
export const LOCATIONS = [
  { id: "ph-pangasinan", name: "Pangasinan", country: "Philippines", lat: 16.2, lon: 119.95, taxa: [KA] },
  { id: "ph-batangas", name: "Batangas", country: "Philippines", lat: 13.6, lon: 121.0, taxa: [KS] },
  { id: "ph-southern-luzon", name: "Southern Luzon", country: "Philippines", lat: 13.2, lon: 123.4, taxa: [KA, KS] },
  { id: "ph-eastern-samar", name: "Eastern Samar", country: "Philippines", lat: 11.5, lon: 125.65, taxa: [KA] },
  { id: "ph-palawan", name: "Palawan", country: "Philippines", lat: 9.6, lon: 118.95, taxa: [KA, KS] },
  { id: "ph-ne-bohol", name: "Northeastern Bohol", country: "Philippines", lat: 10.15, lon: 124.45, taxa: [ED, KA] },
  { id: "ph-bohol", name: "Bohol", country: "Philippines", lat: 9.6, lon: 124.0, taxa: [KS] },
  { id: "ph-zamboanga", name: "Zamboanga City", country: "Philippines", lat: 6.85, lon: 122.1, taxa: [KS] },
  { id: "ph-davao-norte", name: "Davao del Norte", country: "Philippines", lat: 7.25, lon: 125.75, taxa: [KS] },
  { id: "ph-tawi-tawi", name: "Tawi-Tawi", country: "Philippines", lat: 5.05, lon: 119.9, taxa: [ED, KSPP, KA, KS] },
  { id: "my-sabah", name: "Sabah", country: "Malaysia", lat: 4.6, lon: 118.5, taxa: [KA] },
  { id: "vn-khanh-hoa", name: "Khanh Hoa", country: "Vietnam", lat: 12.2, lon: 109.35, taxa: [KS] },
  { id: "id-n-kalimantan", name: "North Kalimantan", country: "Indonesia", lat: 3.3, lon: 117.9, taxa: [KA] },
  { id: "id-c-sulawesi", name: "Central Sulawesi", country: "Indonesia", lat: -1.0, lon: 122.0, taxa: [KA] },
  { id: "id-se-sulawesi", name: "Southeast Sulawesi", country: "Indonesia", lat: -4.3, lon: 122.7, taxa: [ED] },
  { id: "id-s-sulawesi", name: "South Sulawesi", country: "Indonesia", lat: -5.5, lon: 119.35, taxa: [GV, KA] },
  { id: "id-maluku", name: "Maluku", country: "Indonesia", lat: -3.4, lon: 128.4, taxa: [KA] },
  { id: "id-n-java-sea", name: "North Java Sea", country: "Indonesia", lat: -5.6, lon: 110.5, taxa: [KA], note: "Laut Jawa bagian utara" },
  { id: "id-ntb", name: "West Nusa Tenggara", country: "Indonesia", lat: -8.85, lon: 116.9, taxa: [KA] },
].map((l) => ({ concern: "Ice-ice", verification: "pending", ...l }))

/** Country and sea labels drawn on the globe. */
export const PLACE_LABELS = [
  { text: "China", lat: 30, lon: 108 },
  { text: "India", lat: 21, lon: 78 },
  { text: "Myanmar", lat: 21, lon: 95.8 },
  { text: "Thailand", lat: 15.5, lon: 101 },
  { text: "Laos", lat: 19.5, lon: 102.5 },
  { text: "Vietnam", lat: 16, lon: 107.6 },
  { text: "Cambodia", lat: 12.6, lon: 104.9 },
  { text: "Malaysia", lat: 4.2, lon: 102 },
  { text: "Brunei", lat: 4.9, lon: 114.9 },
  { text: "Philippines", lat: 12.2, lon: 122 },
  { text: "Indonesia", lat: -2.3, lon: 113.5 },
  { text: "Timor-Leste", lat: -8.8, lon: 125.9 },
  { text: "Papua New Guinea", lat: -6.3, lon: 144 },
  { text: "Australia", lat: -24, lon: 134 },
  { text: "Taiwan", lat: 23.7, lon: 121 },
  { text: "Japan", lat: 36, lon: 138 },
  { text: "South China Sea", lat: 12.5, lon: 114, sea: true },
  { text: "Java Sea", lat: -4.6, lon: 111.5, sea: true },
  { text: "Celebes Sea", lat: 3.2, lon: 122.3, sea: true },
  { text: "Banda Sea", lat: -5.8, lon: 126.5, sea: true },
  { text: "Indian Ocean", lat: -12, lon: 92, sea: true },
  { text: "Pacific Ocean", lat: 10, lon: 140, sea: true },
]
