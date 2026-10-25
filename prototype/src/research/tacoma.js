import { UPLOADS, bash, driveRead, fetchPage, grep, note, read, search, write } from '../agent/calls'

const rfp = (page, section, quote) => ({ src: 'rfp', page, section, quote })
const scope = (page, section, quote) => ({ src: 'scope', page, section, quote })

export const tacoma = {
  sources: {
    rfp: { title: 'RFP TAC-CSC-26-031', kind: 'Solicitation', pages: 35, from: 'Email from City of Tacoma Purchasing', date: 'Oct 20' },
    scope: { title: 'Exhibit A: Scope of Services', kind: 'Solicitation', pages: 9, from: 'Email from City of Tacoma Purchasing', date: 'Oct 20' },
    add1: { title: 'Addendum 1', kind: 'Addendum', pages: 1, from: 'City of Tacoma bid site', date: 'Oct 22' },
    planholders: { title: 'Planholders list', kind: 'Portal record', pages: 1, from: 'City of Tacoma bid site', date: 'Oct 25' },
    council: { title: 'Council resolution 41207', kind: 'Public record', pages: 3, from: 'cityoftacoma.org', date: 'Oct 25' },
    purlpal: { title: 'PURLPal capability sheet', kind: 'Cadocary file', pages: 2, from: 'Cadocary shared drive', date: 'Aug 2026' },
    ai: { title: 'AI vendor data terms', kind: 'Cadocary file', pages: 2, from: 'Cadocary shared drive', date: 'Jul 2026' },
    coi: { title: 'Certificate of insurance', kind: 'Cadocary file', pages: 1, from: 'Cadocary shared drive', date: 'Jan 2026' },
    rates: { title: 'Rate card 2026', kind: 'Cadocary file', pages: 1, from: 'Cadocary shared drive', date: 'Jan 2026' },
  },

  overview: [
    { label: 'Solicitation', value: 'RFP TAC-CSC-26-031', cite: rfp(1, 'Cover', 'Request for Proposals TAC-CSC-26-031: 311 Resident Help Assistant.') },
    { label: 'Buyer', value: 'City of Tacoma, Customer Support Center', cite: rfp(1, 'Cover', 'Issued by the City of Tacoma Customer Support Center (Tacoma FIRST 311).') },
    { label: 'What they are buying', value: 'An assistant that answers resident questions from city information and hands hard ones to staff', cite: rfp(4, '1.3 Purpose', 'The City seeks an automated assistant that answers resident questions using City information and transfers unresolved requests to 311 staff.') },
    { label: 'Contract', value: 'Fixed price. 1-year base, two 1-year options', cite: rfp(6, '2.2 Term', 'The term shall be one (1) year with two (2) optional one-year renewals.') },
    { label: 'Budget', value: '$95,000 approved by City Council', cite: { src: 'council', page: 2, section: 'Section 1', quote: 'Authorizing an amount not to exceed $95,000 for a 311 resident assistance tool.' } },
    { label: 'Go-live', value: 'Within 4 months of signing', cite: rfp(7, '2.4 Schedule', 'The solution shall be available to residents within four (4) months of contract execution.') },
  ],

  dates: [
    { label: 'RFP released', value: 'Tue, Oct 20', cite: rfp(3, '1.4 Schedule', 'RFP issued: October 20, 2026.') },
    { label: 'Questions due', value: 'Tue, Nov 3 · 5:00 PM', cite: rfp(3, '1.4 Schedule', 'Written questions due: November 3, 2026, 5:00 PM.') },
    { label: 'Proposals due', value: 'Tue, Nov 17 · 4:00 PM', cite: rfp(3, '1.4 Schedule', 'Proposals due: November 17, 2026, 4:00 PM Pacific.') },
    { label: 'Interviews', value: 'Week of Dec 7, top 3 only', cite: rfp(3, '1.4 Schedule', 'Interviews with up to three (3) finalists: week of December 7, 2026.') },
  ],

  addenda: [
    {
      title: 'Addendum 1',
      date: 'Oct 22',
      changes: [{ what: 'Languages', before: 'English required, Spanish desired', after: 'English and Spanish both required', cite: { src: 'add1', page: 1, section: 'Change 1', quote: 'Section A.2 is revised: the assistant shall support both English and Spanish.' } }],
    },
  ],

  qa: [],

  requirements: [
    { id: 'R1', text: 'Answer resident questions from City web pages and documents, and show the source', kind: 'Must', coverage: 'meets', evidence: 'PURLPal answers from a large, changing document set and cites the page it used.', cite: scope(2, 'A.1', 'The assistant shall answer questions using City web content and documents, and shall identify the source of each answer.'), evidenceCite: { src: 'purlpal', page: 1, section: 'Overview', quote: 'Answers questions from plan documents and cites the exact source passage.' } },
    { id: 'R2', text: 'Work in English and Spanish', kind: 'Must', coverage: 'partial', evidence: 'The AI model handles Spanish well, but PURLPal has only been tested in English. About 40 hours with native-speaker review.', cite: { src: 'add1', page: 1, section: 'Change 1', quote: 'Section A.2 is revised: the assistant shall support both English and Spanish.' } },
    { id: 'R3', text: 'Hand unresolved questions to a 311 agent, with the conversation attached', kind: 'Must', coverage: 'partial', evidence: 'Hand-off exists in PURLPal by email. Connecting to the City\'s 311 case system is about 80 hours.', cite: scope(4, 'A.4', 'Unresolved requests shall be transferred to a 311 agent with the full conversation attached.') },
    { id: 'R4', text: 'Never answer emergencies or legal questions; send residents to 911 or staff', kind: 'Must', coverage: 'meets', evidence: 'PURLPal already refuses and redirects out-of-scope questions.', cite: scope(5, 'A.6', 'The assistant shall not provide legal advice and shall direct emergencies to 911.'), evidenceCite: { src: 'purlpal', page: 2, section: 'Guardrails', quote: 'Out-of-scope and sensitive questions are refused and routed to a human.' } },
    { id: 'R5', text: 'Meet WCAG 2.1 AA accessibility', kind: 'Must', coverage: 'meets', evidence: 'PURLPal\'s chat widget passed an accessibility review in 2026.', cite: rfp(14, '4.5 Accessibility', 'The solution shall conform to WCAG 2.1 Level AA.'), evidenceCite: { src: 'purlpal', page: 2, section: 'Accessibility', quote: 'Chat widget conforms to WCAG 2.1 AA (external review, March 2026).' } },
    { id: 'R6', text: 'Send a weekly report of top and unanswered questions', kind: 'Must', coverage: 'meets', evidence: 'Weekly question reports are built in.', cite: scope(6, 'A.8', 'The Contractor shall provide a weekly report of the most frequent and unanswered questions.') },
    { id: 'R7', text: 'Offer text messaging as a channel', kind: 'Nice to have', coverage: 'partial', evidence: 'Not built. About 30 hours with a standard texting service.', cite: scope(7, 'A.9', 'It is desirable that residents can reach the assistant by text message.') },
    { id: 'R8', text: 'Keep resident data in the US, and never use it to train AI models', kind: 'Must', coverage: 'meets', evidence: 'Cadocary\'s AI vendor terms already prohibit training on customer data.', cite: rfp(16, '5.1 Data', 'Resident data shall remain in the United States and shall not be used to train any artificial intelligence model.'), evidenceCite: { src: 'ai', page: 1, section: 'Data use', quote: 'Customer inputs and outputs are not used to train models.' } },
  ],

  eligibility: [
    { item: 'Washington business license', required: 'Active license', ours: 'Active', status: 'pass', cite: rfp(11, '4.1', 'Proposers shall hold a current Washington State business license.') },
    { item: 'Tacoma business license', required: 'Before contract signing', ours: 'Not yet', status: 'gap', cite: rfp(11, '4.1', 'The selected Contractor shall obtain a City of Tacoma business license prior to contract execution.') },
    { item: 'General liability insurance', required: '$1M per occurrence', ours: '$1M', status: 'pass', cite: rfp(12, '4.3', 'Commercial general liability insurance of not less than $1,000,000 per occurrence.'), oursCite: { src: 'coi', page: 1, section: 'Coverages', quote: 'General liability: $1,000,000 each occurrence.' } },
    { item: 'Cyber liability insurance', required: '$1M', ours: '$1M', status: 'pass', cite: rfp(12, '4.3', 'Cyber liability insurance of not less than $1,000,000.'), oursCite: { src: 'coi', page: 1, section: 'Coverages', quote: 'Cyber liability: $1,000,000 aggregate.' } },
    { item: 'References', required: '3, similar work', ours: 'DocketBot, SpendLogic, PURLPal', status: 'pass', cite: rfp(18, '6.2', 'Provide three (3) references for similar work.') },
  ],

  scoring: {
    cite: rfp(20, '7.1 Evaluation', 'Proposals will be scored on a 100-point scale: Proposed Solution 40, Experience 20, Price 25, Accessibility and Language Access 10, Local Business 5.'),
    items: [
      { criterion: 'Proposed solution', points: 40, estimate: 34, read: 'PURLPal is close to what they describe. The 311 hand-off is the gap.' },
      { criterion: 'Experience', points: 20, estimate: 16, read: 'PURLPal is directly relevant. Three solid references.' },
      { criterion: 'Price', points: 25, estimate: 20, read: 'At $93,500 we are just under the approved amount.' },
      { criterion: 'Accessibility and language', points: 10, estimate: 7, read: 'Accessibility is proven. Spanish needs testing before we claim it.' },
      { criterion: 'Local business', points: 5, estimate: 5, read: 'Washington-based. Full points expected.' },
    ],
  },

  competition: {
    cite: { src: 'planholders', page: 1, section: 'Planholders', quote: '7 firms have downloaded RFP TAC-CSC-26-031 as of October 25, 2026.' },
    planholders: [
      { name: 'Bluewater Digital', where: 'Seattle, WA', note: 'Builds city websites.' },
      { name: 'Olympic Systems Group', where: 'Olympia, WA' },
      { name: 'Rainier Analytics', where: 'Tacoma, WA', note: 'Local. Data work, not chat.' },
      { name: 'Columbia Civic Tech', where: 'Vancouver, WA' },
      { name: 'Lakeside Software', where: 'Kirkland, WA' },
      { name: 'Granite Peak IT', where: 'Spokane, WA' },
      { name: 'Cadocary', where: 'Washington', note: 'You.' },
    ],
    incumbent: { text: 'None. Residents call or use a web form today.', cite: rfp(2, '1.2 Background', 'Residents currently reach Tacoma FIRST 311 by phone or an online request form.') },
    history: [],
    read: 'No one on the list has shipped a document-answering assistant like PURLPal. Bluewater knows the City but builds websites.',
  },

  pricing: {
    budget: { text: '$95,000 approved by Council', cite: { src: 'council', page: 2, section: 'Section 1', quote: 'Authorizing an amount not to exceed $95,000 for a 311 resident assistance tool.' } },
    signals: [{ text: 'The Council amount is a hard ceiling: "not to exceed."', cite: { src: 'council', page: 2, section: 'Section 1', quote: 'Authorizing an amount not to exceed $95,000.' } }],
    phases: [
      { phase: 'Load City content and set up', hours: 90 },
      { phase: 'English and Spanish answers, tested', hours: 140 },
      { phase: 'Hand-off to the 311 case system', hours: 80 },
      { phase: 'Accessibility check and launch', hours: 60 },
      { phase: 'Weekly reports and tuning, year one', hours: 150 },
    ],
    rateCite: { src: 'rates', page: 1, section: 'Blended rate', quote: 'Blended project rate: $175 per hour.' },
  },

  risks: [
    { level: 'Medium', text: 'Spanish is now required, and PURLPal has only been tested in English.', fix: 'Budget 40 hours with a native-speaker reviewer, and show test results in the proposal.', cite: { src: 'add1', page: 1, section: 'Change 1', quote: 'Section A.2 is revised: the assistant shall support both English and Spanish.' } },
    { level: 'Medium', text: 'Hand-off to the 311 case system is not built.', fix: 'Ask which system they use (question 1 below). 80 hours are in the estimate.', cite: scope(4, 'A.4', 'Unresolved requests shall be transferred to a 311 agent with the full conversation attached.') },
    { level: 'Low', text: 'Need a Tacoma business license before signing.', fix: 'Online application, about a week. Start it if we win.', cite: rfp(11, '4.1', 'The selected Contractor shall obtain a City of Tacoma business license prior to contract execution.') },
    { level: 'Low', text: 'Thin margin: the budget is a hard cap.', fix: 'Price at $93,500, and keep text messaging as a separate option.', cite: { src: 'council', page: 2, section: 'Section 1', quote: 'Authorizing an amount not to exceed $95,000.' } },
  ],

  questions: {
    due: 'Tue, Nov 3 · 5:00 PM',
    list: [
      { text: 'Which system do 311 agents use for cases, and does it accept transfers through an API?', why: 'The hand-off is 80 hours if there is an API, and much more if not.', cite: scope(4, 'A.4', 'Unresolved requests shall be transferred to a 311 agent with the full conversation attached.') },
      { text: 'Will the City provide a list of documents the assistant may use, or should it use all public City web pages?', why: 'Decides how much content we load and keep current.', cite: scope(2, 'A.1', 'The assistant shall answer questions using City web content and documents.') },
    ],
  },

  log: [
    {
      text: 'Read the RFP email from City of Tacoma Purchasing and saved the attachments',
      adds: { sources: 2 },
      calls: [
        read('email_TAC-CSC-26-031.eml', 'From City of Tacoma Purchasing. Subject: RFP TAC-CSC-26-031, 311 Resident Help Assistant. 2 attachments: RFP (35 pages), Exhibit A (9 pages).'),
        bash(`cd ${UPLOADS} && munpack email_TAC-CSC-26-031.eml`, '2 files saved: TAC-CSC-26-031_RFP.pdf, Exhibit_A.pdf', 2),
      ],
    },
    {
      text: 'Read the RFP, all 35 pages',
      adds: { pages: 35 },
      calls: [
        bash(`pdftotext -layout ${UPLOADS}/TAC-CSC-26-031_RFP.pdf -`, '35 pages of text, 15,730 words.', 5),
        note('A 1-year contract with two renewals. The assistant must answer from City information and hand hard questions to 311 staff. Proposals are due November 17 at 4:00 PM.'),
      ],
    },
    {
      text: 'Read Exhibit A, the scope of services',
      adds: { pages: 9, requirements: 8 },
      calls: [
        bash(`pdftotext -layout ${UPLOADS}/Exhibit_A.pdf -`, '9 pages of text, 3,120 words.', 2),
        grep('shall|must|desirable', 'Exhibit_A.pdf', '8 requirements: 7 required, 1 nice to have.'),
      ],
    },
    {
      text: 'Found Addendum 1: Spanish is now required',
      adds: { sources: 1, pages: 1 },
      calls: [
        fetchPage('https://cityoftacoma.org/purchasing/bids/TAC-CSC-26-031', 'Bid page for TAC-CSC-26-031. Addendum 1 posted October 22.'),
        note('Addendum 1 makes Spanish a requirement. It was a nice-to-have in the original.'),
      ],
    },
    {
      text: 'Matched 8 requirements against the PURLPal capability sheet',
      adds: { sources: 2 },
      calls: [
        driveRead('PURLPal capability sheet.pdf', '2 pages: answers from documents, nightly data refresh, hand-off by email.'),
        driveRead('AI vendor data terms.pdf', '2 pages: no training on customer data, US data residency.'),
        note('5 of 8 are already built. Spanish testing, the 311 hand-off, and text messaging are the work.'),
      ],
    },
    {
      text: 'Checked insurance and licenses: Tacoma license needed before signing',
      adds: { sources: 1 },
      calls: [driveRead('Certificate of insurance 2026.pdf', 'General liability: $1,000,000 each occurrence. Cyber liability: $1,000,000 aggregate.')],
    },
    {
      text: 'Pulled the planholders list: 7 firms',
      adds: { sources: 1 },
      calls: [fetchPage('https://cityoftacoma.org/purchasing/bids/TAC-CSC-26-031/planholders', '7 firms have the documents.')],
    },
    {
      text: 'Found the Council resolution capping the budget at $95,000',
      adds: { sources: 1 },
      calls: [
        search('Tacoma City Council resolution 311 resident assistance tool 2026', [['Resolution 41207', 'https://cityoftacoma.org/council/resolutions/41207']]),
        fetchPage('https://cityoftacoma.org/council/resolutions/41207', 'Section 1: authorizing an amount not to exceed $95,000 for a 311 resident assistance tool.'),
      ],
    },
    {
      text: 'Built a 520-hour estimate from the rate card',
      adds: { sources: 1 },
      calls: [
        driveRead('Rate card 2026.pdf', 'Blended project rate: $175 per hour.'),
        bash('python3 estimate.py --rate 175 --phases phases.json', '5 phases, 520 hours, $91,000 at $175 an hour.'),
      ],
    },
    { text: 'Scored Cadocary against the 5 evaluation criteria', calls: [bash('python3 score.py --criteria rfp_section_6.json', 'Total 82 of 100.')] },
    { text: 'Drafted 2 questions for the City, due Nov 3', calls: [note('Two questions for the City: which 311 system the hand-off connects to, and whether text messaging is required in year one.')] },
    {
      text: 'Wrote the decision brief: 4 risks, none blocking',
      calls: [write('decision_brief.md', 'Saved decision_brief.md, 2 pages.'), note('Recommendation: bid. Nothing blocks it.')],
    },
  ],
  questionAt: null,

  verdict: {
    title: 'Bid',
    text: 'Nothing blocks the bid. The open work is Spanish testing and the hand-off to 311 staff.',
  },
}
