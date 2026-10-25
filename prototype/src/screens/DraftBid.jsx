import { useEffect, useRef, useState } from 'react'
import { Markdown } from '../markdown'
import { Icon } from '../ui'

// The agent's draft bid for a real RFP, from /api/rfp/<id>/proposal. The server has already taken
// out contact details and the notes the Drafter left for Doug. It shows first as a small picture
// of its first page, and opens into the whole document.

const NOT_SENT = 'Draft, not sent. Doug reviews and sends it himself.'
const DONT_BID_NOTE = 'The agent recommends not bidding on this RFP.'
// The first page needs only the start of the draft.
const FIRST_PAGE_CHARACTERS = 2500

export function useProposal(id, hasDraft) {
  const [proposal, setProposal] = useState(null)
  useEffect(() => {
    if (!hasDraft) return
    let stopped = false
    fetch(`/api/rfp/${id}/proposal`)
      .then((reply) => (reply.ok ? reply.json() : null))
      .catch(() => null)
      .then((answer) => !stopped && setProposal(answer))
    return () => {
      stopped = true
    }
  }, [id, hasDraft])
  return proposal
}

function sizeText(proposal) {
  const pages = proposal.page_count?.estimated
  const sections = proposal.markdown.split('\n').filter((line) => /^##\s/.test(line)).length
  return [pages && `About ${pages} pages`, `${sections} sections`, proposal.compliance.length && `${proposal.compliance.length} requirements mapped`].filter(Boolean).join(', ')
}

export function DraftThumbnail({ proposal, onOpen }) {
  return (
    <div className="bid-thumb" data-tour="open-bid">
      <button className="bid-thumb-page" aria-label="Open the draft bid" onClick={onOpen}>
        <article className="doc-page bid-doc" aria-hidden="true">
          <Markdown text={proposal.markdown.slice(0, FIRST_PAGE_CHARACTERS)} />
        </article>
      </button>
      <div className="bid-thumb-text">
        <strong>Draft bid. Not sent.</strong>
        <span>{sizeText(proposal)}</span>
        {proposal.recommendation === 'pass' && <span>{DONT_BID_NOTE}</span>}
        <button className="text-link" onClick={onOpen}>
          Open the bid <Icon name="open" size={12} stroke={2.4} />
        </button>
      </div>
    </div>
  )
}

function Compliance({ rows }) {
  if (!rows.length) return null
  return (
    <>
      <h2>Where each requirement is answered</h2>
      <table>
        <thead>
          <tr>
            <th>Requirement</th>
            <th>Section</th>
            <th>Page</th>
            <th>Status</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.requirement_id}>
              <td>{row.requirement_id}</td>
              <td>{row.section}</td>
              <td>{row.page}</td>
              <td>{row.status}</td>
              <td>{row.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

export function DraftViewer({ proposal, onClose }) {
  const closeButton = useRef(null)

  useEffect(() => {
    closeButton.current?.focus({ preventScroll: true })
    const onKey = (event) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return (
    <div className="viewer" role="dialog" aria-modal="true" aria-label={`Draft bid for ${proposal.title}`}>
      <header className="viewer-bar">
        <span className="viewer-doc">
          <Icon name="doc" size={18} />
          <span>
            <strong>Draft bid: {proposal.title}</strong>
            <span>{NOT_SENT}</span>
          </span>
        </span>
        <button className="viewer-close" aria-label="Close the draft bid" onClick={onClose} ref={closeButton}>
          <Icon name="close" size={20} />
        </button>
      </header>
      <div className="viewer-body">
        <div className="viewer-canvas">
          <article className="doc-page bid-doc">
            <header className="doc-head">
              <span>Cadocary LLC, to {proposal.buyer}</span>
              <span>{NOT_SENT}</span>
            </header>
            {proposal.recommendation === 'pass' && <p className="bid-advice">{DONT_BID_NOTE}</p>}
            <Markdown text={proposal.markdown} />
            <Compliance rows={proposal.compliance} />
          </article>
        </div>
      </div>
    </div>
  )
}
