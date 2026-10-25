import { useEffect, useRef, useState } from 'react'
import { PHASES, buildSteps } from '../bid/flow'
import { JOBS_BY_ID, TODAY } from '../data'
import { Morning } from './Morning'
import { categorize, nextReady } from '../needs'
import { getResearch } from '../research'
import { navigate } from '../router'
import { BidRow, Choice, Facts } from '../parts'
import { useSources } from '../sources'
import { useStore } from '../store'
import { PHASE_HINTS } from '../hints'
import { Hint, Icon } from '../ui'

function BidList({ section, currentId }) {
  const { state } = useStore()
  const lists = categorize(state)
  const total = lists.reduce((sum, list) => sum + list.entries.length, 0)

  return (
    <nav className="desk-list" aria-label="Library">
      <button className="list-item list-today" aria-current={currentId ? undefined : 'page'} onClick={() => navigate('/today')}>
        <span className="today-mark">
          <Icon name="calendar" size={14} stroke={2.2} />
        </span>
        <span className="list-text">
          <strong>Today</strong>
          <span>{TODAY}</span>
        </span>
      </button>
      <h2 className="library-title">
        Library <span className="count">{total} RFPs</span>
      </h2>
      {lists
        .filter((list) => list.entries.length > 0)
        .map((list) => (
          <section key={list.id}>
            <h2 className={`list-title ${list.needsYou ? 'list-title-needs' : ''}`}>
              <Icon name={list.icon} size={13} stroke={2.2} />
              {list.title} <span className="count">{list.entries.length}</span>
            </h2>
            <ul>
              {list.entries.map((entry) => (
                <BidRow key={entry.job.id} entry={entry} current={entry.job.id === currentId} onOpen={() => navigate(`/${section}/${entry.job.id}`)} />
              ))}
            </ul>
          </section>
        ))}
    </nav>
  )
}

function Help({ items, onClose }) {
  const [open, setOpen] = useState(null)
  return (
    <div className="help" role="dialog" aria-label="Questions about this step">
      <div className="help-head">
        <span>Questions about this step</span>
        <button className="icon-button" aria-label="Close" onClick={onClose}>
          <Icon name="close" size={16} />
        </button>
      </div>
      <ul>
        {items.map((item) => (
          <li key={item.q}>
            <button aria-expanded={open === item.q} onClick={() => setOpen(open === item.q ? null : item.q)}>
              {item.q}
              <Icon name="down" size={14} />
            </button>
            {open === item.q && <p>{item.a}</p>}
          </li>
        ))}
      </ul>
    </div>
  )
}

const GENERAL_HELP = [{ q: 'Where does each line come from?', a: 'The chip next to a line opens the page it came from, with the passage highlighted.' }]

