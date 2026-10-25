import { useState } from 'react'
import { COMPANY, JOBS, LEFT_OUT, LEFT_OUT_REASONS, PORTALS, STAGE_INFO, TODAY, TODAY_DATE } from '../data'
import { categorize, liveAction } from '../needs'
import { getResearch } from '../research'
import { navigate } from '../router'
import { postingCite, leftOutPosting } from '../research/postings'
import { Cite, DocChip } from '../sources'
import { REASON_HINTS, deadlineBrief } from '../hints'
import { Facts } from '../parts'
import { useStore } from '../store'
import { Hint, Icon } from '../ui'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const FINISHED = ['passed', 'notcompetitive', 'lost', 'submitted', 'awarded']
const DAY_MS = 24 * 60 * 60 * 1000
const SOON_DAYS = 14
const AHEAD_DAYS = 42
const FIRST_DEADLINES = 5

// Reads the day out of "Sat, Oct 31 · 5:00 PM", "Fri, Oct 25, 2024 · 5:00 PM", or "Nov 4 to 8, 2024".
function parseDay(text) {
  const match = text.match(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{1,2})/)
  if (!match) return null
  const year = text.match(/\b(20\d\d)\b/)?.[1] ?? TODAY_DATE.getFullYear()
  return new Date(Number(year), MONTHS.indexOf(match[1]), Number(match[2]))
}

// Every deadline in the open bids over the next six weeks, soonest first.
function comingUp(state) {
  const items = []
  for (const job of JOBS) {
    if (FINISHED.includes(state.jobs[job.id].stage)) continue
    for (const date of getResearch(job).dates) {
      const day = parseDay(date.value)
      const days = day && Math.round((day - TODAY_DATE) / DAY_MS)
      if (day && days >= 0 && days <= AHEAD_DAYS) items.push({ job, date, day, days, time: date.value.split(' · ')[1] })
    }
  }
  return items.sort((a, b) => a.day - b.day)
}

// Where a bid was found: its posting, or for bids posted on the buyer's own site, the RFP itself.
function foundCite(job) {
  const research = getResearch(job)
  return research.sources.posting ? postingCite(research.sources.posting) : research.overview[0].cite
}

const inDays = (days) => (days === 0 ? 'today' : days === 1 ? 'tomorrow' : `in ${days} days`)

function Drawer({ label, hint, value, detail, children }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="drawer">
      <button className="drawer-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Hint text={hint} align="start">
          <span className="drawer-label">{label}</span>
        </Hint>
        <span className="drawer-value">
          <span>{value}</span>
          {detail && <span className="fact-detail">{detail}</span>}
        </span>
        <Icon name={open ? 'up' : 'down'} size={16} stroke={2.2} />
      </button>
      {open && <ul className="drawer-items">{children}</ul>}
    </li>
  )
}

function LeftOutItem({ item, aside }) {
  const posting = leftOutPosting(item)
  return (
    <li className="drawer-item">
      <span>
        <strong>{item.buyer}</strong> · {item.title}
        {item.note && ` · ${item.note}`}
      </span>
      <span className="drawer-aside">{aside}</span>
      <DocChip doc={posting} cite={postingCite(posting)} />
    </li>
  )
}

// What each card on the morning page says about a category, given how many bids are in it.

const KIND_TONE = { 'Proposals due': 'kind-due', 'Questions due': 'kind-questions' }

