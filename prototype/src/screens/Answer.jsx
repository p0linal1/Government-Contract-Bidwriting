import { useCallback, useEffect, useRef, useState } from 'react'
import { Choice } from '../parts'
import { blankAnswer, isAnswered, QUESTIONS } from '../questions'
import { navigate } from '../router'

// Doug answers the agent's questions here, one per screen. His private link carries a code that
// the server checks before it reads or saves anything, because the answers include his prices.

const CODE_KEY = 'cadocary-answers-code'
const STEP_KEY = 'cadocary-answers-step'
const TEXT_SAVE_MS = 800
const ADVANCE_MS = 220

function readStored(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function store(key, value) {
  try {
    localStorage.setItem(key, value)
    return true
  } catch {
    // Private browsing can block storage. Then the link is needed again on the next visit.
    return false
  }
}

function startingStep() {
  const saved = readStored(STEP_KEY)
  const step = saved == null ? -1 : Number(saved)
  return Number.isInteger(step) && step >= -1 && step <= QUESTIONS.length ? step : -1
}

function useAnswers(code) {
  const [answers, setAnswers] = useState(() => Object.fromEntries(QUESTIONS.map((q) => [q.id, blankAnswer()])))
  const [status, setStatus] = useState(code ? 'loading' : 'locked')
  const [saved, setSaved] = useState('')
  // The newest answers, for saves that run between renders.
  const latest = useRef(answers)
  const inFlight = useRef({})
  const again = useRef({})
  const timers = useRef({})

  useEffect(() => {
    if (!code) return
    let current = true
    fetch('/api/answers', { headers: { 'X-Answers-Code': code } })
      .then((reply) => (reply.ok ? reply.json() : Promise.reject(new Error(reply.status === 403 ? 'locked' : 'unavailable'))))
      .then((body) => {
        if (!current) return
        const merged = { ...latest.current }
        for (const [id, value] of Object.entries(body.answers ?? {})) {
          if (merged[id]) merged[id] = { ...blankAnswer(), ...value }
        }
        latest.current = merged
        setAnswers(merged)
        setStatus('ready')
      })
      .catch((error) => current && setStatus(error.message === 'locked' ? 'locked' : 'unavailable'))
    return () => {
      current = false
    }
  }, [code])

  const send = useCallback(
    (id) => {
      if (inFlight.current[id]) {
        again.current[id] = true
        return
      }
      inFlight.current[id] = true
      setSaved('Saving')
      const { choice, choices, rows, text, note, skipped } = latest.current[id]
      fetch(`/api/answers/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-Answers-Code': code },
        body: JSON.stringify({ choice, choices, rows, text, note, skipped }),
      })
        .then((reply) => setSaved(reply.ok ? 'Saved' : 'Not saved. Your answer is kept and saves on the next change.'))
        .catch(() => setSaved('Not saved. Check your connection.'))
        .finally(() => {
          inFlight.current[id] = false
          if (again.current[id]) {
            again.current[id] = false
            send(id)
          }
        })
    },
    [code],
  )

  const update = useCallback(
    (id, change, { now = true } = {}) => {
      const next = { ...latest.current, [id]: { ...latest.current[id], ...change } }
      latest.current = next
      setAnswers(next)
      clearTimeout(timers.current[id])
      delete timers.current[id]
      if (now) send(id)
      else
        timers.current[id] = setTimeout(() => {
          delete timers.current[id]
          send(id)
        }, TEXT_SAVE_MS)
    },
    [send],
  )

  // Saves typing that is still waiting, before leaving a question.
  const flush = useCallback(() => {
    for (const [id, timer] of Object.entries(timers.current)) {
      clearTimeout(timer)
      delete timers.current[id]
      send(id)
    }
  }, [send])

  return { answers, status, saved, update, flush }
}

function Options({ question, answer, onPick }) {
  return (
    <div className="choices" role="radiogroup" aria-labelledby="answer-title">
      {question.options.map((option) => (
        <Choice key={option} label={option} selected={answer.choice === option} onChoose={() => onPick(answer.choice === option ? '' : option)} />
      ))}
    </div>
  )
}

function Checkboxes({ question, answer, onChange }) {
  return (
    <div className="choices" role="group" aria-labelledby="answer-title">
      {question.options.map((option) => {
        const on = answer.choices.includes(option)
        return (
          <button
            key={option}
            className={`choice ${on ? 'selected' : ''}`}
            role="checkbox"
            aria-checked={on}
            onClick={() => onChange(on ? answer.choices.filter((c) => c !== option) : [...answer.choices, option])}
          >
            <span className="radio is-box" aria-hidden="true" />
            <span className="choice-label">{option}</span>
          </button>
        )
      })}
    </div>
  )
}

function Rows({ question, answer, onChange }) {
  return (
    <div className="answer-rows">
      {question.rows.map(([key, name, detail]) => (
        <div className="answer-row" key={key}>
          <div className="answer-row-name" id={`row-${key}`}>
            <strong>{name}</strong>
            {detail && <span>{detail}</span>}
          </div>
          <div className="answer-chips" role="group" aria-labelledby={`row-${key}`}>
            {question.options.map((option) => (
              <button
                key={option}
                className="answer-chip"
                aria-pressed={answer.rows[key] === option}
                onClick={() => {
                  const rows = { ...answer.rows }
                  if (rows[key] === option) delete rows[key]
                  else rows[key] = option
                  onChange(rows)
                }}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function Typed({ question, answer, onChange }) {
  const shared = { id: 'answer-input', className: 'answer-input', value: answer.text, placeholder: question.placeholder, onChange: (event) => onChange(event.target.value) }
  if (question.kind === 'money') {
    return (
      <label className="answer-money">
        <span>$</span>
        <input {...shared} type="text" inputMode="numeric" aria-label={question.title} />
        <span>{question.suffix}</span>
      </label>
    )
  }
  if (question.multiline) return <textarea {...shared} rows={5} aria-labelledby="answer-title" />
  return <input {...shared} type={question.input ?? 'text'} autoComplete={question.input === 'email' ? 'email' : 'off'} aria-labelledby="answer-title" />
}

function Question({ question, answer, number, last, update, go }) {
  const [noteOpen, setNoteOpen] = useState(Boolean(answer.note) || question.kind === 'grid')
  const showNote = noteOpen || (question.noteWhen && answer.choice === question.noteWhen)
  const showSend = question.send && (!question.sendWhen || answer.choice === question.sendWhen)

  const pick = (choice) => {
    update(question.id, { choice, skipped: false })
    const needsMore = (question.noteWhen && choice === question.noteWhen) || (question.sendWhen && choice === question.sendWhen) || (question.send && !question.sendWhen)
    if (choice && !needsMore) setTimeout(() => go(number), ADVANCE_MS)
  }

  return (
    <>
      <h1 className="answer-title" id="answer-title">
        {question.title}
      </h1>
      {question.help && <p className="answer-help">{question.help}</p>}
      {question.facts && (
        <ul className="answer-facts">
          {question.facts.map(([label, value]) => (
            <li key={label}>
              <strong>{label}</strong>
              <span>{value}</span>
            </li>
          ))}
        </ul>
      )}
      {question.kind === 'one' && <Options question={question} answer={answer} onPick={pick} />}
      {question.kind === 'many' && <Checkboxes question={question} answer={answer} onChange={(choices) => update(question.id, { choices, skipped: false })} />}
      {question.kind === 'grid' && <Rows question={question} answer={answer} onChange={(rows) => update(question.id, { rows, skipped: false })} />}
      {(question.kind === 'text' || question.kind === 'money') && (
        <Typed question={question} answer={answer} onChange={(text) => update(question.id, { text, skipped: false }, { now: false })} />
      )}
      {showSend && <p className="answer-send">{question.send}</p>}
      {question.kind !== 'text' &&
        (showNote ? (
          <label className="answer-note">
            <span>{question.notePrompt ?? 'Add a note (optional)'}</span>
            <textarea className="answer-input" rows={3} value={answer.note} onChange={(event) => update(question.id, { note: event.target.value }, { now: false })} />
          </label>
        ) : (
          <button className="answer-add-note" onClick={() => setNoteOpen(true)}>
            Add a note
          </button>
        ))}
      <div className="answer-nav">
        <button className="btn btn-primary" onClick={() => go(number)}>
          {last ? 'Finish' : 'Next'}
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => {
            if (!isAnswered(question, answer)) update(question.id, { skipped: true })
            go(number)
          }}
        >
          Skip
        </button>
        <button className="btn btn-secondary answer-back" onClick={() => go(number - 2)}>
          Back
        </button>
      </div>
    </>
  )
}

function Review({ answers, go }) {
  const answered = QUESTIONS.filter((q) => isAnswered(q, answers[q.id])).length
  return (
    <>
      <h1 className="answer-title">{answered === QUESTIONS.length ? "That's everything. Thank you." : "Thank you. That's a big help."}</h1>
      <p className="answer-help">There's nothing to send: the team reads your answers here. Tap any question to change it. Anything you skipped, we'll cover on a quick call.</p>
      <ul className="answer-review">
        {QUESTIONS.map((q, i) => {
          const [tone, label] = isAnswered(q, answers[q.id]) ? ['done', 'Answered'] : answers[q.id].skipped ? ['skipped', 'Skipped'] : ['open', 'Not yet']
          return (
            <li key={q.id}>
              <button onClick={() => go(i)}>
                <span>{q.title}</span>
                <span className={`answer-tag is-${tone}`}>{label}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </>
  )
}

export function Answer({ code: codeInLink }) {
  const [code] = useState(() => codeInLink ?? readStored(CODE_KEY))
  const { answers, status, saved, update, flush } = useAnswers(code)
  const [step, setStep] = useState(startingStep)

  useEffect(() => {
    // Once the code is kept on this device, it comes out of the address bar and history.
    if (codeInLink && store(CODE_KEY, codeInLink)) window.history.replaceState(null, '', '#/answer')
  }, [codeInLink])

  const go = (next) => {
    flush()
    const clamped = Math.max(-1, Math.min(QUESTIONS.length, next))
    setStep(clamped)
    store(STEP_KEY, String(clamped))
    window.scrollTo(0, 0)
  }

  if (status !== 'ready') {
    const message = {
      loading: 'Loading your answers.',
      locked: "These questions are Doug's to answer, and they open from his private link. Ask Sheffield for it.",
      unavailable: "The answers can't be reached right now. Try again in a minute.",
    }[status]
    return (
      <div className="step-body">
        <div className="answer">
          <h1 className="answer-title">Questions for Doug</h1>
          <p className="answer-help">{message}</p>
          {status === 'locked' && (
            <div className="answer-nav">
              <button className="btn btn-secondary" onClick={() => navigate('/facts/questions')}>
                See the questions
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  const answered = QUESTIONS.filter((q) => isAnswered(q, answers[q.id])).length
  const firstOpen = QUESTIONS.findIndex((q) => !isAnswered(q, answers[q.id]) && !answers[q.id].skipped)
  const question = QUESTIONS[step]

  return (
    <div className="step-body">
      <div className="answer">
        <div className="answer-top">
          <div className="answer-top-line">
            <span>{step < 0 ? 'About 10 minutes, mostly taps' : question ? `Question ${step + 1} of ${QUESTIONS.length}` : `${answered} of ${QUESTIONS.length} answered`}</span>
            <span>{saved}</span>
          </div>
          <div className="answer-bar" aria-hidden="true">
            <span style={{ width: `${Math.round((100 * answered) / QUESTIONS.length)}%` }} />
          </div>
        </div>

        {step < 0 && (
          <>
            <h1 className="answer-title">A few questions for Doug</h1>
            <p className="answer-help">
              Your answers teach the bid agent what is true about Cadocary and which bids you'd want. Most questions are one tap. Skip anything, and come back any time: it saves as you go.
            </p>
            <div className="answer-nav">
              <button className="btn btn-primary" onClick={() => go(answered ? (firstOpen === -1 ? QUESTIONS.length : firstOpen) : 0)}>
                {answered ? 'Pick up where you left off' : 'Start'}
              </button>
              {answered > 0 && (
                <button className="btn btn-secondary" onClick={() => go(QUESTIONS.length)}>
                  See all questions
                </button>
              )}
            </div>
          </>
        )}
        {question && <Question key={question.id} question={question} answer={answers[question.id]} number={step + 1} last={step === QUESTIONS.length - 1} update={update} go={go} />}
        {step >= QUESTIONS.length && <Review answers={answers} go={go} />}
      </div>
    </div>
  )
}
