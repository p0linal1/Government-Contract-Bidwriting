import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { navigate } from './router'
import { TOUR_STEPS } from './tourSteps'
import { Icon } from './ui'

// The guided walkthrough: it dims the page, lights the part a step talks about, and puts a short
// card beside it. Phones dock the card at the bottom, where it does not cover a narrow target.

// Long enough for an RFP to arrive from the server before the card gives up and sits in the middle.
const FIND_TIMEOUT_MS = 3000
const FIND_EVERY_MS = 100
const SPOT_PAD = 8
const CARD_GAP = 14
const EDGE = 12
const PHONE = '(max-width: 959px)'

// `?tour=3` opens the walkthrough at step 3, for links and screenshots of one step.
export function tourStepInAddress() {
  const step = Number(new URLSearchParams(window.location.search).get('tour'))
  return Number.isInteger(step) && step >= 1 && step <= TOUR_STEPS.length ? step - 1 : null
}

// Some parts render twice, once for laptops and once for phones, with CSS hiding one of them.
function findVisible(selector) {
  return [...document.querySelectorAll(selector)].find((element) => element.getClientRects().length > 0) ?? null
}

// Opens a fold or a panel without closing one that is already open.
function reveal(element) {
  if (element.tagName === 'DETAILS') element.open = true
  else if (element.getAttribute('aria-expanded') !== 'true') element.click()
}

const clamp = (value, low, high) => Math.max(low, Math.min(value, high))

function spotBox(element) {
  const rect = element.getBoundingClientRect()
  const top = clamp(rect.top - SPOT_PAD, 4, window.innerHeight - 4)
  const left = clamp(rect.left - SPOT_PAD, 4, window.innerWidth - 4)
  const bottom = clamp(rect.bottom + SPOT_PAD, top, window.innerHeight - 4)
  const right = clamp(rect.right + SPOT_PAD, left, window.innerWidth - 4)
  return { top, left, bottom, right }
}

const sameBox = (a, b) => a.top === b.top && a.left === b.left && a.bottom === b.bottom && a.right === b.right

// Follows the target as the page scrolls, loads, or animates. A target that React replaced is found again.
function useSpot(element, selector) {
  const [box, setBox] = useState(null)

  useEffect(() => {
    setBox(null)
    if (!element) return
    let current = element
    let frame
    const measure = () => {
      if (!current.isConnected) current = findVisible(selector) ?? current
      const next = spotBox(current)
      setBox((previous) => (previous && sameBox(previous, next) ? previous : next))
      frame = requestAnimationFrame(measure)
    }
    measure()
    return () => cancelAnimationFrame(frame)
  }, [element, selector])

  return box
}

// Beside the target where there is room: right, below, above, then left. Otherwise the corner.
function placeCard(box, size) {
  const width = window.innerWidth
  const height = window.innerHeight
  const top = (value) => clamp(value, EDGE, height - size.height - EDGE)
  const left = (value) => clamp(value, EDGE, width - size.width - EDGE)
  if (width - box.right >= size.width + CARD_GAP + EDGE) return { top: top(box.top), left: box.right + CARD_GAP }
  if (height - box.bottom >= size.height + CARD_GAP + EDGE) return { top: box.bottom + CARD_GAP, left: left(box.left) }
  if (box.top >= size.height + CARD_GAP + EDGE) return { top: box.top - CARD_GAP - size.height, left: left(box.left) }
  if (box.left >= size.width + CARD_GAP + EDGE) return { top: top(box.top), left: box.left - CARD_GAP - size.width }
  return { top: height - size.height - EDGE * 2, left: width - size.width - EDGE * 2 }
}

export function Tour({ index, onGo, onClose }) {
  const step = TOUR_STEPS[index]
  const last = index === TOUR_STEPS.length - 1
  const [found, setFound] = useState({ index: null, element: null })
  const [size, setSize] = useState({ width: 340, height: 200 })
  const card = useRef(null)
  const nextButton = useRef(null)
  const ready = found.index === index
  const box = useSpot(ready ? found.element : null, step.target)

  useEffect(() => {
    const moved = step.route && window.location.hash !== `#${step.route}`
    if (moved) navigate(step.route)
    const started = Date.now()
    let opened = !step.open
    let timer
    const look = () => {
      if (!opened) {
        const toggle = findVisible(step.open)
        if (toggle) reveal(toggle)
        opened = Boolean(toggle)
      }
      const element = opened && step.target ? findVisible(step.target) : null
      if (element || !step.target || Date.now() - started > FIND_TIMEOUT_MS) {
        element?.scrollIntoView({ block: 'center' })
        setFound({ index, element })
        return
      }
      timer = setTimeout(look, FIND_EVERY_MS)
    }
    // After a route change the old screen is still up for a moment, and it can hold a part with the same name.
    timer = setTimeout(look, moved ? FIND_EVERY_MS : 0)
    return () => clearTimeout(timer)
  }, [index, step])

  useLayoutEffect(() => {
    if (!card.current) return
    const { offsetWidth: width, offsetHeight: height } = card.current
    if (width !== size.width || height !== size.height) setSize({ width, height })
  })

  useEffect(() => {
    if (ready) nextButton.current?.focus({ preventScroll: true })
  }, [ready, index])

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'ArrowRight' && !last) onGo(index + 1)
      if (event.key === 'ArrowLeft' && index > 0) onGo(index - 1)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [index, last, onGo, onClose])

  const docked = box && window.matchMedia(PHONE).matches
  const placement = box ? (docked ? 'is-docked' : '') : 'is-centered'
  // A found target is measured one render later. Waiting for it keeps the card from flashing in the middle.
  const shown = ready && (box || !found.element)
  return (
    <div className="tour">
      <div className={`tour-block ${box ? '' : 'is-dim'}`} />
      {box && <div className="tour-spot" style={{ top: box.top, left: box.left, width: box.right - box.left, height: box.bottom - box.top }} />}
      {shown && (
        <section ref={card} className={`tour-card ${placement}`} style={box && !docked ? placeCard(box, size) : undefined} role="dialog" aria-modal="true" aria-labelledby="tour-title" aria-describedby="tour-text">
          <div className="tour-card-head">
            <p className="tour-count">
              Step {index + 1} of {TOUR_STEPS.length}
            </p>
            <button className="icon-button" aria-label="Close walkthrough" onClick={onClose}>
              <Icon name="close" size={16} stroke={2.2} />
            </button>
          </div>
          <h2 id="tour-title" className="tour-title">
            {step.title}
          </h2>
          <p id="tour-text" className="tour-text">
            {step.text}
          </p>
          <div className="tour-actions">
            <button className="btn btn-secondary" disabled={index === 0} onClick={() => onGo(index - 1)}>
              Back
            </button>
            <button ref={nextButton} className="btn btn-primary" onClick={last ? onClose : () => onGo(index + 1)}>
              {last ? 'Done' : 'Next'}
            </button>
          </div>
        </section>
      )}
    </div>
  )
}
