/**
 * Photos of the seaweeds named on the map, shown in a place's detail panel.
 *
 * All from Wikimedia Commons under Creative Commons licences that require the
 * photographer's name and the licence next to the photo (done in sidePanel.js).
 * Files in assets/species/ are the Commons images resized to 480 px wide; nothing
 * else was changed. Picked on 15 Nov 2026.
 *
 * Kappaphycus striatus has no free-licence photo on Commons, and "Kappaphycus spp."
 * is the genus, not one species, so neither gets a photo: a photo of another
 * species would show the wrong seaweed.
 */
import kappaphycusAlvarezii from "../assets/species/kappaphycus-alvarezii.jpg"
import eucheumaDenticulatum from "../assets/species/eucheuma-denticulatum.jpg"
import gracilariaVerrucosa from "../assets/species/gracilaria-verrucosa.jpg"

/** @type {Record<string, {src:string, alt:string, author:string, license:string, licenseUrl:string, page:string}>} */
export const SPECIES_PHOTOS = {
  "Kappaphycus alvarezii": {
    src: kappaphycusAlvarezii,
    alt: "A handful of orange, branching Kappaphycus alvarezii",
    author: "Md. Simul Bhuyan",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0/",
    page: "https://commons.wikimedia.org/wiki/File:Kappaphycus_alvarezii_in_the_St._Martin%27s_Island.jpg",
  },
  "Eucheuma denticulatum": {
    src: eucheumaDenticulatum,
    alt: "Green Eucheuma denticulatum growing on a farm line in shallow water",
    author: "StinaTano",
    license: "CC BY-SA 3.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/3.0/",
    page: "https://commons.wikimedia.org/wiki/File:Eucheuma_denticulatum_in_an_off-bottom_cultivation,_Bweleo,_Zanzibar.JPG",
  },
  "Gracilaria verrucosa": {
    src: gracilariaVerrucosa,
    alt: "Thin, dark Gracilaria verrucosa underwater on sand",
    author: "Ecomare/Oscar Bos",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0/",
    page: "https://commons.wikimedia.org/wiki/File:Ecomare_-_knoopwier_(knoopwier-2133-ogb).jpg",
  },
}