// One deadline. Opens into a short brief, like the notes you would want before a meeting: what
// happens that day, who it is with, where the bid stands, and what you need to do.
function Deadline({ job, progress, date, day, days, time }) {
  const [open, setOpen] = useState(false)
  const brief = deadlineBrief(job, progress, date.label)
  const how = date.label === 'Proposals due' ? getResearch(job).overview.find((row) => row.label === 'How to submit') : null
  const toggle = () => setOpen(!open)

  return (
    <li className={`agenda-item ${open ? 'open' : ''}`}>
      <div
        className={`agenda-row ${days <= SOON_DAYS ? 'agenda-soon' : ''}`}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={toggle}
        onKeyDown={(event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          toggle()
        }}
      >
        <span className="agenda-date">
          <span>{MONTHS[day.getMonth()]}</span>
          <strong>{day.getDate()}</strong>
        </span>
        <span className="agenda-bid">
          <strong>{job.buyer}</strong>
          <span>{job.title}</span>
        </span>
        <span className={`agenda-kind ${KIND_TONE[date.label] ?? ''}`}>{date.label}</span>
        <span className="agenda-when">
          <strong>{time ?? 'All day'}</strong>
          <span>{inDays(days)}</span>
        </span>
        <span className="agenda-source">
          <Cite job={job} cite={date.cite} />
        </span>
        <span className="agenda-chevron">
          <Icon name={open ? 'up' : 'down'} size={16} stroke={2.2} />
        </span>
      </div>
      {open && (
        <div className="agenda-brief">
          <Facts
            job={job}
            rows={[
              { label: 'What happens', value: brief.happens },
              { label: 'Who', value: `${job.buyer}, ${job.agency}` },
              { label: 'Where it stands', value: brief.stands },
              { label: 'What you do', value: brief.todo },
              how && { label: 'How', value: how.value, cite: how.cite },
              { label: 'Source', value: date.value, cite: date.cite, quote: true },
            ].filter(Boolean)}
          />
          <button className="btn btn-primary agenda-open" onClick={() => navigate(`/bids/${job.id}`)}>
            Open {job.buyer}
          </button>
        </div>
      )}
    </li>
  )
}

