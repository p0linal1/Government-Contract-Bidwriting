import { money } from './data'

export function sections(job) {
  const sizes = {
    need: Math.max(1, Math.floor(job.pageLimit * 0.15)),
    approach: Math.max(2, Math.floor(job.pageLimit * 0.35)),
    past: Math.max(1, Math.floor(job.pageLimit * 0.15)),
  }
  const written = job.sections ?? [
    {
      title: 'Cover letter',
      draft: `${job.buyer} wants a ${job.title.toLowerCase()}. Cadocary has built this kind of tool before with ${job.product ?? 'PURLPal'}. We propose a fixed-price build, delivered in phases, with your staff signing off on each one.`,
      revised: `Short version: we have built this before, and we would bring it to ${job.buyer} at a fixed price, one phase at a time.`,
    },
    {
      title: `What ${job.buyer} needs`,
      draft: `The RFP lists its requirements in an attachment. We answer each one in the order ${job.buyer} listed them, in a table, so evaluators can score us line by line.`,
      revised: 'One table, one row per requirement, in the order they were asked. Easy to score.',
    },
    {
      title: 'How we will do it',
      draft: 'Phases with sign-off. Set it up for your team, connect it to the systems you already use, then train staff and support them from day one.',
      revised: 'One phase at a time, and each phase goes live only after your staff sign off on it.',
    },
    {
      title: 'References',
      draft: 'DocketBot, SpendLogic, and PURLPal: three places where Cadocary turned document-heavy work into a few clicks.',
      revised: 'Three past projects, each a document-heavy process Cadocary turned into a few clicks.',
    },
  ]
  const pages = [1, sizes.need, sizes.approach, sizes.past]
  return written.map((section, i) => ({ ...section, pages: section.pages ?? pages[i] }))
}

// Bids with a separate price sheet add one page for it.
export const totalPages = (job) => sections(job).reduce((sum, section) => sum + section.pages, 0) + (job.priceSheet === false ? 0 : 1)

export function reviewItems(job, progress) {
  const chosen = job.question?.options.find((o) => o.id === progress.answer)
  return [
    { label: 'Length', value: `${totalPages(job)} of ${job.pageLimit} pages${job.priceSheet === false ? '' : ', with the price sheet'}` },
    { label: 'Font', value: 'All text 11 point or larger' },
    { label: 'Forms', value: job.forms ? `Forms 1 to ${job.forms} filled in` : 'None required' },
    { label: 'References', value: chosen?.risk ? `Flagged: ${chosen.risk}` : 'Included' },
    { label: 'Deadline', value: job.due },
    { label: 'Price', value: progress.price ?? money(job.price) },
  ]
}
