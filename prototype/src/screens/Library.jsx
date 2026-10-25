import { useState } from 'react'
import { runFacts } from '../agent/live'
import { Steps } from '../agent/Steps'
import { daysLeftText, firstSentence, groupRfps, rfpStatusLine, shortDate, shortTime, useLibrary, useRfp } from '../library'
import { Facts, Mark } from '../parts'
import { navigate } from '../router'
import { Icon } from '../ui'

// The app on the real RFP Library: every SAM.gov notice the agent has stored, grouped by who has
// the next move, and each one's packet and qualification when a run has made them.

const NEAREST_DEADLINES = 8
const TODAY_TEXT = new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })

function RfpRow({ rfp, mark, current }) {
  const working = rfp.run?.status === 'running'
  // A pass reads best as its reason alone. Otherwise the title says which notice it is.
  const line = working || rfp.status === 'passed' ? rfpStatusLine(rfp) : `${rfp.title}. ${rfpStatusLine(rfp)}`
  return (
    <li>
      <button className={`list-item ${working ? 'is-working' : ''}`} aria-current={current ? 'page' : undefined} onClick={() => navigate(`/bids/${rfp.id}`)}>
        <Mark stage={mark} current={current} />
        <span className="list-text">
          <strong>{rfp.buyer}</strong>
          <span>{line}</span>
        </span>
      </button>
    </li>
  )
}

function FoldToggle({ open, count, onToggle }) {
  return (
    <li>
      <button className="list-item" aria-expanded={open} onClick={onToggle}>
        <span className="list-text">
          <strong className="text-link">{open ? 'Show fewer' : `Show all ${count}`}</strong>
        </span>
      </button>
    </li>
  )
}

function LibraryGroup({ group, currentId }) {
  const holdsCurrent = group.rfps.some((rfp) => rfp.id === currentId)
  const [open, setOpen] = useState(!group.folded || holdsCurrent)
  return (
    <section data-tour={`group-${group.id}`}>
      <h2 className={`list-title ${group.needsYou ? 'list-title-needs' : ''}`}>
        <Icon name={group.icon} size={13} stroke={2.2} />
        {group.title} <span className="count">{group.rfps.length}</span>
      </h2>
      <ul>
        {open && group.rfps.map((rfp) => <RfpRow key={rfp.id} rfp={rfp} mark={group.mark} current={rfp.id === currentId} />)}
        {group.folded && <FoldToggle open={open} count={group.rfps.length} onToggle={() => setOpen(!open)} />}
      </ul>
    </section>
  )
}

function LibraryList({ currentId }) {
  const { library } = useLibrary()
  const groups = library ? groupRfps(library.rfps) : []
  return (
    <nav className="desk-list" aria-label="Library" data-tour="library">
      <button className="list-item list-today" aria-current={currentId ? undefined : 'page'} onClick={() => navigate('/today')}>
        <span className="today-mark">
          <Icon name="calendar" size={14} stroke={2.2} />
        </span>
        <span className="list-text">
          <strong>Today</strong>
          <span>{TODAY_TEXT}</span>
        </span>
      </button>
      <h2 className="library-title">
        Library <span className="count">{library ? `${library.rfps.length} RFPs` : 'Loading'}</span>
      </h2>
      {groups
        .filter((group) => group.rfps.length > 0)
        .map((group) => (
          <LibraryGroup key={group.id} group={group} currentId={currentId} />
        ))}
    </nav>
  )
}

function money(dollars) {
  return dollars == null ? null : `$${Math.round(dollars).toLocaleString()}`
}

// Research copies award dates as the source wrote them, so some are not dates a browser can read.
function awardMonth(text) {
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? text : date.toLocaleDateString([], { month: 'short', year: 'numeric' })
}

function worthText(worth) {
  if (!worth || [worth.low, worth.likely, worth.high].every((value) => value == null)) return 'Unknown'
  const range = [money(worth.low), money(worth.high)].filter(Boolean).join(' to ')
  const likely = worth.likely != null ? `, likely ${money(worth.likely)}` : ''
  return `${range}${likely}`
}

