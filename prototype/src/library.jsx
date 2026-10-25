import { createContext, useContext, useEffect, useState } from 'react'

// The real RFP Library, from our server's /api/library and /api/rfp/<id> (server/rfp_library.py).
// The offline click-through has no server, so it never asks, and a library that does not answer
// means the app quietly shows the sample bids. Settings can also pick the sample bids on purpose,
// so the recorded walkthrough still plays.

const LIBRARY_POLL_MS = 30000
const RUNNING_RFP_POLL_MS = 10000
const SAMPLE_KEY = 'cadocary-sample-data'

const fetchJson = (url) =>
  fetch(url)
    .then((reply) => (reply.ok ? reply.json() : null))
    .catch(() => null)

function readSampleChoice() {
  try {
    return localStorage.getItem(SAMPLE_KEY) === 'yes'
  } catch {
    return false
  }
}

function saveSampleChoice(sample) {
  try {
    localStorage.setItem(SAMPLE_KEY, sample ? 'yes' : 'no')
  } catch {
    // Private browsing can block storage. The choice then lasts until the page reloads.
  }
}

// `reach` is 'asking' until the first answer, then 'live' or 'none'. A later failed poll keeps
// the last answer, so a slow moment on the server does not swap the whole app to sample bids.
function useLibraryAnswer() {
  const offline = window.location.protocol === 'file:'
  const [answer, setAnswer] = useState({ reach: offline ? 'none' : 'asking', library: null })

  useEffect(() => {
    if (offline) return
    let stopped = false
    const poll = () =>
      fetchJson('/api/library').then((library) => {
        if (stopped) return
        setAnswer((previous) => (library?.rfps ? { reach: 'live', library } : previous.library ? previous : { reach: 'none', library: null }))
      })
    poll()
    const timer = setInterval(poll, LIBRARY_POLL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [offline])

  return answer
}

const LibraryContext = createContext(null)

export function LibraryProvider({ children }) {
  const { reach, library } = useLibraryAnswer()
  const [sample, setSample] = useState(readSampleChoice)
  const choose = (next) => {
    saveSampleChoice(next)
    setSample(next)
  }
  const live = reach !== 'none' && !sample
  return <LibraryContext.Provider value={{ reach, library, sample, setSample: choose, live }}>{children}</LibraryContext.Provider>
}

export function useLibrary() {
  return useContext(LibraryContext)
}

// One RFP with its findings and newest run. While a run is working on it, it is asked again often.
export function useRfp(id) {
  const [found, setFound] = useState({ state: 'asking', rfp: null })
  const running = found.rfp?.run?.status === 'running'

  useEffect(() => {
    let stopped = false
    const ask = () => fetchJson(`/api/rfp/${id}`).then((rfp) => !stopped && setFound(rfp ? { state: 'found', rfp } : { state: 'missing', rfp: null }))
    ask()
    const timer = running ? setInterval(ask, RUNNING_RFP_POLL_MS) : null
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [id, running])

  return found
}

const isRunning = (rfp) => rfp.run?.status === 'running'

// Each RFP sits in the first group it fits. `mark` borrows the sample bids' list marks.
export const GROUPS = [
  { id: 'working', title: 'Working now', icon: 'agent', mark: 'researching', fits: isRunning },
  { id: 'ready', title: 'Ready for you', icon: 'doc', mark: 'ready', needsYou: true, fits: (rfp) => rfp.status === 'ready_for_doug' },
  { id: 'partway', title: 'Stopped partway', icon: 'agent', mark: 'new', fits: (rfp) => ['qualifying', 'researching', 'drafting'].includes(rfp.status) },
  { id: 'new', title: 'To read', icon: 'search', mark: 'new', folded: true, fits: (rfp) => rfp.status === 'new' },
  { id: 'passed', title: 'Not bidding', icon: 'close', mark: 'passed', fits: (rfp) => rfp.status === 'passed' },
  { id: 'sent', title: 'Sent', icon: 'check', mark: 'submitted', fits: (rfp) => ['sent', 'won', 'lost'].includes(rfp.status) },
]

const byDeadline = (a, b) => (a.deadline ?? '9999').localeCompare(b.deadline ?? '9999')

export function groupRfps(rfps) {
  const groups = GROUPS.map((group) => ({ ...group, rfps: [] }))
  for (const rfp of [...rfps].sort(byDeadline)) groups.find((group) => group.fits(rfp))?.rfps.push(rfp)
  return groups
}

// The agent writes "Pass" for don't bid, which reads to people like passing a test.
export const shownHeadline = (headline) => headline.replace(/^Pass([:.])/, "Don't bid$1")

// The packet's headline starts with the decision and runs several sentences. The list wants one.
export function firstSentence(headline) {
  const text = headline.replace(/^(Pass|Send|Bid|Don't bid)[:.]\s*/, '')
  const sentence = text.match(/^.+?[.!?](?=\s|$)/)?.[0] ?? text
  return sentence.charAt(0).toUpperCase() + sentence.slice(1)
}

// Doug works in Pacific time, so deadlines are shown in it, next to the buyer's own time when the
// deadline was written in another US zone.
const PACIFIC = 'America/Los_Angeles'
const US_ZONES = [
  ['Eastern', 'America/New_York'],
  ['Central', 'America/Chicago'],
  ['Mountain', 'America/Denver'],
  ['Pacific', PACIFIC],
  ['Alaska', 'America/Anchorage'],
  ['Hawaii', 'Pacific/Honolulu'],
]

export const shortDate = (iso) => new Date(iso).toLocaleDateString('en-US', { timeZone: PACIFIC, month: 'short', day: 'numeric' })

const timeIn = (date, zone) => date.toLocaleTimeString('en-US', { timeZone: zone, hour: 'numeric', minute: '2-digit' })

const zoneOffset = (date, zone) =>
  new Intl.DateTimeFormat('en-US', { timeZone: zone, timeZoneName: 'longOffset' }).formatToParts(date).find((part) => part.type === 'timeZoneName')?.value

// The US zone a deadline was written in, from its UTC offset on that date. None for UTC, which
// is how SAM.gov stores most deadlines, so the buyer's own zone is unknown.
function writtenZone(written) {
  const offset = written.match(/([+-]\d\d:\d\d)$/)?.[1]
  if (!offset || offset === '+00:00') return null
  const date = new Date(written)
  return US_ZONES.find(([, zone]) => zoneOffset(date, zone) === `GMT${offset}`) ?? null
}

// "8:00 AM Pacific (11:00 AM Eastern, as written)". `written` is the deadline as the buyer gave it,
// when that is known separately.
export function deadlineTime(iso, written = iso) {
  const pacific = `${timeIn(new Date(iso), PACIFIC)} Pacific`
  const zone = /^\d{4}-\d\d-\d\dT/.test(written) ? writtenZone(written) : null
  return zone && zone[0] !== 'Pacific' ? `${pacific} (${timeIn(new Date(written), zone[1])} ${zone[0]}, as written)` : pacific
}

export const deadlineText = (iso, written) => `${shortDate(iso)}, ${deadlineTime(iso, written)}`

// The day of the month in Pacific time, for the date badges.
export const pacificDay = (iso) => new Date(iso).toLocaleDateString('en-US', { timeZone: PACIFIC, day: 'numeric' })

export const shortTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

export function daysLeftText(days) {
  if (days == null) return 'No deadline given'
  if (days < 0) return 'Closed'
  if (days === 0) return 'Due today'
  return days === 1 ? '1 day left' : `${days} days left`
}

// The line under an RFP's name in the list: what the agent is doing, or where it stands.
// The newest thing an agent said in a run: what it is doing, in its own words.
export function nowLine(run) {
  const said = run?.steps.find((step) => step.text.startsWith(`${step.agent}: `))
  return said ? shownHeadline(said.text.slice(said.agent.length + 2)) : null
}

export function rfpStatusLine(rfp) {
  if (isRunning(rfp)) return `Now: ${nowLine(rfp.run) ?? rfp.run.steps[0]?.text ?? 'the agent is working on it'}`
  if (rfp.status === 'passed' && rfp.headline) return firstSentence(rfp.headline)
  if (rfp.status === 'ready_for_doug') return 'Packet ready. Read it and decide.'
  if (!rfp.deadline) return 'No deadline given'
  return `Due ${deadlineText(rfp.deadline)}. ${daysLeftText(rfp.days_left)}.`
}
