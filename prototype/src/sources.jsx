import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { citationsBySource, citeLabel, getResearch } from './research'
import { citeHint } from './hints'
import { Hint, Icon } from './ui'

const SourceContext = createContext(null)

export function SourceProvider({ children }) {
  const [open, setOpen] = useState(null)
  return (
    <SourceContext.Provider value={{ open, show: setOpen, close: () => setOpen(null) }}>
      {children}
      {open && <DocumentViewer job={open.job} given={open.doc} cite={open.cite} />}
    </SourceContext.Provider>
  )
}

export function useSources() {
  return useContext(SourceContext)
}

export function Cite({ job, cite }) {
  const { show } = useSources()
  const research = getResearch(job)
  return (
    <Hint text={citeHint(research.sources[cite.src], cite)} align="end">
      <button
        className="cite"
        onClick={(event) => {
          event.stopPropagation()
          show({ job, cite })
        }}
      >
        {citeLabel(cite, research)}
        <Icon name="open" size={11} stroke={2.4} />
      </button>
    </Hint>
  )
}

export function Quote({ job, cite }) {
  return (
    <figure className="quote-block">
      <blockquote>{cite.quote}</blockquote>
      <figcaption>
        <Cite job={job} cite={cite} />
      </figcaption>
    </figure>
  )
}

// A chip for a document that belongs to no bid, such as a posting the agent left out.
export function DocChip({ doc, cite }) {
  const { show } = useSources()
  return (
    <Hint text={citeHint(doc, cite)} align="end">
      <button
        className="cite"
        onClick={(event) => {
          event.stopPropagation()
          show({ doc, cite })
        }}
      >
        {doc.short}
        <Icon name="open" size={11} stroke={2.4} />
      </button>
    </Hint>
  )
}

// Text lines around the highlighted passage, drawn as bars so the page reads like a scan.
const LINE_WIDTHS = [100, 96, 100, 88, 100, 72]

const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// The real text of a page, with the quoted passage marked. Line breaks in the page do not
// have to match the quote, so any run of whitespace in the quote matches any other.
function PageText({ text, quote, email }) {
  const words = quote.trim().split(/\s+/).filter(Boolean)
  const match = words.length ? text.match(new RegExp(words.map(escape).join('\\s+'))) : null
  const className = email ? 'pdf-real pdf-email' : 'pdf-real'
  if (!match) return <p className={className}>{text}</p>
  const start = match.index
  const end = start + match[0].length
  return (
    <p className={className}>
      {text.slice(0, start)}
      <mark>{text.slice(start, end)}</mark>
      {text.slice(end)}
    </p>
  )
}

// Shows a page from a bid's sources, or a document handed over directly (`given`) that belongs to
// no bid, like a posting the agent left out.
function DocumentViewer({ job, given, cite }) {
  const { show, close } = useSources()
  const research = job && getResearch(job)
  const doc = given ?? research.sources[cite.src]
  const passages = (research && citationsBySource(research)[cite.src]) ?? [cite]
  const isFromCadocary = doc.kind === 'Cadocary file'
  const lastPage = useRef(cite.page)
  const closeButton = useRef(null)
  const canvas = useRef(null)
  const direction = cite.page >= lastPage.current ? 'forward' : 'back'
  // Paging through a real document shows each page plainly, with no passage marked.
  const turnTo = (page) => show({ job, doc: given, cite: { src: cite.src, page, section: '', quote: '' } })

  useEffect(() => {
    lastPage.current = cite.page
  }, [cite.page])

  // A modal dialog holds focus while it is open. Without this, focus stays on the chip or link
  // that opened it, and closing with Escape leaves a focus ring on that link.
  useEffect(() => {
    closeButton.current?.focus({ preventScroll: true })
  }, [])

  // On a long page the quoted passage can sit below the fold, so bring it into view.
  useEffect(() => {
    canvas.current?.querySelector('mark')?.scrollIntoView({ block: 'center' })
  }, [cite.page, cite.quote])

  useEffect(() => {
    const onKey = (event) => event.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [close])

  return (
    <div className="viewer" role="dialog" aria-modal="true" aria-label={`${doc.title}, page ${cite.page}`}>
      <header className="viewer-bar">
        <span className="viewer-doc">
          <Icon name="doc" size={18} />
          <span>
            <strong>{doc.title}</strong>
            <span>
              {doc.kind} · {doc.from}
            </span>
          </span>
        </span>
        <span className="viewer-page">
          {doc.text && (
            <button aria-label="Previous page" disabled={cite.page <= 1} onClick={() => turnTo(cite.page - 1)}>
              <Icon name="back" size={18} stroke={2.4} />
            </button>
          )}
          {cite.page} / {doc.pages}
          {doc.text && (
            <button aria-label="Next page" disabled={cite.page >= doc.pages} onClick={() => turnTo(cite.page + 1)}>
              <Icon name="chevron" size={18} stroke={2.4} />
            </button>
          )}
        </span>
        {doc.original && (
          <a className="viewer-original" href={doc.original} target="_blank" rel="noreferrer">
            Original PDF <Icon name="open" size={12} stroke={2.4} />
          </a>
        )}
        <button className="viewer-close" aria-label="Close document" onClick={close} ref={closeButton}>
          <Icon name="close" size={20} />
        </button>
      </header>

      <div className="viewer-body">
        <aside className="viewer-passages" aria-label="Passages the agent used">
          <p className="label">Passages used · {passages.length}</p>
          <ul>
            {passages.map((passage) => {
              const current = passage.page === cite.page && passage.quote === cite.quote
              return (
                <li key={`${passage.page}-${passage.quote}`}>
                  <button aria-current={current ? 'true' : undefined} onClick={() => show({ job, doc: given, cite: passage })}>
                    <span className="passage-page">p.{passage.page}</span>
                    <span className="passage-text">{passage.quote}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </aside>

        <div className="viewer-canvas" ref={canvas}>
          <article className={`pdf-page turn-${direction}`} key={`${cite.page}-${cite.quote}`}>
            <div className="pdf-head">
              <span>{isFromCadocary ? 'Cadocary LLC' : job ? `${job.buyer} · ${job.agency}` : doc.from}</span>
              <span>{doc.title}</span>
            </div>
            {doc.text ? (
              <PageText text={doc.text[cite.page - 1]} quote={cite.quote} email={doc.kind === 'Email'} />
            ) : (
              <>
                {cite.section && <p className="pdf-section">{cite.section}</p>}
                {LINE_WIDTHS.slice(0, 3).map((width, i) => (
                  <span key={`a${i}`} className="pdf-line" style={{ width: `${width}%` }} />
                ))}
                <p className="pdf-text">
                  <mark>{cite.quote}</mark>
                </p>
                {LINE_WIDTHS.map((width, i) => (
                  <span key={`b${i}`} className="pdf-line" style={{ width: `${width}%` }} />
                ))}
              </>
            )}
            <div className="pdf-foot">
              Page {cite.page} of {doc.pages}
            </div>
          </article>
        </div>
      </div>
    </div>
  )
}