function recommendationText(packet, qualification, run) {
  if (packet) return packet.recommendation === 'send' ? 'Send. The agent recommends bidding.' : 'Pass. The agent recommends not bidding.'
  if (qualification) return qualification.decision === 'pass' ? 'Pass, at the go or no-go step' : 'Pursue, still being worked'
  // The packet reaches the library only after a finished run is saved, so until then the run says it.
  if (run?.status === 'finished') return 'Decided in the run above. Its packet is not in the library yet.'
  return 'Not read yet'
}

function CiteChip({ cite }) {
  return (
    <span className="cite">
      {cite.doc}
      {cite.page != null && `, p.${cite.page}`}
    </span>
  )
}

function Section({ title, rows, tour }) {
  if (!rows.length) return null
  return (
    <section className="morning-group" data-tour={tour}>
      <h2 className="start-title">{title}</h2>
      <Facts rows={rows} />
    </section>
  )
}

// One run works one RFP through these stages. Each helper's own status says where it stands.
const STAGES = [
  { key: 'read', label: 'Read', agent: 'Reader', doing: 'is reading the RFP' },
  { key: 'qualify', label: 'Qualify', agent: 'Qualifier', doing: 'is deciding go or no-go' },
  { key: 'research', label: 'Research', agent: 'Researcher', doing: 'is working out what the contract is worth' },
  { key: 'draft', label: 'Draft', agent: 'Drafter', doing: 'is writing the proposal' },
  { key: 'packet', label: 'Packet', agent: 'Operator', doing: 'is writing the packet for Doug' },
]

// done, working, waiting, or skipped. A stage is skipped when the run was not asked for it, or
// when the run ended without reaching it, as after a pass.
function stageState(stage, run) {
  const running = run.status === 'running'
  if (stage.key === 'packet') {
    if (!running) return run.status === 'finished' ? 'done' : 'skipped'
    return run.steps[0]?.text.includes('packet') ? 'working' : 'waiting'
  }
  if (run.planned.length && !run.planned.includes(stage.key)) return 'skipped'
  const state = run.agents[stage.agent]
  if (state === 'working' || state === 'done') return state
  return running ? 'waiting' : 'skipped'
}

const RAIL_STATE = { done: 'done', working: 'current', skipped: 'skipped' }

// What the Operator said last, which at the end of a run is what it decided.
function operatorVerdict(run) {
  const said = run.steps.find((step) => step.agent === 'Operator' && step.text.startsWith('Operator: '))
  return said?.text.replace('Operator: ', '')
}

function runStatusLine(run, states, packet) {
  const minutes = Math.round(run.active_minutes)
  if (run.status === 'running') {
    const working = STAGES.find((stage) => states[stage.key] === 'working')
    return working ? `Working: the ${working.agent} ${working.doing}.` : 'Working: the Operator is deciding the next step.'
  }
  if (run.status === 'stopped') return `Stopped after ${minutes} min, before it finished.`
  const verdict = packet ? `${packet.recommendation === 'send' ? 'Send' : 'Pass'}. ${firstSentence(packet.headline)}` : operatorVerdict(run)
  return verdict ? `Finished in ${minutes} min: ${verdict}` : `Finished in ${minutes} min.`
}

