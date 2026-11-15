/**
 * The "Thinking" bubble shown while the assistant works. An answer can take 10 to 30 seconds (retrieval, then a
 * model that is free and shared), so the bubble moves (three pulsing dots, see .thinking in dashboard.css) and the
 * words change with time, so nobody wonders whether it has hung.
 */

/** The words for a given number of seconds waited. */
export function thinkingLabel(seconds) {
  if (seconds < 8) return "Thinking"
  if (seconds < 20) return "Still thinking"
  return "Still working. This one is taking a while"
}

export const thinkingHtml = () =>
  `<p class="thinking" role="status" aria-live="polite"><span class="th-label">${thinkingLabel(0)}</span><span class="th-dots" aria-hidden="true"><i></i><i></i><i></i></span></p>`

/**
 * Keeps the label up to date inside `bubble` until the returned function is called.
 * @param {HTMLElement} bubble
 * @returns {() => void} stop
 */
export function startThinking(bubble, now = () => Date.now(), setTimer = setInterval, clearTimer = clearInterval) {
  const t0 = now()
  const timer = setTimer(() => {
    const label = bubble.querySelector(".th-label")
    if (label) label.textContent = thinkingLabel((now() - t0) / 1000)
  }, 1000)
  return () => clearTimer(timer)
}
