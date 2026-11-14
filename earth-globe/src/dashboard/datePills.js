const MON = new Intl.DateTimeFormat("en", { month: "short" })

/**
 * Yesterday + today + forecast days, Watch-Duty style.
 * @param {HTMLElement} root
 * @param {{daysBefore?:number, daysAfter?:number, onChange?:(d:{date:Date, kind:"history"|"now"|"forecast"})=>void}} opts
 */
export function mountDatePills(root, { daysBefore = 1, daysAfter = 3, onChange } = {}) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = []
  for (let i = -daysBefore; i <= daysAfter; i++) {
    const date = new Date(today)
    date.setDate(today.getDate() + i)
    days.push({ date, kind: i < 0 ? "history" : i === 0 ? "now" : "forecast" })
  }

  let selected = daysBefore
  root.innerHTML = days
    .map(
      (d, i) => `
      <div class="date-pill ${d.kind === "history" ? "past" : ""}">
        <span class="today">${d.kind === "now" ? "Today" : ""}</span>
        <button type="button" data-i="${i}" aria-pressed="${i === selected}"
          aria-label="${d.date.toDateString()}${d.kind === "now" ? ", today" : d.kind === "forecast" ? ", forecast" : ""}">
          <span class="mon">${MON.format(d.date)}</span>
          <span class="day">${d.date.getDate()}</span>
        </button>
      </div>`,
    )
    .join("")

  root.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]")
    if (!b) return
    selected = Number(b.dataset.i)
    for (const x of root.querySelectorAll("button[data-i]")) x.setAttribute("aria-pressed", String(x === b))
    onChange && onChange(days[selected])
  })

  return { get current() { return days[selected] } }
}
