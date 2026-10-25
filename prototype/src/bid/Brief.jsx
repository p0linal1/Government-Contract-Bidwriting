import { useState } from 'react'
import { RATE, money } from '../data'
import { citationsBySource, eligibilityStatus, getResearch, tally } from '../research'
import { Sheet, Status } from '../Sheet'
import { Cite, useSources } from '../sources'

const COVERAGE = { meets: ['Meets', 'good'], partial: ['Partly', 'warn'], gap: ['Gap', 'bad'] }
const ELIGIBLE = { pass: ['OK', 'good'], gap: ['Fix', 'bad'], unknown: ['Unknown', 'warn'] }
const LEVEL = { High: 'bad', Medium: 'warn', Low: 'plain' }

const cite = (job, value) => (value ? <Cite job={job} cite={value} /> : <span className="muted">Cadocary file</span>)

// The headline numbers as a two-column sheet. Also used on the "research done" step.
export function SummarySheet({ job, progress }) {
  const research = getResearch(job)
  const numbers = tally(research)
  const option = job.question?.options.find((o) => o.id === progress.answer)
  const due = research.dates.find((d) => d.label === 'Proposals due')
  const rows = [
    { item: 'Recommendation', value: <strong>{option?.verdict ?? research.verdict.title}</strong> },
    { item: 'Requirements met', value: `${numbers.coverage.meets} of ${numbers.requirements} (${numbers.coverage.partial} partly, ${numbers.coverage.gap} gaps)` },
    { item: 'Estimated score', value: `${numbers.score} of 100` },
    { item: 'Risks', value: `${numbers.risks.High} high, ${numbers.risks.Medium} medium, ${numbers.risks.Low} low` },
    { item: 'Budget', value: money(job.value), source: research.pricing.budget.cite },
    { item: 'Cost estimate', value: `${money(numbers.cost)} (${numbers.hours.toLocaleString('en-US')} h × $${RATE})`, source: research.pricing.rateCite },
    { item: 'Suggested price', value: money(job.price) },
    { item: 'Proposals due', value: job.due, source: due?.cite },
    { item: 'Competitors', value: `${research.competition.count ?? research.competition.planholders.length} firms`, source: research.competition.cite },
    { item: 'Sources read', value: Object.keys(research.sources).length },
  ]
  return (
    <Sheet
      label="Summary"
      numbered={false}
      columns={[
        { key: 'item', label: 'Item', width: '34%' },
        { key: 'value', label: 'Finding' },
        { key: 'source', label: 'Source', render: (row) => (row.source ? <Cite job={job} cite={row.source} /> : null) },
      ]}
      rows={rows}
      rowKey={(row) => row.item}
    />
  )
}

