import { useEffect, useState } from 'react'
import { Markdown } from '../markdown'
import { navigate } from '../router'
import { Icon } from '../ui'

// A private claude.ai page where Doug answers the questions. It opens only for the people it is shared with.
const ANSWER_PAGE = 'https://claude.ai/artifact/Qp4Jy1q2iq7DGRrvLsfTm5'

const PAGES = [
  {
    id: 'facts',
    title: 'What the agent knows',
    note: 'Every fact it may claim, and its source',
    intro: 'The agent may claim only what is in this file. Prices and private contacts are kept in a separate file that never leaves the team.',
  },
  {
    id: 'questions',
    title: 'Questions for Doug',
    note: 'What the agent still needs from Doug',
    intro: 'Until Doug answers these, the agent marks each gap in a bid instead of guessing.',
  },
  {
    id: 'tracker',
    title: 'Context tracker',
    note: 'How close the agent is, piece by piece',
    intro: 'Everything the agent needs to work like Doug, scored after every round of research.',
  },
]

function Document({ page }) {
  const [text, setText] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let current = true
    fetch(`/api/facts/${page.id}`)
      .then((reply) => (reply.ok ? reply.text() : Promise.reject(new Error(`${reply.status}`))))
      .then((body) => current && setText(body))
      .catch(() => current && setFailed(true))
    return () => {
      current = false
    }
  }, [page.id])

  return (
    <>
      <h1 className="step-title">{page.title}</h1>
      <p className="step-intro">{page.intro}</p>
      {page.id === 'questions' && (
        <div className="alternates">
          <a className="btn btn-secondary" href={ANSWER_PAGE} target="_blank" rel="noreferrer">
            Open Doug's answer page
          </a>
        </div>
      )}
      {failed && <p className="step-intro">This file can't be loaded here. It loads on the live app, which reads it from the repo.</p>}
      {!failed && text == null && <p className="step-intro">Loading the file.</p>}
      {text != null && (
        <article className="doc-page bid-doc facts-doc">
          <Markdown text={text} />
        </article>
      )}
    </>
  )
}

export function Facts({ id }) {
  const open = PAGES.find((page) => page.id === id)
  // On a laptop the first page shows by default. On a phone the list comes first.
  const shown = open ?? PAGES[0]

  return (
    <div className={`desk ${open ? 'has-open' : ''}`}>
      <nav className="desk-list" aria-label="Facts">
        <section>
          <h2 className="list-title">Facts</h2>
          <ul>
            {PAGES.map((page) => (
              <li key={page.id}>
                <button className="list-item" aria-current={page.id === shown.id ? 'page' : undefined} onClick={() => navigate(`/facts/${page.id}`)}>
                  <span className="list-text">
                    <strong>{page.title}</strong>
                    <span>{page.note}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </nav>
      <div className="desk-main">
        <header className="step-head step-head-plain">
          <button className="all-bids" onClick={() => navigate('/facts')}>
            <Icon name="back" size={16} stroke={2.4} />
            Facts
          </button>
        </header>
        <div className="step-body" key={shown.id}>
          <Document page={shown} />
        </div>
      </div>
    </div>
  )
}
