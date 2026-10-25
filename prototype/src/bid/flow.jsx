import { reviewItems, sections, totalPages } from '../bid'
import { PORTALS, RATE, money } from '../data'
import { draftRun, researchRun } from '../agent/session'
import { eligibilityStatus, getResearch, researchProgress, tally } from '../research'
import { postingCite } from '../research/postings'
import { agentPick, assess } from './assess'
import { ProposalPage } from './Proposal'
import { AgentSession } from './Session'

export const PHASES = ['Find', 'Research', 'Draft', 'Review']

// The format rules checked before upload. Price, references, and the deadline are the agent's calls, listed with their reasons.
const FORMAT_CHECKS = ['Length', 'Font', 'Forms']

const margin = (price, cost) => Math.round(((price - cost) / price) * 100)
const plural = (count, one, many = `${one}s`) => `${count} ${count === 1 ? one : many}`

const SOURCE_HELP = { q: 'Where does each line come from?', a: 'The chip next to a line opens the page it came from, with the passage highlighted.' }
const LIVE_HELP = [
  { q: 'Do I need to stay here?', a: 'No. The agent keeps going on its own. The bid moves to Ready for you when the draft is done.' },
  { q: 'What are raw events?', a: 'The exact messages the agent sends while it works: each search, page, file, and note. Plain English is the same list, translated.' },
]

// The facts behind the agent's verdict, each with its source.
function verdictRows(job, research, progress) {
  const numbers = tally(research)
  const built = research.requirements.find((r) => r.coverage === 'meets' && r.evidenceCite)
  const budget = research.overview.find((row) => row.label === 'Budget')
  const competitors = research.competition.count ?? research.competition.planholders.length
  const gaps = research.eligibility.filter((row) => eligibilityStatus(row, progress, job) !== 'pass')
  return [
    { label: 'Why Cadocary', value: job.why },
    { label: 'Estimated value', value: budget?.value ?? money(job.value), cite: budget?.cite ?? research.pricing.budget.cite, quote: true },
    { label: 'Already built', value: `${numbers.coverage.meets} of ${numbers.requirements} requirements`, detail: `${numbers.coverage.partial} partly built, ${numbers.coverage.gap} not built`, cite: built?.evidenceCite },
    { label: 'Eligibility', value: gaps.length ? `${plural(gaps.length, 'rule')} to fix before signing` : 'Meets every rule', detail: gaps.map((g) => g.item).join(', ') || null, tone: gaps.length ? 'warn' : 'good' },
    competitors
      ? { label: 'Other bidders', value: `${competitors - 1} firms have the documents`, cite: research.competition.cite }
      : { label: 'Other bidders', value: 'Not published', detail: research.competition.read },
    { label: 'Estimated score', value: `${numbers.score} of 100`, cite: research.scoring.cite },
  ]
}

// The calls the agent made on its own, each with the reason and the source behind it.
function decisionRows(job, research, progress) {
  const numbers = tally(research)
  const pick = agentPick(job)
  const references = research.eligibility.find((row) => row.status === 'answer')
  const due = research.dates.find((d) => d.unconfirmed)
  const price = progress.price ?? money(job.price)
  return [
    { label: 'Price', value: price, detail: `${margin(job.price, numbers.cost)}% margin over ${money(numbers.cost)} of work at $${RATE} an hour, inside the ${money(job.value)} budget.`, cite: research.pricing.budget.cite },
    pick && { label: job.question.label, value: pick.label.replace(/^Use | instead$/g, ''), detail: job.question.agentReason, cite: references?.cite },
    { label: 'Questions to the buyer', value: `Sent ${plural(research.questions.list.length, 'question')}`, detail: research.questions.list[0].text, cite: research.questions.list[0].cite },
    due && { label: 'Deadline', value: job.due, detail: 'Checked against the latest addendum, which reissued the schedule.', cite: due.cite },
  ].filter(Boolean)
}

