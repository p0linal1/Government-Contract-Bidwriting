import { UPLOADS, bash, driveRead, fetchPage, grep, note, write } from '../agent/calls'

const VENDORS = [
  ['Northwind Justice Systems', 'Dallas, TX'],
  ['Cascade Case Software', 'Seattle, WA'],
  ['Pioneer GovTech', 'Portland, OR'],
  ['Evergreen Data Partners', 'Tacoma, WA'],
  ['Bluewater Digital', 'Seattle, WA'],
  ['Olympic Systems Group', 'Olympia, WA'],
  ['Rainier Analytics', 'Tacoma, WA'],
  ['Columbia Civic Tech', 'Vancouver, WA'],
  ['Lakeside Software', 'Kirkland, WA'],
  ['Granite Peak IT', 'Spokane, WA'],
  ['Puget Web Works', 'Everett, WA'],
  ['Harborline Consulting', 'Seattle, WA'],
  ['Ridgeview Software', 'Boise, ID'],
  ['Summit Legal Technologies', 'Denver, CO'],
]

const PORTAL_URLS = {
  WEBS: 'https://pr-webs-vendor.des.wa.gov/solicitations',
  FGA: 'https://fga.example.gov/solicitations',
  'Public Purchase': 'https://www.publicpurchase.com/gems/bid',
  Email: 'https://bids.cadocary.com/inbox',
}

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1)

