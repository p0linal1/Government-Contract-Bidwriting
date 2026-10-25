import { totalPages } from '../bid'
import { money } from '../data'
import { getResearch } from '../research'
import { Cite } from '../sources'
import { Icon } from '../ui'

// For proposals without hand-written notes: why each standard section is written the way it is.
const STANDARD_WHY = [
  'Opens with the product closest to what they are buying.',
  'Answers each requirement in the order the RFP lists them, so evaluators can score it line by line.',
  'Follows how the RFP scores the approach.',
  'Uses the references you confirmed.',
]

function standardAnswers(research, index) {
  const references = research.eligibility.find((row) => row.item.startsWith('References'))
  return [research.overview[0].cite, research.requirements[0]?.cite, research.scoring.cite, references?.cite][index]
}

// The draft proposal on its own pages, the way someone across a desk turns a document around
// and walks you through it: one section at a time, marked with a highlighter, with a note in the
// margin saying which line of the RFP it answers.
export function ProposalPage({ job, progress, list, index, rewrites }) {
  const research = getResearch(job)
  const section = list[index]
  const revised = progress.revised[index]
  const price = progress.price ?? money(job.price)
  const text = revised ? section.revised : (section.draftFor?.[progress.answer] ?? section.draft)
  const paragraphs = (Array.isArray(text) ? text : [text]).map((paragraph) => paragraph.replaceAll('{price}', price))
  const first = list.slice(0, index).reduce((sum, s) => sum + s.pages, 0) + 1
  const last = first + section.pages - 1
  const answers = section.answers ?? standardAnswers(research, index)

  return (
    <div className="proposal">
      <ol className="doc-strip" aria-label="Sections of the proposal">
        {list.map((item, i) => (
          <li key={item.title} className={i < index ? 'done' : i === index ? 'now' : ''}>
            <span className="doc-strip-mark">{i < index ? <Icon name="check" size={10} stroke={3.4} /> : i + 1}</span>
            <span className="doc-strip-title">{item.title}</span>
          </li>
        ))}
      </ol>

      <div className="proposal-desk">
        <article className="doc-page" key={`${index}-${revised ? 'revised' : 'draft'}`}>
          <header className="doc-head">
            <span>Cadocary LLC</span>
            <span>Proposal to {job.buyer}</span>
          </header>
          <p className="doc-kicker">Section {index + 1}</p>
          <h2 className="doc-title">
            <span className="pen">{section.title}</span>
          </h2>
          {paragraphs.map((paragraph, i) => (
            <p key={paragraph} className="doc-text">
              <span className="pen" style={{ animationDelay: `${200 + i * 220}ms` }}>
                {paragraph}
              </span>
            </p>
          ))}
          <footer className="doc-foot">
            {first === last ? `Page ${first}` : `Pages ${first} to ${last}`} of {totalPages(job)}
          </footer>
        </article>

        <aside className="margin-note">
          <p className="margin-label">Why it says this</p>
          <p>{section.why ?? STANDARD_WHY[index]}</p>
          {answers && (
            <>
              <p className="margin-label">Answers this line of the RFP</p>
              <blockquote>
                “{answers.quote}” <Cite job={job} cite={answers} />
              </blockquote>
            </>
          )}
          {revised && <p className="margin-done">Rewritten once.</p>}
          {rewrites}
        </aside>
      </div>
    </div>
  )
}
