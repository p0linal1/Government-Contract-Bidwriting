import { useState } from 'react'
import { WORKING, liveAction, shortStatus } from './needs'
import { getResearch } from './research'
import { Cite } from './sources'
import { statusHint } from './hints'
import { Hint, Icon } from './ui'

const DONE = ['submitted', 'awarded']
const CLOSED = ['passed', 'notcompetitive', 'lost']
const NEEDS_YOU = ['ready']

// The circle in front of each bid: a dot when it is waiting on you, empty when new, pulsing
// while the agent works, a check when done, and filled when it is the one open.
export function Mark({ stage, current }) {
  if (DONE.includes(stage)) {
    return (
      <span className="mark mark-done">
        <Icon name="check" size={11} stroke={3.2} />
      </span>
    )
  }
  if (CLOSED.includes(stage)) return <span className="mark mark-closed" />
  const state = WORKING.includes(stage) ? 'mark-working' : NEEDS_YOU.includes(stage) ? 'mark-needs' : ''
  return <span className={`mark ${state} ${current ? 'mark-current' : ''}`} />
}

export function Tone({ tone }) {
  const icon = { good: 'check', bad: 'close' }[tone]
  return <span className={`tone tone-${tone}`}>{icon && <Icon name={icon} size={10} stroke={3.4} />}</span>
}

// Label on the left, what was found on the right, the source chip and its exact words under it.
// Grouped tables leave a repeated label blank so each group reads as one block.
export function Facts({ job, rows, foldLabel, grouped, tour }) {
  const [unfolded, setUnfolded] = useState(false)
  const research = job && getResearch(job)
  const folded = rows.filter((row) => row.folded).length
  const shown = unfolded ? rows : rows.filter((row) => !row.folded)
  return (
    <dl className="facts" data-tour={tour}>
      {shown.map((row, i) => {
        const pages = row.cite && research.sources[row.cite.src]?.pages
        const repeat = grouped && i > 0 && shown[i - 1].label === row.label
        return (
          <div className={`fact ${repeat ? 'fact-repeat' : ''}`} key={`${row.label}-${row.value}`}>
            <dt>{repeat ? '' : <Hint text={row.labelHint} align="start">{row.label}</Hint>}</dt>
            <dd>
              <span className="fact-value">
                {row.tone && <Tone tone={row.tone} />}
                <span>
                  {row.value}
                  {row.cite && (
                    <>
                      {' '}
                      <Cite job={job} cite={row.cite} />
                    </>
                  )}
                </span>
              </span>
              {row.detail && (
                <span className="fact-detail">
                  {row.detailLabel && <strong>{row.detailLabel} </strong>}
                  {row.detail}
                  {row.detailCite && (
                    <>
                      {' '}
                      <Cite job={job} cite={row.detailCite} />
                    </>
                  )}
                </span>
              )}
              {row.quote && row.cite && (
                <span className="fact-quote">
                  “{row.cite.quote}”{pages > 1 && <span> p.{row.cite.page}</span>}
                </span>
              )}
            </dd>
          </div>
        )
      })}
      {folded > 0 && (
        <div className="fact fact-fold">
          <dt />
          <dd>
            <button className="text-link" aria-expanded={unfolded} onClick={() => setUnfolded(!unfolded)}>
              {unfolded ? 'Hide them' : (foldLabel ?? `Show ${folded} more`)}
              <Icon name={unfolded ? 'up' : 'down'} size={14} stroke={2.4} />
            </button>
          </dd>
        </div>
      )}
    </dl>
  )
}

export function Choice({ label, note, selected, disabled, onChoose }) {
  return (
    <button className={`choice ${selected ? 'selected' : ''}`} role="radio" aria-checked={selected} disabled={disabled} onClick={onChoose}>
      <span className="radio" aria-hidden="true" />
      <span className="choice-label">{label}</span>
      {note && <span className="choice-note">{note}</span>}
    </button>
  )
}

// One bid in a list. While the agent works on it, the second line is what it is doing right now.
export function BidRow({ entry, current, onOpen }) {
  const { job, progress } = entry
  const working = WORKING.includes(progress.stage)
  return (
    <li>
      <Hint text={statusHint(job, progress)} align="start" block>
      <button className={`list-item ${working ? 'is-working' : ''}`} aria-current={current ? 'page' : undefined} onClick={onOpen}>
        <Mark stage={progress.stage} current={current} />
        <span className="list-text">
          <strong>{job.buyer}</strong>
          <span>{working ? liveAction(job, progress) : shortStatus(job, progress)}</span>
        </span>
      </button>
      </Hint>
    </li>
  )
}
