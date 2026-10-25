import { useEffect, useRef, useState } from 'react'
import { translate } from '../agent/session'
import { Icon } from '../ui'

const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`

// A new agent message arrives a few words at a time, the way the session previews text.
function Streamed({ text, live }) {
  const [started] = useState(() => (live ? performance.now() : null))
  const [shown, setShown] = useState(live ? 0 : text.length)

  useEffect(() => {
    if (started === null) return
    let frame
    const reveal = (now) => {
      const next = Math.min(text.length, Math.round(((now - started) / 600) * text.length))
      setShown(next)
      if (next < text.length) frame = requestAnimationFrame(reveal)
    }
    frame = requestAnimationFrame(reveal)
    return () => cancelAnimationFrame(frame)
  }, [started, text])

  return text.slice(0, shown)
}

function Item({ item }) {
  if (item.note) {
    return (
      <li className="run-note">
        <Icon name="note" size={15} />
        <p>
          <Streamed text={item.note} live={item.live} />
        </p>
      </li>
    )
  }
  return (
    <li className={`run-item run-${item.state ?? 'done'}`}>
      <span className="run-icon">
        <Icon name={item.icon} size={15} />
      </span>
      <span className="run-text">
        <span className="run-title">{item.title}</span>
        {item.detail && <span className="run-detail">{item.detail}</span>}
      </span>
      <span className="run-state">
        {item.state === 'running' && <span className="spinner" aria-label="Running" />}
        {item.state === 'done' && item.seconds > 0 && `${item.seconds}s`}
      </span>
    </li>
  )
}

function Step({ step, open, onToggle }) {
  const actions = step.items.filter((item) => !item.note && item.icon !== 'you').length
  const canToggle = step.status === 'done' && step.items.length > 0
  return (
    <li className={`run-step run-step-${step.status}`}>
      <button className="run-step-head" disabled={!canToggle} aria-expanded={canToggle ? open : undefined} onClick={onToggle}>
        <span className="run-mark">{step.status === 'done' && <Icon name="check" size={10} stroke={3.4} />}</span>
        <span className="run-step-text">{step.text}</span>
        {canToggle && (
          <span className="run-count">
            {actions} {actions === 1 ? 'action' : 'actions'}
            <Icon name={open ? 'up' : 'down'} size={14} stroke={2.4} />
          </span>
        )}
      </button>
      {open && step.items.length > 0 && (
        <ul className="run-items">
          {step.items.map((item) => (
            <Item key={item.id} item={item} />
          ))}
        </ul>
      )}
    </li>
  )
}

// The session exactly as it streamed, newest at the bottom. Simulation-only fields are left out.
function RawEvents({ events }) {
  const list = useRef(null)

  useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight
  }, [events.length])

  return (
    <ol className="raw-events" ref={list} aria-label="Raw session events">
      {events.map(({ step, at, ...event }) => (
        <li key={event.id}>
          <span className="raw-type">{event.type}</span>
          <code>{JSON.stringify(event)}</code>
        </li>
      ))}
    </ol>
  )
}

// One agent run on a bid: its plan as a list of steps, and under the current step every
// search, page, file, and note as it happens. `stats` are the numbers across the top.
export function AgentSession({ run: source, count, stats }) {
  const [view, setView] = useState('plain')
  const [opened, setOpened] = useState(() => new Set())
  const run = translate(source, count)
  const [showAll, setShowAll] = useState(false)

  // While it runs, keep the screen short: a few steps either side of the one it is on.
  const current = run.steps.findIndex((step) => step.status === 'now')
  const folding = current !== -1 && !showAll
  const from = folding ? Math.max(0, current - 2) : 0
  const to = folding ? Math.min(run.steps.length, current + 4) : run.steps.length
  const hiddenBefore = from
  const hiddenAfter = run.steps.length - to

  const toggle = (index) =>
    setOpened((previous) => {
      const next = new Set(previous)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })

  return (
    <>
      <div className="facts run-tally">
        <ul className="tally">
          <li>
            <strong>{clock(run.clock)}</strong>
            <span>Run time</span>
          </li>
          <li>
            <strong>{run.toolCalls}</strong>
            <span>Tool calls</span>
          </li>
          {stats(run).map((stat) => (
            <li key={stat.label}>
              <strong>{stat.value}</strong>
              <span>{stat.label}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="run-bar">
        <p className="run-model">Claude, running as a managed agent</p>
        <div className="segmented" role="group" aria-label="How to show the agent's work">
          <button aria-pressed={view === 'plain'} onClick={() => setView('plain')}>
            Plain English
          </button>
          <button aria-pressed={view === 'raw'} onClick={() => setView('raw')}>
            Raw events
          </button>
        </div>
      </div>

      {view === 'plain' ? (
        <ol className="facts run-steps">
          {hiddenBefore > 0 && (
            <li className="run-fold">
              <button className="text-link" onClick={() => setShowAll(true)}>
                Show {hiddenBefore} earlier {hiddenBefore === 1 ? 'step' : 'steps'}
                <Icon name="up" size={14} stroke={2.4} />
              </button>
            </li>
          )}
          {run.steps.map(
            (step, i) => i >= from && i < to && <Step key={step.text} step={step} open={step.status === 'now' || opened.has(i)} onToggle={() => toggle(i)} />,
          )}
          {hiddenAfter > 0 && (
            <li className="run-fold">
              <button className="text-link" onClick={() => setShowAll(true)}>
                Show {hiddenAfter} more {hiddenAfter === 1 ? 'step' : 'steps'}
                <Icon name="down" size={14} stroke={2.4} />
              </button>
            </li>
          )}
        </ol>
      ) : (
        <RawEvents events={source.events.slice(0, count)} />
      )}
    </>
  )
}