// Builds research for jobs without a hand-written file, from the facts in data.js.
export function generateResearch(job, index) {
  const portal = PORTAL_URLS[job.source]
  const rfp = (page, section, quote) => ({ src: 'rfp', page, section, quote })
  const insurance = `$${job.insurance}M`
  const insuranceShort = job.insurance > 1

  const requirements = job.reqs.map(([text, kind, coverage, evidence], i) => ({
    id: `R${i + 1}`,
    text: capitalize(text),
    kind,
    coverage,
    evidence,
    cite: {
      src: 'scope',
      page: 2 + i,
      section: `A.${i + 1}`,
      quote: kind === 'Must' ? `The solution shall ${text}.` : `It is desirable that the solution ${text}.`,
    },
    evidenceCite: { src: 'capability', page: 1 + (i % 2), section: 'Capabilities', quote: evidence },
  }))

  const counts = { meets: 0, partial: 0, gap: 0 }
  requirements.forEach((r) => counts[r.coverage]++)
  const technical = Math.round(40 * ((counts.meets + counts.partial * 0.5) / requirements.length))

  const planholders = VENDORS.slice(index % 4, (index % 4) + job.competitors - 1)
    .map(([name, where]) => ({ name, where }))
    .concat({ name: 'Cadocary', where: 'Washington', note: 'You.' })

  const totalHours = job.hours
  const phases = [
    { phase: 'Discovery and setup', hours: Math.round(totalHours * 0.15) },
    { phase: `Build on ${job.product}`, hours: Math.round(totalHours * 0.45) },
    { phase: 'Integration and testing', hours: Math.round(totalHours * 0.2) },
    { phase: 'Training and launch', hours: Math.round(totalHours * 0.1) },
  ]
  phases.push({ phase: 'Year-one support', hours: totalHours - phases.reduce((sum, p) => sum + p.hours, 0) })

  const risks = requirements
    .filter((r) => r.coverage === 'gap')
    .map((r) => ({ level: 'High', text: `${r.text}: not something Cadocary has done.`, fix: r.evidence, cite: r.cite }))
  if (insuranceShort) {
    risks.push({
      level: 'High',
      text: `Liability insurance must be ${insurance}. Cadocary carries $1M.`,
      fix: 'Usually only needed before contract signing. Ask the broker for a quote now.',
      cite: rfp(11, '4.2', `Commercial general liability insurance of not less than ${insurance} per occurrence, prior to contract execution.`),
    })
  }
  requirements
    .filter((r) => r.coverage === 'partial' && r.kind === 'Must')
    .forEach((r) => risks.push({ level: 'Medium', text: `${r.text}: only partly built.`, fix: r.evidence, cite: r.cite }))
  risks.push({
    level: 'Low',
    text: `${job.pageLimit}-page limit.`,
    fix: 'Answer requirements in a table, one row each.',
    cite: rfp(9, '4.3 Format', `Proposals exceeding ${job.pageLimit} pages will not be evaluated.`),
  })

  const highRisks = risks.filter((r) => r.level === 'High').length
  const verdict =
    counts.gap > 0
      ? { title: 'Bid only if the gap can be closed', text: `${counts.gap} required item is something Cadocary has not built before.` }
      : highRisks > 0
        ? { title: 'Bid', text: `${highRisks} ${highRisks === 1 ? 'item' : 'items'} to fix before contract signing.` }
        : { title: 'Bid', text: 'Nothing blocks the bid.' }

  return {
    sources: {
      rfp: { title: `RFP ${job.solicitation}`, kind: 'Solicitation', pages: job.pages, from: job.source, date: 'Oct 25' },
      scope: { title: 'Attachment A: Scope of Work', kind: 'Solicitation', pages: 8, from: job.source, date: 'Oct 25' },
      planholders: { title: 'Planholders list', kind: 'Portal record', pages: 1, from: job.source, date: 'Oct 25' },
      capability: { title: `${job.product} capability sheet`, kind: 'Cadocary file', pages: 2, from: 'Cadocary shared drive', date: '2026' },
      coi: { title: 'Certificate of insurance', kind: 'Cadocary file', pages: 1, from: 'Cadocary shared drive', date: 'Jan 2026' },
      rates: { title: 'Rate card 2026', kind: 'Cadocary file', pages: 1, from: 'Cadocary shared drive', date: 'Jan 2026' },
    },
    overview: [
      { label: 'Solicitation', value: `RFP ${job.solicitation}`, cite: rfp(1, 'Cover', `Request for Proposals ${job.solicitation}: ${job.title}.`) },
      { label: 'Buyer', value: `${job.buyer}, ${job.agency}`, cite: rfp(1, 'Cover', `Issued by ${job.buyer}, ${job.agency}.`) },
      { label: 'What they are buying', value: job.title, cite: rfp(4, '1.3 Purpose', `${job.buyer} seeks a vendor to deliver a ${job.title.toLowerCase()}.`) },
      { label: 'Budget', value: `About ${'$' + job.value.toLocaleString('en-US')}`, cite: rfp(5, '2.1 Budget', `The estimated budget for this project is $${job.value.toLocaleString('en-US')}.`) },
      { label: 'Proposals due', value: job.due, cite: rfp(3, '1.4 Schedule', `Proposals due: ${job.due.replace(' · ', ', ')}.`) },
      { label: 'Page limit', value: `${job.pageLimit} pages`, cite: rfp(9, '4.3 Format', `Proposals exceeding ${job.pageLimit} pages will not be evaluated.`) },
    ],
    dates: [{ label: 'Proposals due', value: job.due, cite: rfp(3, '1.4 Schedule', `Proposals due: ${job.due.replace(' · ', ', ')}.`) }],
    addenda: [],
    qa: [],
    requirements,
    eligibility: [
      { item: 'Washington business license', required: 'Active license', ours: 'Active', status: 'pass', cite: rfp(11, '4.1', 'Proposers shall hold a current Washington State business license.') },
      {
        item: 'Liability insurance',
        required: `${insurance} per occurrence`,
        ours: '$1M',
        status: insuranceShort ? 'gap' : 'pass',
        cite: rfp(11, '4.2', `Commercial general liability insurance of not less than ${insurance} per occurrence, prior to contract execution.`),
        oursCite: { src: 'coi', page: 1, section: 'Coverages', quote: 'General liability: $1,000,000 each occurrence.' },
      },
      { item: 'References', required: '3, similar work', ours: 'DocketBot, SpendLogic, PURLPal', status: 'pass', cite: rfp(18, '6.2', 'Provide three (3) references for similar work.') },
    ],
    scoring: {
      cite: rfp(20, '7.1 Evaluation', 'Proposals will be scored on a 100-point scale: Technical 40, Experience 20, Price 30, Local Business 10.'),
      items: [
        { criterion: 'Technical', points: 40, estimate: technical, read: `${counts.meets} of ${requirements.length} requirements already built.` },
        { criterion: 'Experience', points: 20, estimate: 15, read: `${job.product} is directly relevant.` },
        { criterion: 'Price', points: 30, estimate: 24, read: 'Priced just under budget.' },
        { criterion: 'Local business', points: 10, estimate: 10, read: 'Washington-based.' },
      ],
    },
    competition: {
      count: job.competitors,
      cite: { src: 'planholders', page: 1, section: 'Planholders', quote: `${job.competitors} firms have downloaded ${job.solicitation} as of October 25, 2026.` },
      planholders,
      incumbent: null,
      history: [],
      read: job.competitors > 10 ? 'A crowded field. Expect price pressure.' : 'A manageable field.',
    },
    pricing: {
      budget: { text: `About ${'$' + job.value.toLocaleString('en-US')} budgeted`, cite: rfp(5, '2.1 Budget', `The estimated budget for this project is $${job.value.toLocaleString('en-US')}.`) },
      signals: [],
      phases,
      rateCite: { src: 'rates', page: 1, section: 'Blended rate', quote: 'Blended project rate: $175 per hour.' },
    },
    risks,
    questions: {
      due: 'One week before proposals',
      list: [
        {
          text: `Will ${job.buyer} accept a phased launch, with the first part live within 90 days?`,
          why: 'Lets us show results early and spread the risk.',
          cite: rfp(7, '2.4 Schedule', 'The Contractor shall propose an implementation schedule.'),
        },
      ],
    },
    log: [
      {
        text: `Downloaded RFP ${job.solicitation} and Attachment A from ${job.source}`,
        adds: { sources: 2 },
        calls: [
          fetchPage(`${portal}/${job.solicitation}`, `Solicitation ${job.solicitation}, ${job.title}. Documents: RFP (${job.pages} pages), Attachment A (8 pages).`),
          bash(`cd ${UPLOADS} && curl -sSO ${portal}/${job.solicitation}/RFP.pdf -O ${portal}/${job.solicitation}/Attachment_A.pdf`, '2 files saved: RFP.pdf, Attachment_A.pdf', 4),
        ],
      },
      {
        text: `Read the RFP, all ${job.pages} pages`,
        adds: { pages: job.pages },
        calls: [
          bash(`pdftotext -layout ${UPLOADS}/RFP.pdf -`, `${job.pages} pages of text.`, 5),
          note(`${job.buyer} wants a ${job.title.toLowerCase()}. Proposals are due ${job.due.replace(' · ', ' at ')}, with a ${job.pageLimit}-page limit.`),
        ],
      },
      {
        text: `Pulled ${requirements.length} requirements out of Attachment A`,
        adds: { requirements: requirements.length, pages: 8 },
        calls: [grep('shall|desirable', 'Attachment_A.pdf', `${requirements.length} requirements.`)],
      },
      {
        text: `Matched every requirement against the ${job.product} capability sheet`,
        adds: { sources: 1 },
        calls: [
          driveRead(`${job.product} capability sheet.pdf`, `2 pages describing what ${job.product} does today.`),
          note(`${counts.meets} of ${requirements.length} requirements are already built in ${job.product}.`),
        ],
      },
      {
        text: 'Checked licenses, insurance, and references',
        adds: { sources: 1 },
        calls: [driveRead('Certificate of insurance 2026.pdf', 'General liability: $1,000,000 each occurrence. Cyber liability: $1,000,000 aggregate.')],
      },
      {
        text: `Pulled the planholders list: ${job.competitors} firms`,
        adds: { sources: 1 },
        calls: [fetchPage(`${portal}/${job.solicitation}/planholders`, `${job.competitors} firms have the documents.`)],
      },
      {
        text: `Built a ${job.hours.toLocaleString('en-US')}-hour estimate from the rate card`,
        adds: { sources: 1 },
        calls: [
          driveRead('Rate card 2026.pdf', 'Blended project rate: $175 per hour.'),
          bash('python3 estimate.py --rate 175 --phases phases.json', `5 phases, ${job.hours.toLocaleString('en-US')} hours.`),
        ],
      },
      { text: 'Scored Cadocary against the evaluation criteria', calls: [bash('python3 score.py --criteria rfp_section_7.json', 'Scored against 4 criteria.')] },
      {
        text: `Wrote the decision brief: ${risks.length} risks`,
        calls: [write('decision_brief.md', 'Saved decision_brief.md.'), note(`Recommendation: ${verdict.title.toLowerCase()}. ${verdict.text}`)],
      },
    ],
    questionAt: job.question ? 4 : null,
    verdict,
  }
}
