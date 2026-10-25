import { sections } from './bid'
import { PORTALS } from './data'
import { getResearch } from './research'

// Plain explanations shown on hover. Each one says what a thing means and why it is there.

export const PHASE_HINTS = {
  Find: 'The agent finds bids in your range on the bid websites and in the bid inbox.',
  Research: 'It reads every page, checks Cadocary against each requirement, and decides whether Cadocary is competitive.',
  Draft: 'If Cadocary is competitive, it drafts the whole proposal on its own.',
  Review: 'You read the finished bid, then upload it or pass. This is the only step that needs you.',
}

export const COVERAGE_HINTS = {
  Built: "One of Cadocary's products already does this today.",
  'Partly built': 'Most of it exists. The hours to finish it are already in the cost estimate.',
  'Not built': 'Cadocary would have to build this from scratch.',
}

export const REASON_HINTS = {
  'Not software work': 'Cadocary only bids on software and IT work.',
  'Under $25,000': 'Bids this small rarely cover the cost of writing a proposal.',
  'Outside Washington': 'Cadocary only bids on work in Washington.',
  'Closes in under 7 days': 'Too little time to research it and write a strong proposal.',
}

// Why a bid sits where it does in the list.
export function statusHint(job, progress) {
  const research = getResearch(job)
  switch (progress.stage) {
    case 'new':
      return `Found on ${PORTALS[job.source].name} on ${research.sources.rfp.date}. The agent researches it as soon as it finishes the bids ahead of it.`
    case 'researching':
      return `The agent is researching this now, step ${Math.min(progress.researchStep + 1, research.log.length)} of ${research.log.length}. Open it to watch.`
    case 'drafting':
      return 'Cadocary is competitive for this one, so the agent is writing the proposal now. Open it to watch.'
    case 'ready':
      return `Researched and drafted: ${sections(job).length} sections, with the reasons Cadocary is competitive. Read it, then upload it or pass.`
    case 'notcompetitive':
      return `The agent researched this and skipped it: ${progress.reason} You can still have it drafted.`
    case 'submitted':
      return `Uploaded ${progress.submittedOn}. The buyer expects to decide by ${progress.decisionBy}.`
    case 'awarded':
      return 'The buyer awarded the contract to Cadocary.'
    case 'lost':
      return 'The buyer chose another firm.'
    default:
      return 'You passed on this bid.'
  }
}

// A deadline as a short brief: what happens that day, where this bid stands, and whether the owner
// needs to do anything before it. Until a bid is ready, the agent handles everything.
export function deadlineBrief(job, progress, label) {
  const research = getResearch(job)
  const count = research.questions.list.length
  const questions = `${count} ${count === 1 ? 'question' : 'questions'}`
  const stands = statusHint(job, progress)
  const yours = progress.stage === 'ready' ? 'Review the bid and upload it.' : 'Nothing. The agent is handling it.'

  switch (label) {
    case 'Questions due':
      return {
        happens: 'The last day to send the buyer written questions. After this they will not answer any.',
        stands: progress.questionsSent ? `The agent sent ${questions}.` : 'The agent writes and sends questions during research.',
        todo: 'Nothing. The agent reads the answers when they are posted.',
      }
    case 'Proposals due':
      return { happens: 'The proposal must be in by this time. Late proposals are not accepted.', stands, todo: yours }
    case 'Answers posted':
      return {
        happens: "The buyer posts answers to every firm's questions, so everyone bids on the same facts.",
        stands,
        todo: 'Nothing. The agent reads the answers and updates the bid.',
      }
    case 'Interviews':
    case 'Demonstrations':
      return { happens: 'If the buyer shortlists Cadocary, you present on these days.', stands, todo: 'Keep these days open.' }
    default:
      return { happens: `${label}.`, stands, todo: yours }
  }
}

// What a source chip opens.
export function citeHint(doc, cite) {
  if (!doc) return null
  const where = doc.pages > 1 ? `, page ${cite.page}` : ''
  return cite.quote ? `Opens ${doc.title}${where}, with the line it came from highlighted.` : `Opens ${doc.title}${where}.`
}
