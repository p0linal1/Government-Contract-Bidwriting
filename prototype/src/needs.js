import { activeRun, nowDoing } from './agent/session'
import { JOBS, PORTALS } from './data'

export const WORKING = ['researching', 'drafting']

// The stops a bid makes. The sidebar sections and the morning cards both come from this list, so
// they always match. The owner only has to act on bids that are ready for him.
export const CATEGORIES = [
  { id: 'ready', title: 'Ready for you', icon: 'doc', stages: ['ready'], needsYou: true },
  { id: 'drafting', title: 'Drafting', icon: 'agent', stages: ['drafting'] },
  { id: 'researching', title: 'Researching', icon: 'agent', stages: ['researching'] },
  { id: 'new', title: 'To read', icon: 'search', stages: ['new'] },
  { id: 'notcompetitive', title: 'Skipped by the agent', icon: 'close', stages: ['notcompetitive'] },
  { id: 'done', title: 'Done', icon: 'check', stages: ['submitted', 'awarded', 'passed', 'lost'] },
]

export function categorize(state) {
  return CATEGORIES.map((category) => ({
    ...category,
    entries: JOBS.filter((job) => category.stages.includes(state.jobs[job.id].stage)).map((job) => ({ job, progress: state.jobs[job.id] })),
  }))
}

// The line under a bid's name in the list: where it stands, in a few words.
export function shortStatus(job, progress) {
  switch (progress.stage) {
    case 'new':
      return `Found on ${PORTALS[job.source].name}. Read next.`
    case 'ready':
      return 'Drafted. Review and upload.'
    case 'notcompetitive':
      return 'Not competitive. See why.'
    case 'submitted':
      return `Uploaded ${progress.submittedOn}`
    case 'awarded':
      return 'Won'
    case 'lost':
      return 'Not awarded'
    default:
      return 'You passed'
  }
}

// What the agent is doing on a bid this moment, in plain words.
export function liveAction(job, progress) {
  const [run, count] = activeRun(job, progress)
  return nowDoing(run, count)
}

// The next bid that is ready for the owner, other than the one open now.
export function nextReady(state, exceptId) {
  const job = JOBS.find((candidate) => candidate.id !== exceptId && state.jobs[candidate.id].stage === 'ready')
  return job ? { job, progress: state.jobs[job.id] } : null
}
