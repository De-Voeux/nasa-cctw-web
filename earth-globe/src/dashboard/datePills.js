const MON = new Intl.DateTimeFormat("en", { month: "short" })
const MONTH_YEAR = new Intl.DateTimeFormat("en", { month: "long", year: "numeric" })
const SHORT = new Intl.DateTimeFormat("en", { day: "numeric", month: "short" })
const LONG = new Intl.DateTimeFormat("en", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"]
const DAY = 86400000

const midnight = (d) => {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}
const addDays = (d, n) => {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}
const sameDay = (a, b) => a.getTime() === b.getTime()

const calendarIcon = `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg>`
const chevron = (dir) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${dir === "prev" ? "m15 18-6-6 6-6" : "m9 18 6-6-6-6"}"/></svg>`

/**
 * Date bar: five day buttons around the chosen day, and a calendar button that
 * opens a month calendar for the last three months (plus the forecast days).
 * The chosen day sets the map's colour layer, the five buttons and the values in
 * the panel. How many days the charts show is set in the panel (sidePanel.js).
 *
 * @param {HTMLElement} bar  the date bar (nav)
 * @param {{
 *   forecastDays?: number,
 *   monthsBack?: number,
 *   onChange?: (d:{date:Date, kind:"history"|"now"|"forecast"}) => void,
 * }} opts
 */
export function mountDatePills(bar, { forecastDays = 3, monthsBack = 3, onChange } = {}) {
  const today = midnight(new Date())
  const minDate = (() => {
    const d = new Date(today)
    d.setMonth(d.getMonth() - monthsBack)
    return d
  })()
  const maxDate = addDays(today, forecastDays)
  const kindOf = (d) => (d < today ? "history" : sameDay(d, today) ? "now" : "forecast")
  const inRange = (d) => d >= minDate && d <= maxDate

  let selected = today
  let view = new Date(today.getFullYear(), today.getMonth(), 1) // month shown in the calendar
  let focusDay = today // day that gets keyboard focus in the calendar

  bar.innerHTML = `
    <div class="date-pills" role="group" aria-label="Day"></div>
    <span class="date-sep" aria-hidden="true"></span>
    <div class="cal-slot">
      <span class="today cal-label" aria-hidden="true"></span>
      <button type="button" class="cal-btn" aria-label="Pick a date" aria-haspopup="dialog" aria-expanded="false">${calendarIcon}</button>
    </div>`
  const pills = bar.querySelector(".date-pills")
  const calBtn = bar.querySelector(".cal-btn")
  // The calendar lives on <body>, not in the bar: a blurred panel inside the bar's own
  // blur doesn't render its blur in Chrome, so the map would show through it.
  const pop = document.createElement("div")
  pop.className = "glass cal-pop"
  pop.setAttribute("role", "dialog")
  pop.setAttribute("aria-label", "Pick a date")
  pop.hidden = true
  document.body.append(pop)

  /** Under the bar, right edges aligned, kept on screen. */
  function place() {
    const r = bar.getBoundingClientRect()
    const w = pop.offsetWidth
    const left = Math.max(12, Math.min(r.right - w, innerWidth - w - 12))
    pop.style.top = `${Math.round(r.bottom + 10)}px`
    pop.style.left = `${Math.round(left)}px`
  }
  addEventListener("resize", () => !pop.hidden && place())

  // ---------------------------------------------------------------- five day buttons

  /** First of the five days: yesterday while the chosen day is near today, else centred on it. */
  function windowStart() {
    const def = addDays(today, -1)
    if (selected >= def && selected <= addDays(def, 4)) return def
    let start = addDays(selected, -2)
    if (addDays(start, 4) > maxDate) start = addDays(maxDate, -4)
    if (start < minDate) start = minDate
    return start
  }

  function renderPills() {
    const start = windowStart()
    pills.innerHTML = Array.from({ length: 5 }, (_, i) => {
      const d = addDays(start, i)
      const kind = kindOf(d)
      return `
      <div class="date-pill ${kind === "history" ? "past" : ""}">
        <span class="today">${kind === "now" ? "Today" : ""}</span>
        <button type="button" data-day="${d.getTime()}" aria-pressed="${sameDay(d, selected)}"
          aria-label="${LONG.format(d)}${kind === "now" ? ", today" : kind === "forecast" ? ", forecast" : ""}">
          <span class="mon">${MON.format(d)}</span>
          <span class="day">${d.getDate()}</span>
        </button>
      </div>`
    }).join("")
  }

  pills.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-day]")
    if (b) select(new Date(Number(b.dataset.day)))
  })

  // ---------------------------------------------------------------- calendar

  function renderCalendar() {
    const y = view.getFullYear()
    const m = view.getMonth()
    const first = new Date(y, m, 1)
    const days = new Date(y, m + 1, 0).getDate()
    const prevOk = new Date(y, m, 0) >= minDate
    const nextOk = new Date(y, m + 1, 1) <= maxDate

    const blanks = Array.from({ length: first.getDay() }, () => `<span class="cal-blank"></span>`).join("")
    const cells = Array.from({ length: days }, (_, i) => {
      const d = new Date(y, m, i + 1)
      const ok = inRange(d)
      const kind = kindOf(d)
      const cls = ["cal-day", kind === "forecast" ? "is-forecast" : "", sameDay(d, today) ? "is-today" : ""].join(" ")
      return `<button type="button" class="${cls}" data-day="${d.getTime()}" ${ok ? "" : "disabled"}
        tabindex="${sameDay(d, focusDay) ? 0 : -1}" aria-pressed="${sameDay(d, selected)}"
        ${sameDay(d, today) ? 'aria-current="date"' : ""}
        aria-label="${LONG.format(d)}${kind === "forecast" ? ", forecast" : ""}${ok ? "" : ", no data"}">${i + 1}</button>`
    }).join("")

    pop.innerHTML = `
      <div class="cal-head">
        <button type="button" class="cal-nav" data-step="-1" aria-label="Previous month" ${prevOk ? "" : "disabled"}>${chevron("prev")}</button>
        <h2 class="cal-title" aria-live="polite">${MONTH_YEAR.format(view)}</h2>
        <button type="button" class="cal-nav" data-step="1" aria-label="Next month" ${nextOk ? "" : "disabled"}>${chevron("next")}</button>
      </div>
      <div class="cal-grid">
        ${WEEKDAYS.map((w) => `<span class="cal-wd" aria-hidden="true">${w}</span>`).join("")}
        ${blanks}${cells}
      </div>
      <p class="cal-note">Data from ${SHORT.format(minDate)} to ${SHORT.format(maxDate)}. <span class="cal-key"></span>Days after today are forecasts.</p>
      <button type="button" class="cal-today-btn" ${sameDay(selected, today) ? "disabled" : ""}>Back to today</button>`
  }

  function focusCalendarDay() {
    const b = pop.querySelector(`.cal-day[data-day="${focusDay.getTime()}"]`)
    if (b) b.focus()
  }

  function moveFocus(d) {
    if (d < minDate) d = minDate
    if (d > maxDate) d = maxDate
    focusDay = d
    if (d.getMonth() !== view.getMonth() || d.getFullYear() !== view.getFullYear()) {
      view = new Date(d.getFullYear(), d.getMonth(), 1)
    }
    renderCalendar()
    focusCalendarDay()
  }

  function setOpen(open) {
    pop.hidden = !open
    calBtn.setAttribute("aria-expanded", String(open))
    if (open) {
      focusDay = selected
      view = new Date(selected.getFullYear(), selected.getMonth(), 1)
      renderCalendar()
      place()
      focusCalendarDay()
    }
  }

  calBtn.addEventListener("click", () => setOpen(pop.hidden))

  pop.addEventListener("click", (e) => {
    const day = e.target.closest(".cal-day")
    if (day && !day.disabled) {
      select(new Date(Number(day.dataset.day)))
      setOpen(false)
      calBtn.focus()
      return
    }
    const nav = e.target.closest(".cal-nav")
    if (nav && !nav.disabled) {
      view = new Date(view.getFullYear(), view.getMonth() + Number(nav.dataset.step), 1)
      // Keep one day of the shown month reachable with Tab: the chosen day, else the first day with data.
      const inView = (d) => d.getMonth() === view.getMonth() && d.getFullYear() === view.getFullYear()
      const firstOk = Array.from({ length: 31 }, (_, i) => new Date(view.getFullYear(), view.getMonth(), i + 1))
        .filter(inView)
        .find(inRange)
      if (!inView(focusDay)) focusDay = inView(selected) ? selected : firstOk || focusDay
      renderCalendar()
      pop.querySelector(`.cal-nav[data-step="${nav.dataset.step}"]`)?.focus()
      return
    }
    if (e.target.closest(".cal-today-btn")) {
      select(today)
      setOpen(false)
      calBtn.focus()
    }
  })

  pop.addEventListener("keydown", (e) => {
    const day = e.target.closest(".cal-day")
    if (!day) return
    const steps = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }
    if (e.key in steps) {
      e.preventDefault()
      moveFocus(addDays(focusDay, steps[e.key]))
    } else if (e.key === "PageUp" || e.key === "PageDown") {
      e.preventDefault()
      const d = new Date(focusDay)
      d.setMonth(d.getMonth() + (e.key === "PageUp" ? -1 : 1))
      moveFocus(d)
    }
  })

  document.addEventListener("click", (e) => {
    // composedPath, not contains: month buttons are redrawn on click, so the target is gone by now.
    const path = e.composedPath()
    if (!pop.hidden && !path.includes(pop) && !path.includes(calBtn)) setOpen(false)
  })
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !pop.hidden) {
      setOpen(false)
      calBtn.focus()
    }
  })

  // ---------------------------------------------------------------- state

  function select(d) {
    d = midnight(d)
    if (!inRange(d)) return
    selected = d
    renderPills()
    onChange && onChange(current())
  }

  const current = () => ({ date: selected, kind: kindOf(selected) })

  renderPills()

  return {
    get current() {
      return current()
    },
  }
}
