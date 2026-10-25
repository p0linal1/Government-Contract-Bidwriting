import { useState } from 'react'
import { stepTime } from './live'
import { Icon } from '../ui'

// A real run's latest steps, newest first. Each opens to show what the agent was given (the file,
// search, command, or page) and the start of what came back. The server has already cut both
// short and taken out contact details.

function Step({ step }) {
  const [open, setOpen] = useState(false)
  const { input, result } = step.detail ?? {}
  return (
    <li className="agent-step">
      <button className="agent-step-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <time dateTime={step.at}>{stepTime(step.at)}</time>
        <span>
          {step.text}
          {step.count > 1 && <span className="muted"> ({step.count} times)</span>}
        </span>
        <Icon name={open ? 'up' : 'down'} size={14} stroke={2.2} />
      </button>
      {open && (
        <div className="agent-step-detail">
          {input && (
            <>
              <p className="agent-step-label">Given</p>
              <pre>{input}</pre>
            </>
          )}
          <p className="agent-step-label">{input ? 'Came back' : 'Said'}</p>
          <pre>{result ?? 'Nothing yet. This step is still running.'}</pre>
        </div>
      )}
    </li>
  )
}

export function Steps({ title, label, steps }) {
  if (!steps.length) return null
  return (
    <section className="agent-steps" aria-label={label}>
      <p className="agent-steps-title">{title}</p>
      <ol>
        {steps.map((step) => (
          <Step key={`${step.at}-${step.text}`} step={step} />
        ))}
      </ol>
    </section>
  )
}
