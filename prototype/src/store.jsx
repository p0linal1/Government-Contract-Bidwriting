import { createContext, useContext, useEffect, useReducer } from 'react'
import { draftRun, eventsBeforeStep, isVisible, researchRun, stepsDone } from './agent/session'
import { assess } from './bid/assess'
import { JOBS, JOBS_BY_ID, money } from './data'
import { getResearch } from './research'

const STORAGE_KEY = 'cadocary-demo-v11'
const AGENT_TICK_MS = 700

// The calls the agent makes on its own once research is done: its pick where the files left one
// open, the suggested price, and sending its questions to the buyer.
function agentCalls(job) {
  return { answer: job.question?.agentPick ?? null, price: money(job.price), questionsSent: true }
}

function startingProgress(job) {
  const { start } = job
  const research = researchRun(job)
  const draft = draftRun(job)
  const researched = !['new', 'researching'].includes(start.stage)
  return {
    stage: start.stage,
    researchStep: researched ? getResearch(job).log.length : (start.researchStep ?? 0),
    eventCount: researched ? research.events.length : eventsBeforeStep(research, start.researchStep ?? 0),
    draftCount: start.stage === 'drafting' ? eventsBeforeStep(draft, start.draftStep ?? 0) : researched ? draft.events.length : 0,
    revised: {},
    reason: start.stage === 'notcompetitive' ? assess(job).reason : null,
    submittedOn: start.submittedOn ?? null,
    decisionBy: start.decisionBy ?? null,
    ...(researched ? agentCalls(job) : { answer: null, price: null, questionsSent: false }),
    ...(start.price ? { price: start.price } : {}),
  }
}

function initialState() {
  return {
    jobs: Object.fromEntries(JOBS.map((job) => [job.id, startingProgress(job)])),
    toasts: [],
    nextToastId: 1,
  }
}

function withJob(state, id, changes) {
  return { ...state, jobs: { ...state.jobs, [id]: { ...state.jobs[id], ...changes } } }
}

function notify(state, text, to) {
  const id = state.nextToastId
  return { ...state, nextToastId: id + 1, toasts: [{ id, text, to }] }
}

// Emits events up to and including the next one a person would notice. Bookkeeping events
// (timing spans, usage) ride along with it.
function nextVisible(run, count) {
  let next = count
  do {
    next += 1
  } while (next < run.events.length && !isVisible(run.events[next - 1]))
  return next
}

// Plays the agent's research forward by one step a person would notice. When research ends, the
// agent makes its calls and either drafts the bid or skips it, with the reason.
function advanceResearch(state, id) {
  const job = JOBS_BY_ID[id]
  const run = researchRun(job)
  const count = nextVisible(run, state.jobs[id].eventCount)
  const changes = { eventCount: count, researchStep: stepsDone(run, count) }
  if (count < run.events.length) return withJob(state, id, changes)

  const verdict = assess(job)
  const done = { ...changes, ...agentCalls(job) }
  if (verdict.competitive) {
    return notify(withJob(state, id, { ...done, stage: 'drafting', draftCount: 0 }), `${job.buyer}: Cadocary is competitive, so the agent is drafting the bid.`, `/bids/${id}`)
  }
  return notify(withJob(state, id, { ...done, stage: 'notcompetitive', reason: verdict.reason }), `${job.buyer}: skipped. ${verdict.reason}`, `/bids/${id}`)
}

// Plays the agent's proposal draft forward the same way. A finished draft goes to the owner.
function advanceDraft(state, id) {
  const job = JOBS_BY_ID[id]
  const run = draftRun(job)
  const count = nextVisible(run, state.jobs[id].draftCount)
  if (count >= run.events.length) {
    return notify(withJob(state, id, { draftCount: count, stage: 'ready' }), `${job.buyer}: the bid is drafted and ready for your review.`, `/bids/${id}`)
  }
  return withJob(state, id, { draftCount: count })
}

// The agent works on a few bids at once. When one finishes research, it starts the next bid in line.
const AT_ONCE = 2

function startNext(state) {
  const busy = JOBS.filter((job) => state.jobs[job.id].stage === 'researching').length
  const next = JOBS.find((job) => state.jobs[job.id].stage === 'new')
  if (busy >= AT_ONCE || !next) return state
  return withJob(state, next.id, { stage: 'researching', researchStep: 0, eventCount: 0 })
}

function reducer(state, action) {
  const job = JOBS_BY_ID[action.id]
  switch (action.type) {
    case 'tick':
      return Object.keys(state.jobs).reduce((next, id) => {
        if (next.jobs[id].stage === 'researching') return advanceResearch(next, id)
        if (next.jobs[id].stage === 'drafting') return advanceDraft(next, id)
        return next
      }, startNext(state))
    case 'draftAnyway':
      return withJob(state, action.id, { stage: 'drafting', draftCount: 0, reason: null })
    case 'revise':
      return withJob(state, action.id, { revised: { ...state.jobs[action.id].revised, [action.section]: true } })
    case 'upload':
      return notify(
        withJob(state, action.id, { stage: 'submitted', submittedOn: 'Oct 26', decisionBy: 'Dec 15' }),
        `${job.buyer}: marked as uploaded. The agent will watch for the award.`,
        `/bids/${action.id}`,
      )
    case 'pass':
      return withJob(state, action.id, { stage: 'passed' })
    case 'reconsider':
      return withJob(state, action.id, { stage: 'ready' })
    case 'award':
      return notify(withJob(state, action.id, { stage: 'awarded' }), `${job.buyer} awarded the contract to Cadocary.`, `/bids/${action.id}`)
    case 'lose':
      return withJob(state, action.id, { stage: 'lost' })
    case 'dismissToast':
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.toastId) }
    case 'reset':
      return initialState()
    default:
      throw new Error(`Unknown action: ${action.type}`)
  }
}

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY))
    return saved ? { ...saved, toasts: [] } : initialState()
  } catch {
    return initialState()
  }
}

const StoreContext = createContext(null)

export function StoreProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, undefined, loadState)

  useEffect(() => {
    const timer = setInterval(() => dispatch({ type: 'tick' }), AGENT_TICK_MS)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch {
      // Private browsing can block storage. The demo still works, it just forgets on reload.
    }
  }, [state])

  return <StoreContext.Provider value={{ state, dispatch }}>{children}</StoreContext.Provider>
}

export function useStore() {
  return useContext(StoreContext)
}