// The bar under every screen: back, a question, and the one thing that moves it forward.
function Actions({ canBack, onBack, help, primary }) {
  const [helpOpen, setHelpOpen] = useState(false)
  const bar = useRef(null)

  useEffect(() => {
    if (!helpOpen) return
    const close = (event) => !bar.current?.contains(event.target) && setHelpOpen(false)
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [helpOpen])

  return (
    <footer className="step-actions" ref={bar}>
      {helpOpen && <Help items={help ?? GENERAL_HELP} onClose={() => setHelpOpen(false)} />}
      <button className="text-button" disabled={!canBack} onClick={onBack}>
        <Icon name="undo" size={16} />
        Back a step
      </button>
      <button className="pill-button" aria-expanded={helpOpen} onClick={() => setHelpOpen(!helpOpen)}>
        Not sure, I have a question
      </button>
      {primary && (
        <button className="btn btn-primary step-primary" disabled={primary.disabled} onClick={primary.run}>
          {primary.label}
        </button>
      )}
    </footer>
  )
}

function StepView({ job, step, canBack, onBack, onForward, nextBid }) {
  const [pending, setPending] = useState(null)
  const answered = step.answer != null

  let primary = null
  if (answered) primary = { label: step.nextLabel ?? 'Next', run: onForward }
  else if (step.confirm) primary = { label: step.confirm.label, run: step.confirm.run }
  else if (step.choices) primary = { label: 'Continue', disabled: !pending, run: () => pending.run() }
  else if (nextBid) primary = { label: `Next bid: ${nextBid.job.buyer}`, run: () => navigate(nextBid.to) }

  return (
    <>
      <div className="step-body">
        <h1 className="step-title">{step.title}</h1>
        {step.intro && <p className="step-intro">{step.intro}</p>}
        {step.working && (
          <p className="step-working">
            <span className="pulse" />
            Working on its own. This updates as it goes.
          </p>
        )}

        {step.rows && <Facts job={job} rows={step.rows} foldLabel={step.foldLabel} grouped={step.grouped} />}
        {step.body && <div className="step-extra">{step.body}</div>}
        {step.alternates && !answered && (
          <div className="alternates">
            {step.alternates.map((alt) => (
              <button key={alt.label} className="btn btn-secondary" onClick={alt.run}>
                {alt.label}
              </button>
            ))}
          </div>
        )}

        {step.choices && (
          <div className="choices" role="radiogroup" aria-label={step.title}>
            {step.prompt && <p className="choices-prompt">{step.prompt}</p>}
            {step.choices.map((choice) => (
              <Choice key={choice.label} label={choice.label} selected={pending === choice} onChoose={() => setPending(choice)} />
            ))}
          </div>
        )}
      </div>

      <Actions canBack={canBack} onBack={onBack} help={step.help} primary={primary} />
    </>
  )
}

function Phases({ current }) {
  const at = PHASES.indexOf(current)
  return (
    <ol className="phases" aria-label="Where this bid is">
      {PHASES.map((phase, i) => (
        <li key={phase} className={i < at ? 'done' : i === at ? 'now' : ''}>
          <Hint text={PHASE_HINTS[phase]} align={i > 1 ? 'end' : 'center'} below>
            <span className="phase-dot">{i < at && <Icon name="check" size={10} stroke={3.4} />}</span>
            {phase}
          </Hint>
        </li>
      ))}
    </ol>
  )
}

function BidPane({ job, section }) {
  const { state, dispatch } = useStore()
  const { show } = useSources()
  const progress = state.jobs[job.id]
  const research = getResearch(job)
  const steps = buildSteps(job, progress, dispatch)
  // A ready bid opens on its review. Otherwise the bid opens on the first screen still in progress.
  const marked = steps.findIndex((s) => s.start)
  const firstOpen = steps.findIndex((s) => s.answer == null)
  const currentIndex = marked !== -1 ? marked : firstOpen === -1 ? steps.length - 1 : firstOpen

  const [view, setView] = useState(currentIndex)
  const lastCurrent = useRef(currentIndex)
  const pane = useRef(null)

  // When the agent moves the bid forward, jump to the new screen.
  useEffect(() => {
    if (currentIndex !== lastCurrent.current) {
      lastCurrent.current = currentIndex
      setView(currentIndex)
    }
  }, [currentIndex])

  useEffect(() => {
    pane.current?.scrollTo(0, 0)
    window.scrollTo(0, 0)
  }, [view])

  const index = Math.min(view, steps.length - 1)
  const step = steps[index]
  const next = nextReady(state, job.id)
  const researched = !['new', 'researching'].includes(progress.stage)

  return (
    <div className="desk-main" ref={pane}>
      <header className="step-head">
        <button className="all-bids" onClick={() => navigate(`/${section}`)}>
          <Icon name="back" size={16} stroke={2.4} />
          All bids
        </button>
        <div className="step-bid">
          <p>
            <strong>{job.buyer}</strong> <span className="muted">{job.title}</span>
          </p>
          <p className="step-links">
            <span className="tag">{job.solicitation}</span>
            <button className="text-link" onClick={() => show({ job, cite: research.overview[0].cite })}>
              open the RFP <Icon name="open" size={12} stroke={2.4} />
            </button>
            {researched && (
              <button className="text-link" onClick={() => navigate(`/${section}/${job.id}/research`)}>
                full research <Icon name="open" size={12} stroke={2.4} />
              </button>
            )}
          </p>
        </div>
        <Phases current={step.phase} />
      </header>

      <StepView
        key={`${step.key}-${index}`}
        job={job}
        step={step}
        canBack={index > 0}
        onBack={() => setView(index - 1)}
        onForward={() => setView(index + 1)}
        nextBid={next && { job: next.job, to: `/${section}/${next.job.id}` }}
      />
    </div>
  )
}

// The whole app: Today and every bid down the left, sectioned by who has the next move. The open
// bid, or the morning when none is open, fills the rest. On a phone the list is the first screen,
// so Today opens like a bid does.
export function Bids({ id, today }) {
  const job = id && JOBS_BY_ID[id]
  return (
    <div className={`desk ${job || today ? 'has-open' : ''}`}>
      <BidList section="bids" currentId={id} />
      {job ? <BidPane key={id} job={job} section="bids" /> : <Morning />}
    </div>
  )
}
