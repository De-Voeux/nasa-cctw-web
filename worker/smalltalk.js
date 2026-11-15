// Greetings, thanks and "what can you do" get a fixed reply, without a model call.
//
// Why not the model: its answers must be backed by sources or data (validateAnswer in
// ask.js), and a greeting has neither, so it used to end in "the sources do not answer
// this". A fixed reply is instant, free, works while the model is rate-limited or not
// configured, and cannot say anything factual. Only a message that is *entirely* one of
// these phrases matches; "hai, which area has the most ice-ice?" still goes to the model.

const ID_WORDS = /\b(hai|halo|selamat|terima|makasih|terimakasih|assalamualaikum|permisi|bantuan|tolong|apa|kamu|anda|siapa|cara|bisa|dapat|kabar)\b/

const GREETING = /^(h+a+i+|h+a+l+o+|h+e+l+l+o+|h+i+|h+e+y+|h+e+i+|yo|selamat (pagi|siang|sore|malam)|good (morning|afternoon|evening)|assalamu ?alaikum( wr wb)?|permisi|apa kabar|how are you)( (there|all|semua|kak|min|admin|bot|seamon))?$/
const THANKS = /^(terima ?kasih( banyak)?|makasih( banyak)?|thanks?( a lot| so much)?|thank you( so much)?|thx|tq)( (ya|yaa|kak|min))?$/
const HELP = /^(help( me)?|bantuan|tolong|what (can|could) (you|i) (do|ask|help)( with)?( you| me)?|what (do|can) you (do|help with)|what are you( for)?|how (can|do) you help( me)?|can you help( me)?|apa (yang )?(bisa|dapat) (kamu|anda) (lakukan|bantu)|(kamu|anda) bisa apa|bisa apa( saja)?|apa saja yang bisa ditanyakan|boleh tanya apa|who are you|kamu siapa|siapa (kamu|anda)|cara (pakai|menggunakan)( ini)?|how (do i|to) use( this)?)$/
// A greeting in front of one of the phrases above ("hi, what can you do?") is just a greeting; it is cut off first.
const LEAD = /^((h+a+i+|h+a+l+o+|h+e+l+l+o+|h+i+|h+e+y+|h+e+i+|selamat (pagi|siang|sore|malam)|good (morning|afternoon|evening)|permisi|assalamu ?alaikum( wr wb)?)( (there|all|semua|kak|min|admin|bot|seamon))? )+/

const REPLIES = {
  id: {
    greeting:
      "Hai! Saya asisten SEAmon. Tanyakan soal penyakit ice-ice pada rumput laut atau data lingkungan di lokasi yang dipantau, misalnya suhu laut di Maluku. Saya hanya menjawab dari sumber terverifikasi dan data pemantauan; kalau buktinya belum ada, saya akan bilang begitu.",
    thanks: "Sama-sama! Tanyakan saja kalau ada yang ingin diketahui lagi.",
    help:
      "Saya asisten SEAmon. Saya bisa:\n\n- Menjawab pertanyaan tentang ice-ice dari sumber yang sudah diverifikasi (jumlahnya masih sedikit).\n- Menampilkan data lingkungan per lokasi, misalnya suhu laut harian di Maluku.\n\nJawaban selalu mencantumkan sumber atau data yang dipakai. Kalau tidak ada buktinya, saya akan bilang tidak tahu, bukan menebak.",
  },
  en: {
    greeting:
      "Hi! I'm the SEAmon assistant. Ask about ice-ice disease in seaweed or about environmental data at the monitored sites, for example sea temperature at Maluku. I answer only from verified sources and monitoring data; when there is no evidence I will say so.",
    thanks: "You're welcome! Ask anything else any time.",
    help:
      "I'm the SEAmon assistant. I can:\n\n- Answer questions about ice-ice from verified sources (there are still few).\n- Show environmental data per site, for example daily sea temperature at Maluku.\n\nAnswers always show the sources or data they used. If there is no evidence I will say I don't know instead of guessing.",
  },
}

const normalize = (q) =>
  String(q)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim()

/** @returns {string | null} the Markdown reply, or null when the message is a real question */
export function smalltalkReply(question) {
  const q = normalize(question)
  if (!q || q.length > 80) return null
  // "hi, what can you do?": decide on what follows the greeting (nothing left = just a greeting)
  const rest = q.replace(LEAD, "")
  const kind = GREETING.test(q) ? "greeting" : THANKS.test(rest) ? "thanks" : HELP.test(rest) ? "help" : rest === "" ? "greeting" : GREETING.test(rest) ? "greeting" : null
  if (!kind) return null
  return REPLIES[ID_WORDS.test(q) ? "id" : "en"][kind]
}
