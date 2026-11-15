/**
 * Ice-ice report locations for the dashboard markers.
 *
 * Source: Alimin et al. (2026), "Reported seaweed diseases in aquaculture: a
 * systematic review", Aquaculture International 34:97, Table 1. The review
 * compiles earlier field studies; each row here is a place where one of those
 * studies reported ice-ice on farmed seaweed. Checked against the paper by the
 * SEAmon team (as stated by Eileen, 15 Nov 2026). See also
 * research/evidence/CANDIDATE_HOST_REGIONS.md.
 *
 * lat/lon are approximate display anchors for the named province/region
 * (placed on nearby water so markers don't sit inland). They are NOT farm
 * or sampling coordinates.
 */

export const SOURCE = {
  short: "Alimin et al. (2026)",
  title: "Reported seaweed diseases in aquaculture: a systematic review",
  journal: "Aquaculture International",
  citation: "Alimin AWF, Kasmiati K, Aswin A, et al. (2026) Reported seaweed diseases in aquaculture: a systematic review. Aquaculture International 34:97",
  url: "https://doi.org/10.1007/s10499-026-02486-2",
  table: "Table 1",
  status: "checked",
}

const KA = "Kappaphycus alvarezii"
const KS = "Kappaphycus striatus"
const KSPP = "Kappaphycus spp."
const ED = "Eucheuma denticulatum"
const GV = "Gracilaria verrucosa"

/** @type {{id:string,name:string,country:string,lat:number,lon:number,taxa:string[],concern:string,verification:"checked"}[]} */
export const LOCATIONS = [
  { id: "ph-pangasinan", dataRegionId: "PH-PANG", name: "Pangasinan", country: "Philippines", lat: 16.2, lon: 119.95, taxa: [KA] },
  { id: "ph-batangas", dataRegionId: "PH-BATANGAS", name: "Batangas", country: "Philippines", lat: 13.6, lon: 121.0, taxa: [KS] },
  { id: "ph-southern-luzon", dataRegionId: "PH-S-LUZON", name: "Southern Luzon", country: "Philippines", lat: 13.2, lon: 123.4, taxa: [KA, KS] },
  { id: "ph-eastern-samar", dataRegionId: "PH-E-SAMAR", name: "Eastern Samar", country: "Philippines", lat: 11.5, lon: 125.65, taxa: [KA] },
  { id: "ph-palawan", dataRegionId: "PH-PALAWAN", name: "Palawan", country: "Philippines", lat: 9.6, lon: 118.95, taxa: [KA, KS] },
  { id: "ph-bohol", dataRegionId: "PH-BOHOL", name: "Bohol", country: "Philippines", lat: 9.6, lon: 124.0, taxa: [ED, KA] },
  { id: "ph-zamboanga", dataRegionId: "PH-ZAMBOANGA", name: "Zamboanga City", country: "Philippines", lat: 6.85, lon: 122.1, taxa: [KS] },
  { id: "ph-davao-norte", dataRegionId: "PH-DAVAO-N", name: "Davao del Norte", country: "Philippines", lat: 7.25, lon: 125.75, taxa: [KS] },
  { id: "ph-tawi-tawi", dataRegionId: "PH-TAWI", name: "Tawi-Tawi", country: "Philippines", lat: 5.05, lon: 119.9, taxa: [ED, KSPP, KA, KS] },
  { id: "my-sabah", dataRegionId: "MY-SABAH", name: "Sabah", country: "Malaysia", lat: 4.6, lon: 118.5, taxa: [KA] },
  { id: "vn-khanh-hoa", dataRegionId: "VN-KHANH-HOA", name: "Khanh Hoa", country: "Vietnam", lat: 12.2, lon: 109.35, taxa: [KS] },
  { id: "id-n-kalimantan", dataRegionId: "ID-N-KAL", name: "North Kalimantan", country: "Indonesia", lat: 3.3, lon: 117.9, taxa: [KA] },
  { id: "id-c-sulawesi", dataRegionId: "ID-CENT-SUL", name: "Central Sulawesi", country: "Indonesia", lat: -1.0, lon: 122.0, taxa: [KA] },
  { id: "id-se-sulawesi", dataRegionId: "ID-SEA-SUL", name: "Southeast Sulawesi", country: "Indonesia", lat: -4.3, lon: 122.7, taxa: [ED] },
  { id: "id-s-sulawesi", dataRegionId: "ID-SOUTH-SUL", name: "South Sulawesi", country: "Indonesia", lat: -5.5, lon: 119.35, taxa: [GV, KA] },
  { id: "id-maluku", dataRegionId: "ID-MALUKU", name: "Maluku", country: "Indonesia", lat: -3.4, lon: 128.4, taxa: [KA] },
  { id: "id-n-java-sea", dataRegionId: "ID-N-JAVA-SEA", name: "North Java Sea", country: "Indonesia", lat: -5.6, lon: 110.5, taxa: [KA], note: "Laut Jawa bagian utara" },
  { id: "id-ntb", dataRegionId: "ID-NTB", name: "West Nusa Tenggara", country: "Indonesia", lat: -8.85, lon: 116.9, taxa: [KA] },
].map((l) => ({ concern: "Ice-ice", verification: "checked", ...l }))

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