function RunProgress({ run, packet }) {
  const running = run.status === 'running'
  const states = Object.fromEntries(STAGES.map((stage) => [stage.key, stageState(stage, run)]))
  return (
    <section className="rfp-run" aria-label="Where the run on this RFP stands" data-tour="rfp-progress">
      <div className="agent-runbar" data-mode={running ? 'live' : 'last'} aria-live="polite">
        <span className="agent-runbar-tag">{running ? 'Working now' : run.status === 'stopped' ? 'Stopped' : 'Finished'}</span>
        <span className="agent-runbar-text">{runStatusLine(run, states, packet)}</span>
        <span className="agent-runbar-aside">{runFacts(run)}</span>
      </div>
      <ol className="agent-rail rfp-stages" aria-label="Stages of the run">
        {STAGES.map((stage, i) => (
          <li key={stage.key}>
            <span className="agent-rail-item" data-state={RAIL_STATE[states[stage.key]]}>
              {states[stage.key] === 'working' ? <span className="pulse" /> : <span className="agent-rail-num">{i + 1}</span>}
              <span>
                {stage.label}
                <span className="rfp-stage-note">{states[stage.key] === 'working' ? `${stage.agent}, working` : states[stage.key] === 'waiting' ? 'Not started' : states[stage.key] === 'skipped' ? 'Skipped' : 'Done'}</span>
              </span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function RfpBody({ rfp }) {
  const { findings, run } = rfp
  const { packet, qualification, research, summary } = findings
  const running = run?.status === 'running'
  const headline = packet?.headline ?? qualification?.headline
  // A run in progress outranks whatever an earlier run left in the library.
  const intro = running
    ? 'The agent is working on this RFP now. The tracker shows each stage as it happens, and every step below opens to show what it did.'
    : (headline ?? (run ? operatorVerdict(run) : null) ?? 'The agent has not read this RFP yet. It is in the library, waiting its turn.')
  const deadlines = packet?.deadlines ?? []
  const reasons = qualification?.decision_reasons ?? []

  return (
    <div className="step-body">
      <h1 className="step-title">{rfp.title}</h1>
      <p className="step-intro">{intro}</p>
      {run && <RunProgress run={run} packet={packet} />}

      <Facts
        tour="rfp-facts"
        rows={[
          { label: 'Recommendation', value: running ? 'Not decided yet. The agent is working on it.' : recommendationText(packet, qualification, run) },
          packet && { label: 'Expected worth', value: worthText(packet.expected_worth), detail: packet.expected_worth?.basis, detailLabel: packet.expected_worth?.confidence && `Confidence ${packet.expected_worth.confidence}.` },
          research && { label: 'Research estimate', value: worthText(research.value_estimate), detail: research.value_estimate.confidence && `Confidence ${research.value_estimate.confidence}.` },
          rfp.draft_ready && { label: 'Draft', value: 'Draft ready. Doug reads it in the private workspace.' },
          { label: 'Proposal deadline', value: rfp.deadline ? `${shortDate(rfp.deadline)}, ${shortTime(rfp.deadline)}` : 'Not given', detail: daysLeftText(rfp.days_left) },
          { label: 'Buyer', value: rfp.agency ?? 'Not given' },
          { label: 'Kind', value: [rfp.notice_type, rfp.set_aside && `set-aside: ${rfp.set_aside}`].filter(Boolean).join(', ') || 'Not given' },
          rfp.place_of_performance && { label: 'Where', value: rfp.place_of_performance },
        ].filter(Boolean)}
      />

      {run && <Steps title={running ? 'Latest steps' : 'How the run ended'} label="Steps of the run on this RFP" steps={run.steps} tour="run-steps" />}

      <Section
        title="Why"
        tour="rfp-reasons"
        rows={reasons.map((reason, i) => ({
          label: `Reason ${i + 1}`,
          value: reason.reason,
          detail: reason.cite && (
            <>
              {reason.cite.quote && `“${reason.cite.quote}” `}
              <CiteChip cite={reason.cite} />
            </>
          ),
        }))}
      />
      <Section title="Deadlines" rows={deadlines.map((date, i) => ({ label: date.kind ?? `Deadline ${i + 1}`, value: date.as_written, detail: date.page != null ? `Page ${date.page}` : null }))} />
      <Section
        title="Calls the agent made for you"
        rows={(packet?.calls_for_doug ?? []).map((call) => ({ label: call.topic, value: call.choice_made, detail: call.why }))}
      />
      <Section title="Open items" rows={(packet?.open_items ?? []).map((item, i) => ({ label: `Item ${i + 1}`, value: item }))} />
      <Section
        title="Comparable past awards"
        rows={(research?.comparables ?? []).map((award) => ({
          label: award.awarded_on ? awardMonth(award.awarded_on) : 'Date unknown',
          value: `${award.buyer}: ${award.title}`,
          detail: [award.awardee, money(award.amount), award.term_years && (award.term_years === 1 ? '1 year' : `${award.term_years} years`)].filter(Boolean).join(', '),
        }))}
      />
      <Section title="Risks" rows={(packet?.risks ?? []).map((risk, i) => ({ label: `Risk ${i + 1}`, value: risk.risk, detail: risk.source, detailLabel: 'Source:' }))} />
      {summary && (
        <section className="morning-group">
          <h2 className="start-title">Summary</h2>
          {summary
            .split(/\n\s*\n/)
            .filter((paragraph) => paragraph.trim())
            .map((paragraph) => (
              <p className="step-intro" key={paragraph}>
                {paragraph.replace(/^#+\s*/, '')}
              </p>
            ))}
        </section>
      )}
    </div>
  )
}

function RfpPane({ id }) {
  const { state, rfp } = useRfp(id)
  return (
    <div className="desk-main">
      <header className="step-head">
        <button className="all-bids" onClick={() => navigate('/bids')}>
          <Icon name="back" size={16} stroke={2.4} />
          All bids
        </button>
        {rfp && (
          <div className="step-bid">
            <p>
              <strong>{rfp.buyer}</strong> <span className="muted">{rfp.title}</span>
            </p>
            <p className="step-links">
              {rfp.solicitation_number && <span className="tag">{rfp.solicitation_number}</span>}
              {rfp.sam_url && (
                <a className="text-link" href={rfp.sam_url} target="_blank" rel="noreferrer">
                  open on SAM.gov <Icon name="open" size={12} stroke={2.4} />
                </a>
              )}
            </p>
          </div>
        )}
      </header>
      {state === 'found' && <RfpBody rfp={rfp} />}
      {state === 'asking' && (
        <div className="step-body">
          <p className="step-intro">Opening the RFP from the library.</p>
        </div>
      )}
      {state === 'missing' && (
        <div className="step-body">
          <h1 className="step-title">Not in the library</h1>
          <p className="step-intro">There is no RFP with this id in the RFP Library. Sample bids open when Settings, Demo data is set to sample data.</p>
        </div>
      )}
    </div>
  )
}

function Card({ icon, title, count, text, action, idle }) {
  return (
    <li className={`next-card ${idle ? 'next-card-idle' : ''}`}>
      <div className="next-card-head">
        <Icon name={icon} size={18} stroke={2} />
        <h2>{title}</h2>
        <span className="next-count">{count}</span>
      </div>
      <p>{text}</p>
      {action && (
        <button className="next-link" onClick={action.run}>
          {action.label}
          <Icon name="chevron" size={18} stroke={2.4} />
        </button>
      )}
    </li>
  )
}

function Today() {
  const { library } = useLibrary()
  if (!library) {
    return (
      <div className="desk-main">
        <div className="step-body">
          <p className="morning-date">{TODAY_TEXT}</p>
          <h1 className="step-title morning-headline">Opening the RFP Library.</h1>
        </div>
      </div>
    )
  }

  const groups = Object.fromEntries(groupRfps(library.rfps).map((group) => [group.id, group.rfps]))
  const { working, ready, passed } = groups
  const toRead = groups.new
  const open = (rfp) => () => navigate(`/bids/${rfp.id}`)
  const headline = ready.length === 0 ? 'Nothing needs you right now.' : `${ready.length} ${ready.length === 1 ? 'RFP is' : 'RFPs are'} ready for you.`
  const nearest = library.rfps
    .filter((rfp) => rfp.deadline && rfp.days_left >= 0 && rfp.status !== 'passed')
    .sort((a, b) => a.deadline.localeCompare(b.deadline))
    .slice(0, NEAREST_DEADLINES)

  return (
    <div className="desk-main">
      <header className="step-head step-head-plain">
        <button className="all-bids" onClick={() => navigate('/bids')}>
          <Icon name="back" size={16} stroke={2.4} />
          All bids
        </button>
      </header>
      <div className="step-body">
        <p className="morning-date">{TODAY_TEXT}</p>
        <h1 className="step-title morning-headline">{headline}</h1>
        <p className="step-intro">
          The RFP Library holds {library.rfps.length} open SAM.gov notices for Cadocary's codes. The agent reads each one, passes on the ones Cadocary cannot win, and drafts the rest for you.
        </p>

        <ul className="next-cards" data-tour="today-cards">
          <Card
            icon="doc"
            title="Ready for you"
            count={`${ready.length} ready`}
            idle={!ready.length}
            text={ready.length ? `Packets ready to read: ${ready.map((rfp) => rfp.buyer).join(', ')}.` : 'No packets waiting. The agent brings each one here when it recommends sending.'}
            action={ready.length ? { label: 'Read the packet', run: open(ready[0]) } : null}
          />
          <Card
            icon="agent"
            title="Agent working"
            count={`${working.length} working`}
            idle={!working.length}
            text={working.length ? `${working[0].buyer}: ${working[0].run.steps[0]?.text ?? 'working'}.` : 'Nothing running right now.'}
            action={{ label: working.length ? 'Watch it work' : 'See how it works', run: working.length ? open(working[0]) : () => navigate('/agent') }}
          />
          <Card
            icon="close"
            title="Passed"
            count={`${passed.length} passed`}
            idle={!passed.length}
            text={passed.length ? `${passed[0].buyer}: ${passed[0].headline ? firstSentence(passed[0].headline) : 'passed.'}` : 'Nothing passed yet.'}
            action={passed.length ? { label: 'See why', run: open(passed[0]) } : null}
          />
          <Card icon="search" title="To read" count={`${toRead.length} to read`} idle={!toRead.length} text={`${toRead.length} notices are waiting for the agent to read them, nearest deadline first.`} />
        </ul>

        {library.runs.length > 0 && (
          <section className="morning-group">
            <h2 className="start-title">Latest runs</h2>
            <Facts
              rows={library.runs.map((run) => ({
                label: `${shortDate(run.started_at)}, ${shortTime(run.started_at)}`,
                value: run.rfp_title ?? run.title,
                detail: runFacts(run),
              }))}
            />
          </section>
        )}

        {nearest.length > 0 && (
          <section className="morning-group">
            <h2 className="start-title">Nearest deadlines</h2>
            <ul className="facts agenda" aria-label="Deadlines">
              {nearest.map((rfp) => (
                <li className="agenda-item" key={rfp.id}>
                  <div className={`agenda-row ${rfp.days_left <= 14 ? 'agenda-soon' : ''}`} role="button" tabIndex={0} onClick={open(rfp)} onKeyDown={(event) => event.key === 'Enter' && open(rfp)()}>
                    <span className="agenda-date">
                      <span>{shortDate(rfp.deadline).split(' ')[0]}</span>
                      <strong>{new Date(rfp.deadline).getDate()}</strong>
                    </span>
                    <span className="agenda-bid">
                      <strong>{rfp.buyer}</strong>
                      <span>{rfp.title}</span>
                    </span>
                    <span className="agenda-kind kind-due">{rfp.response_kind === 'bid' ? 'Proposals due' : 'Response due'}</span>
                    <span className="agenda-when">
                      <strong>{shortTime(rfp.deadline)}</strong>
                      <span>{daysLeftText(rfp.days_left)}</span>
                    </span>
                    <span className="agenda-source">
                      <span className="cite">SAM.gov</span>
                    </span>
                    <span className="agenda-chevron">
                      <Icon name="chevron" size={16} stroke={2.2} />
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  )
}

export function LiveBids({ id, today }) {
  return (
    <div className={`desk ${id || today ? 'has-open' : ''}`}>
      <LibraryList currentId={id} />
      {id ? <RfpPane key={id} id={id} /> : <Today />}
    </div>
  )
}