// With no bid open: the morning. What needs doing, what is due soon, where the agent looked
// overnight, and every posting it left out with the reason. Each line opens to its detail.
export function Morning() {
  const { state } = useStore()
  const [allDeadlines, setAllDeadlines] = useState(false)
  const deadlines = comingUp(state)
  const shownDeadlines = allDeadlines ? deadlines : deadlines.slice(0, FIRST_DEADLINES)
  // Bids found overnight, in whatever stage the agent has taken them to since.
  const overnight = JOBS.filter((job) => job.start.stage !== 'submitted')
  const byId = Object.fromEntries(categorize(state).map((category) => [category.id, category.entries]))
  const ready = byId.ready
  const working = [...byId.drafting, ...byId.researching]
  const upNext = byId.new
  const skipped = byId.notcompetitive
  const headline = ready.length === 0 ? 'Nothing needs you right now.' : `${ready.length} ${ready.length === 1 ? 'bid is' : 'bids are'} ready for you.`

  return (
    <div className="desk-main">
      <header className="step-head step-head-plain">
        <button className="all-bids" onClick={() => navigate('/bids')}>
          <Icon name="back" size={16} stroke={2.4} />
          All bids
        </button>
      </header>
      <div className="step-body">
        <p className="morning-date">{TODAY}</p>
        <h1 className="step-title morning-headline">{headline}</h1>
        <p className="step-intro">
          Overnight the agent checked {COMPANY.watching.length} sources, found {overnight.length} bids worth a look, and left out {LEFT_OUT.length}. It researches each one, drafts the ones Cadocary can win, and brings you the finished bid.
        </p>

        <ul className="next-cards">
          <li className={`next-card ${ready.length ? '' : 'next-card-idle'}`}>
            <div className="next-card-head">
              <Icon name="doc" size={18} stroke={2} />
              <h2>Ready for you</h2>
              <span className="next-count">{ready.length} ready</span>
            </div>
            {ready.length > 0 ? (
              <p>
                {ready.length === 1 ? 'One bid is' : `${ready.length} bids are`} researched and fully drafted: {ready.map((entry) => entry.job.buyer).join(', ')}. Read it, then upload it or pass.
              </p>
            ) : (
              <p>No finished bids yet. The agent brings each one here as soon as it is drafted.</p>
            )}
            {ready.length > 0 && (
              <button className="btn btn-primary next-primary" onClick={() => navigate(`/bids/${ready[0].job.id}`)}>
                Review the bid
                <Icon name="chevron" size={18} stroke={2.4} />
              </button>
            )}
          </li>
          <li className={`next-card next-card-working ${working.length ? '' : 'next-card-idle'}`}>
            <div className="next-card-head">
              <Icon name="agent" size={18} stroke={2} />
              <h2>Agent working</h2>
              <span className="next-count">{working.length} working</span>
            </div>
            {working.length > 0 ? (
              <p>
                <strong>{working[0].job.buyer}:</strong> {liveAction(working[0].job, working[0].progress)}.
                {upNext.length > 0 && ` ${upNext.length} more ${upNext.length === 1 ? 'bid is' : 'bids are'} waiting to be read.`}
              </p>
            ) : (
              <p>Nothing running right now. It checks for new bids again tomorrow at 6:00 AM.</p>
            )}
            <button className="next-link" onClick={() => navigate(working.length ? `/bids/${working[0].job.id}` : '/agent')}>
              {working.length ? 'Watch it work' : 'See how it works'}
              <Icon name="chevron" size={18} stroke={2.4} />
            </button>
          </li>
          <li className={`next-card next-card-skipped ${skipped.length ? '' : 'next-card-idle'}`}>
            <div className="next-card-head">
              <Icon name="close" size={18} stroke={2} />
              <h2>Skipped by the agent</h2>
              <span className="next-count">{skipped.length} skipped</span>
            </div>
            {skipped.length > 0 ? (
              <p>
                Researched, but Cadocary would not be competitive: {skipped.map((entry) => entry.job.buyer).join(', ')}. You can still have one drafted.
              </p>
            ) : (
              <p>Every bid it has researched so far is worth drafting.</p>
            )}
            {skipped.length > 0 && (
              <button className="next-link" onClick={() => navigate(`/bids/${skipped[0].job.id}`)}>
                See why
                <Icon name="chevron" size={18} stroke={2.4} />
              </button>
            )}
          </li>
        </ul>

        {deadlines.length > 0 && (
          <section className="morning-group">
            <h2 className="start-title">Coming up</h2>
            <ul className="facts agenda" aria-label="Deadlines">
              <li className="agenda-row agenda-header" aria-hidden="true">
                <span>Date</span>
                <span>Bid</span>
                <span>Deadline</span>
                <span>Time</span>
                <span>Source</span>
                <span />
              </li>
              {shownDeadlines.map((item) => (
                <Deadline key={`${item.job.id}-${item.date.label}`} {...item} progress={state.jobs[item.job.id]} />
              ))}
              {deadlines.length > FIRST_DEADLINES && (
                <li className="run-fold">
                  <button className="text-link" onClick={() => setAllDeadlines(!allDeadlines)}>
                    {allDeadlines ? 'Show fewer' : `Show ${deadlines.length - FIRST_DEADLINES} more`}
                    <Icon name={allDeadlines ? 'up' : 'down'} size={14} stroke={2.4} />
                  </button>
                </li>
              )}
            </ul>
          </section>
        )}

        <section className="morning-group">
          <h2 className="start-title">Where it looked</h2>
          <ul className="facts drawers">
            {COMPANY.watching.map((source) => {
              const bids = overnight.filter((job) => PORTALS[job.source].name === source.name)
              const left = LEFT_OUT.filter((item) => item.source === source.name)
              return (
                <Drawer
                  key={source.name}
                  label={source.name}
                  hint={source.detail}
                  value={`${bids.length} found, ${left.length} left out`}
                  detail={source.last === 'Live' ? `${source.checked} checked as they arrived.` : `${source.checked} checked at ${source.last}.`}
                >
                  {bids.map((job) => (
                    <li key={job.id} className="drawer-item">
                      <button className="drawer-bid" onClick={() => navigate(`/bids/${job.id}`)}>
                        <span className="drawer-new">{STAGE_INFO[state.jobs[job.id].stage].label}</span>
                        <span>
                          <strong>{job.buyer}</strong> · {job.title}
                        </span>
                        <Icon name="chevron" size={16} stroke={2.2} />
                      </button>
                      <Cite job={job} cite={foundCite(job)} />
                    </li>
                  ))}
                  {left.map((item) => (
                    <LeftOutItem key={`${item.buyer}-${item.title}`} item={item} aside={item.reason} />
                  ))}
                </Drawer>
              )
            })}
          </ul>
        </section>

        <section className="morning-group">
          <h2 className="start-title">Why {LEFT_OUT.length} were left out</h2>
          <ul className="facts drawers">
            {LEFT_OUT_REASONS.map((reason) => {
              const items = LEFT_OUT.filter((item) => item.reason === reason)
              return (
                <Drawer key={reason} label={reason} hint={`${REASON_HINTS[reason]} You can change these rules in Settings.`} value={`${items.length} bids`} detail={`For example: ${items[0].buyer}, ${items[0].title.toLowerCase()}`}>
                  {items.map((item) => (
                    <LeftOutItem key={`${item.buyer}-${item.title}`} item={item} aside={`From ${item.source}`} />
                  ))}
                </Drawer>
              )
            })}
          </ul>
        </section>
      </div>

    </div>
  )
}