// A bid is a run of screens built from saved progress. The agent's part (finding, researching,
// drafting) shows live and stays in the history. The owner's part is one review at the end.
//
// Step shape: { key, phase, title, intro, rows, body, choices, confirm, alternates, answer, start,
// nextLabel, working, final, help, foldLabel, grouped }. A step with `answer` set is history and
// moves forward with Next. `start` marks the screen a bid opens on when it is ready for review.
export function buildSteps(job, progress, dispatch) {
  const research = getResearch(job)
  const act = (type, extra) => () => dispatch({ type, id: job.id, ...extra })
  const steps = []
  const add = (step) => steps.push(step)
  const { stage } = progress
  const posting = research.sources.posting

  add({
    key: 'found',
    phase: 'Find',
    title: stage === 'new' ? 'Found. The agent researches it next.' : "Here's what the agent found.",
    intro: job.real,
    rows: [
      { label: 'Found on', value: `${PORTALS[job.source].name}, ${research.sources.rfp.date}`, cite: posting ? postingCite(posting) : research.overview[0].cite },
      ...research.overview.map((item) => ({ ...item, quote: true })),
    ],
    answer: stage === 'new' ? null : 'Done',
    help: [{ q: 'When does research start?', a: 'On its own, as soon as the agent finishes the bids ahead of this one.' }, SOURCE_HELP],
  })
  if (stage === 'new') return steps

  const researching = stage === 'researching'
  add({
    key: 'research',
    phase: 'Research',
    title: researching ? `Researching ${job.buyer}.` : `How the agent researched ${job.buyer}.`,
    body: (
      <AgentSession
        run={researchRun(job)}
        count={progress.eventCount}
        stats={() => {
          const counts = researchProgress(research, progress.researchStep)
          return [
            { value: counts.pages, label: 'Pages read' },
            { value: counts.sources, label: 'Sources' },
          ]
        }}
      />
    ),
    working: researching,
    answer: researching ? null : 'Done',
    help: LIVE_HELP,
  })
  if (researching) return steps

  const verdict = assess(job)
  if (!verdict.competitive && stage === 'notcompetitive') {
    add({
      key: 'skipped',
      phase: 'Research',
      title: 'The agent skipped this bid.',
      intro: 'It researched the whole RFP and found Cadocary would not be competitive.',
      rows: [
        { label: 'The reason', value: verdict.reason, detail: verdict.detail, cite: verdict.cite, quote: true, tone: 'bad' },
        ...verdictRows(job, research, progress).filter((row) => row.label !== 'Why Cadocary'),
      ],
      confirm: { label: 'Draft it anyway', run: act('draftAnyway') },
      answer: null,
      help: [{ q: 'What does drafting it anyway do?', a: 'The agent writes the proposal as it would for any bid, and it comes back to you to review.' }, SOURCE_HELP],
    })
    return steps
  }

  const drafting = stage === 'drafting'
  const list = sections(job)
  const draft = draftRun(job)
  add({
    key: 'draft',
    phase: 'Draft',
    title: drafting ? `Drafting the bid for ${job.buyer}.` : 'How the agent drafted the bid.',
    intro: drafting ? 'Cadocary is competitive for this one, so the agent is writing the proposal.' : null,
    body: (
      <AgentSession
        run={draft}
        count={drafting ? progress.draftCount : draft.events.length}
        stats={(run) => [
          { value: `${run.written} of ${list.length}`, label: 'Sections' },
          { value: `${list.slice(0, run.written).reduce((sum, s) => sum + s.pages, 0)} of ${job.pageLimit}`, label: 'Pages' },
        ]}
      />
    ),
    working: drafting,
    answer: drafting ? null : 'Done',
    help: LIVE_HELP,
  })
  if (drafting) return steps

  const ready = stage === 'ready'
  add({
    key: 'verdict',
    phase: 'Review',
    start: ready,
    title: verdict.competitive ? 'Cadocary is a competitive bidder.' : 'Drafted at your request.',
    intro: verdict.competitive
      ? `The agent researched it, made the calls, and drafted ${plural(totalPages(job), 'page')}. Here is why it went ahead.`
      : `The agent judged Cadocary not competitive: ${verdict.reason} You asked for a draft anyway.`,
    rows: verdictRows(job, research, progress),
    answer: 'Read',
    nextLabel: 'Read the draft',
    help: [{ q: 'How does the agent decide?', a: "It checks every requirement against Cadocary's products, the eligibility rules, the budget, and who else has the documents." }, SOURCE_HELP],
  })

  list.forEach((section, i) => {
    add({
      key: `section-${i}`,
      phase: 'Review',
      title: 'The draft proposal.',
      intro: `${job.pageLimit}-page limit. The agent's note in the margin says why each section says what it says.`,
      body: (
        <ProposalPage
          job={job}
          progress={progress}
          list={list}
          index={i}
          rewrites={
            ready && (
              <div className="margin-actions">
                <button className="btn btn-secondary" onClick={act('revise', { section: i })}>
                  Make it shorter
                </button>
                <button className="btn btn-secondary" onClick={act('revise', { section: i })}>
                  Make it more specific
                </button>
              </div>
            )
          }
        />
      ),
      answer: 'Read',
      nextLabel: i + 1 < list.length ? 'Next page' : 'Next: upload',
      help: [
        { q: 'Can I edit the text?', a: 'Pick a rewrite here, or edit the final document before you upload it.' },
        { q: 'What are the bracketed parts?', a: 'Things only you know, like names and addresses. Fill them in before you upload.' },
      ],
    })
  })

  add({
    key: 'upload',
    phase: 'Review',
    title: `Upload it to ${job.buyer}?`,
    intro: 'Checked against the RFP format rules. Below are the calls the agent made for you.',
    rows: [
      ...reviewItems(job, progress)
        .filter((item) => FORMAT_CHECKS.includes(item.label))
        .map((item) => ({ ...item, tone: 'good' })),
      ...decisionRows(job, research, progress),
    ],
    confirm: { label: "Looks good. I'll upload it.", run: act('upload') },
    alternates: [{ label: 'Pass on this bid', run: act('pass') }],
    answer: ready ? null : stage === 'passed' ? 'Passed' : 'Uploaded',
    help: [{ q: 'Why do I upload it?', a: 'Cadocary is responsible for what is submitted, so the agent never submits on its own.' }, SOURCE_HELP],
  })
  if (ready) return steps

  if (stage === 'passed') {
    add({ key: 'passed', phase: 'Review', title: 'You passed on this bid.', confirm: { label: 'Bring it back', run: act('reconsider') }, answer: null })
    return steps
  }
  if (stage === 'submitted') {
    add({
      key: 'waiting',
      phase: 'Review',
      title: `Waiting on ${job.buyer}.`,
      rows: [
        { label: 'Uploaded', value: progress.submittedOn },
        { label: 'Price', value: progress.price ?? money(job.price) },
        { label: 'Decision expected', value: progress.decisionBy },
      ],
      prompt: 'Demo only: pick their decision.',
      choices: [
        { label: 'Awarded', run: act('award') },
        { label: 'Not awarded', run: act('lose') },
      ],
      answer: null,
    })
    return steps
  }
  add({
    key: 'result',
    phase: 'Review',
    title: stage === 'awarded' ? `${job.buyer} awarded the contract to Cadocary.` : `${job.buyer} chose another firm.`,
    rows: [
      { label: 'Result', value: stage === 'awarded' ? 'Won' : 'Not awarded', tone: stage === 'awarded' ? 'good' : null },
      { label: 'Price', value: progress.price ?? money(job.price) },
      { label: 'Uploaded', value: progress.submittedOn },
    ],
    answer: null,
    final: true,
  })
  return steps
}