export function Brief({ job, progress }) {
  const { show } = useSources()
  const [tab, setTab] = useState('summary')
  const research = getResearch(job)
  const numbers = tally(research)
  const bySource = citationsBySource(research)
  const changes = research.addenda.flatMap((a) => a.changes.map((c) => ({ ...c, addendum: a.title })))

  const tabs = [
    { id: 'summary', label: 'Summary' },
    { id: 'requirements', label: `Requirements ${numbers.requirements}` },
    { id: 'eligibility', label: 'Eligibility' },
    { id: 'risks', label: `Risks ${research.risks.length}` },
    { id: 'pricing', label: 'Pricing' },
    { id: 'scoring', label: 'Scoring' },
    { id: 'competition', label: 'Competition' },
    { id: 'dates', label: 'Dates & changes' },
    { id: 'questions', label: 'Questions' },
    { id: 'sources', label: `Sources ${Object.keys(research.sources).length}` },
    { id: 'log', label: 'Agent log' },
  ]

  const sheets = {
    summary: () => <SummarySheet job={job} progress={progress} />,
    requirements: () => (
      <Sheet
        label="Requirements"
        columns={[
          { key: 'id', label: 'ID', render: (r) => <span className="mono">{r.id}</span> },
          { key: 'text', label: 'Requirement', width: '26%' },
          { key: 'kind', label: 'Type' },
          { key: 'coverage', label: 'Status', render: (r) => <Status tone={COVERAGE[r.coverage][1]}>{COVERAGE[r.coverage][0]}</Status> },
          { key: 'quote', label: 'RFP says', width: '24%', render: (r) => <span className="cell-quote">{r.cite.quote}</span> },
          { key: 'cite', label: 'Source', render: (r) => cite(job, r.cite) },
          { key: 'evidence', label: 'Cadocary today', width: '22%' },
          { key: 'evidenceCite', label: 'Evidence', render: (r) => cite(job, r.evidenceCite) },
        ]}
        rows={research.requirements}
        rowKey={(r) => r.id}
      />
    ),
    eligibility: () => (
      <Sheet
        label="Eligibility"
        columns={[
          { key: 'item', label: 'Rule' },
          { key: 'required', label: 'They require' },
          { key: 'cite', label: 'Source', render: (r) => cite(job, r.cite) },
          { key: 'ours', label: 'Cadocary has', render: (r) => (r.status === 'answer' && progress.answer ? job.question.options.find((o) => o.id === progress.answer).label : r.ours) },
          { key: 'oursCite', label: 'Evidence', render: (r) => (r.oursCite ? <Cite job={job} cite={r.oursCite} /> : null) },
          {
            key: 'status',
            label: 'Status',
            render: (r) => {
              const [text, tone] = ELIGIBLE[eligibilityStatus(r, progress, job)]
              return <Status tone={tone}>{text}</Status>
            },
          },
        ]}
        rows={research.eligibility}
        rowKey={(r) => r.item}
      />
    ),
    risks: () => (
      <Sheet
        label="Risks"
        columns={[
          { key: 'level', label: 'Level', render: (r) => <Status tone={LEVEL[r.level]}>{r.level}</Status> },
          { key: 'text', label: 'Risk', width: '34%' },
          { key: 'fix', label: 'Fix', width: '40%' },
          { key: 'cite', label: 'Source', render: (r) => cite(job, r.cite) },
        ]}
        rows={research.risks}
        rowKey={(r) => r.text}
      />
    ),
    pricing: () => (
      <Sheet
        label="Pricing"
        columns={[
          { key: 'phase', label: 'Phase' },
          { key: 'hours', label: 'Hours', align: 'right', render: (r) => (r.hours ? <span className="mono">{r.hours.toLocaleString('en-US')}</span> : null) },
          { key: 'rate', label: 'Rate', align: 'right', render: (r) => (r.rate ? <span className="mono">${r.rate}</span> : null) },
          { key: 'cost', label: 'Cost', align: 'right', render: (r) => <span className={`mono ${r.total ? 'strong' : ''}`}>{money(r.cost)}</span> },
        ]}
        rows={[
          ...research.pricing.phases.map((p) => ({ ...p, rate: RATE, cost: p.hours * RATE })),
          { phase: 'Total cost', hours: numbers.hours, cost: numbers.cost, total: true },
          { phase: 'Their budget', hours: 0, cost: job.value, total: true },
          { phase: 'Suggested price', hours: 0, cost: job.price, total: true },
        ]}
        rowKey={(r) => r.phase}
      />
    ),
    scoring: () => (
      <Sheet
        label="Scoring"
        columns={[
          { key: 'criterion', label: 'Criterion' },
          { key: 'points', label: 'Points', align: 'right', render: (r) => <span className="mono">{r.points}</span> },
          { key: 'estimate', label: 'Our estimate', align: 'right', render: (r) => <span className="mono">{r.estimate}</span> },
          { key: 'read', label: 'Why', width: '48%' },
        ]}
        rows={[...research.scoring.items, { criterion: 'Total', points: 100, estimate: numbers.score, read: <Cite job={job} cite={research.scoring.cite} /> }]}
        rowKey={(r) => r.criterion}
      />
    ),
    competition: () => (
      <Sheet
        label="Competition"
        columns={[
          { key: 'name', label: 'Firm' },
          { key: 'where', label: 'Based in' },
          { key: 'note', label: 'Note' },
        ]}
        rows={research.competition.planholders}
        rowKey={(r) => r.name}
      />
    ),
    dates: () => (
      <Sheet
        label="Dates and changes"
        columns={[
          { key: 'label', label: 'Event' },
          { key: 'value', label: 'Date or change' },
          { key: 'changed', label: 'Note' },
          { key: 'cite', label: 'Source', render: (r) => cite(job, r.cite) },
        ]}
        rows={[
          ...research.dates,
          ...changes.map((c) => ({ label: `${c.addendum}: ${c.what}`, value: `${c.before} → ${c.after}`, changed: 'Changed', cite: c.cite })),
          ...research.qa.map((q) => ({ label: `Q&A: ${q.q}`, value: q.a, changed: 'Answer', cite: q.cite })),
        ]}
        rowKey={(r) => r.label}
      />
    ),
    questions: () => (
      <Sheet
        label="Questions"
        columns={[
          { key: 'text', label: `Question for ${job.buyer}`, width: '46%' },
          { key: 'why', label: 'Why ask', width: '38%' },
          { key: 'cite', label: 'Source', render: (r) => cite(job, r.cite) },
        ]}
        rows={research.questions.list}
        rowKey={(r) => r.text}
      />
    ),
    sources: () => (
      <Sheet
        label="Sources"
        onRowClick={(row) => row.cites.length && show({ job, cite: row.cites[0] })}
        columns={[
          { key: 'title', label: 'Document' },
          { key: 'kind', label: 'Type' },
          { key: 'pages', label: 'Pages', align: 'right', render: (r) => <span className="mono">{r.pages}</span> },
          { key: 'from', label: 'From' },
          { key: 'date', label: 'Retrieved' },
          { key: 'used', label: 'Lines used', align: 'right', render: (r) => <span className="mono">{r.cites.length}</span> },
        ]}
        rows={Object.entries(research.sources).map(([key, doc]) => ({ ...doc, key, cites: bySource[key] ?? [] }))}
        rowKey={(r) => r.key}
      />
    ),
    log: () => (
      <Sheet label="Agent log" columns={[{ key: 'text', label: 'What the agent did' }]} rows={research.log} rowKey={(r) => r.text} />
    ),
  }

  return (
    <div className="research-sheets">
      <nav className="sheet-tabs" aria-label="Research sheets">
        {tabs.map((t) => (
          <button key={t.id} aria-current={t.id === tab ? 'page' : undefined} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>
      {sheets[tab]()}
    </div>
  )
}
