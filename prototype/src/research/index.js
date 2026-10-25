import { JOBS, PORTALS, RATE } from '../data'
import { generateResearch } from './generate'
import { kingCounty } from './kingCounty'
import { lakewood } from './lakewood'
import { postingFor } from './postings'
import { tacoma } from './tacoma'

const WRITTEN = { 'king-county': kingCounty, lakewood, tacoma }
const cache = new Map()

// Every bid's research also carries the posting it was found in, except bids found on the
// buyer's own website, where the RFP itself is the posting.
export function getResearch(job) {
  if (!cache.has(job.id)) {
    const index = JOBS.findIndex((j) => j.id === job.id)
    const research = WRITTEN[job.id] ?? generateResearch(job, index)
    const posting = PORTALS[job.source].posting === false ? {} : { posting: postingFor(job, research.sources.rfp.date) }
    cache.set(job.id, { ...research, sources: { ...research.sources, ...posting } })
  }
  return cache.get(job.id)
}

const SHORT_KIND = {
  rfp: 'RFP',
  attA: 'Att. A',
  attB: 'Att. B',
  scope: 'Scope',
  add1: 'Add. 1',
  add2: 'Add. 2',
  qa: 'Q&A',
  budget: 'County budget',
  council: 'Council resolution',
  ai: 'AI data terms',
  prior: '2019 award',
  planholders: 'Planholders',
  exclusions: 'SAM.gov',
  coi: 'Insurance',
  rates: 'Rate card',
}

export function citeLabel(cite, research) {
  const source = research.sources[cite.src]
  const short = source?.short ?? SHORT_KIND[cite.src] ?? source?.title.replace(' capability sheet', ' sheet') ?? cite.src
  const pages = research.sources[cite.src]?.pages ?? 1
  return pages > 1 ? `${short} p.${cite.page}` : short
}

export function tally(research) {
  const coverage = { meets: 0, partial: 0, gap: 0 }
  research.requirements.forEach((r) => coverage[r.coverage]++)
  const risks = { High: 0, Medium: 0, Low: 0 }
  research.risks.forEach((r) => risks[r.level]++)
  const score = research.scoring.items.reduce((sum, item) => sum + item.estimate, 0)
  const hours = research.pricing.phases.reduce((sum, p) => sum + p.hours, 0)
  return { coverage, risks, score, hours, cost: hours * RATE, requirements: research.requirements.length }
}

export function eligibilityStatus(row, progress, job) {
  if (row.status !== 'answer') return row.status
  if (!progress.answer) return 'unknown'
  const option = job.question.options.find((o) => o.id === progress.answer)
  return option.risk ? 'gap' : 'pass'
}

// Every citation in the research, grouped by the document it points to.
export function citationsBySource(research) {
  const found = []
  const visit = (value) => {
    if (Array.isArray(value)) value.forEach(visit)
    else if (value && typeof value === 'object') {
      if (typeof value.src === 'string' && typeof value.quote === 'string') found.push(value)
      else Object.values(value).forEach(visit)
    }
  }
  visit(research)
  const bySource = {}
  for (const cite of found) {
    const key = `${cite.page}|${cite.quote}`
    bySource[cite.src] ??= new Map()
    bySource[cite.src].set(key, cite)
  }
  return Object.fromEntries(Object.entries(bySource).map(([src, map]) => [src, [...map.values()].sort((a, b) => a.page - b.page)]))
}

export function researchProgress(research, step) {
  const shown = research.log.slice(0, step)
  return shown.reduce(
    (totals, entry) => ({
      pages: totals.pages + (entry.adds?.pages ?? 0),
      requirements: totals.requirements + (entry.adds?.requirements ?? 0),
      sources: totals.sources + (entry.adds?.sources ?? 0),
    }),
    { pages: 0, requirements: 0, sources: 0 },
  )
}
