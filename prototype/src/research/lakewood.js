import { bash, driveRead, driveSearch, fetchPage, grep, note, read, write } from '../agent/calls'
import { LAKEWOOD_PAGES } from './lakewoodPages'

// A real RFP: the City of Lakewood, WA, posted it on October 7, 2024. Every quote below is
// copied word for word from that document. Cadocary's side (files, fit, estimate) is sample data.
const RFP_URL = 'https://cityoflakewood.us/wp-content/uploads/2024/10/2024-10-07-AI-Research-RFP.pdf'
const rfp = (page, section, quote) => ({ src: 'rfp', page, section, quote })

export const lakewood = {
  sources: {
    rfp: {
      title: 'RFP for Generative Artificial Intelligence Research Tool',
      kind: 'Solicitation',
      pages: 5,
      from: 'City of Lakewood website',
      date: 'Oct 7, 2024',
      text: LAKEWOOD_PAGES,
      original: RFP_URL,
    },
    purlpal: { title: 'PURLPal capability sheet', kind: 'Cadocary file', pages: 2, from: 'Cadocary shared drive', date: 'Aug 2026' },
    spendlogic: { title: 'SpendLogic capability sheet', kind: 'Cadocary file', pages: 2, from: 'Cadocary shared drive', date: 'Jun 2026' },
    rates: { title: 'Rate card 2026', kind: 'Cadocary file', pages: 1, from: 'Cadocary shared drive', date: 'Jan 2026' },
  },

  overview: [
    { label: 'What they are buying', value: 'An AI tool that researches laws and codes for permit review', cite: rfp(1, '1.1 Summary', 'The City seeks to develop a generative artificial intelligence (AI) application to assist staff in researching applicable federal, state and local municipal laws, codes, rules and design manuals as part of the project permit review process.') },
    { label: 'Why', value: 'Faster answers to residents and faster staff reports', cite: rfp(1, '1.1 Summary', 'This tool is intended to improve efficiencies by reducing time necessary to prepare responses to customers on development project feasibility and associated requirements, as well as assist in the development of staff reports, letters and public notices.') },
    { label: 'Buyer', value: 'City of Lakewood, WA. About 2,000 permits a year', cite: rfp(1, '1.1 Summary', 'The City of Lakewood, WA serves a population of 63,000 people with an average permit volume close to 2,000 permits annually.') },
    { label: 'Budget', value: '$30,000, not counting ongoing fees', cite: rfp(4, '1.8 Budget', 'This does not include monthly or annual fees following implementation.') },
    { label: 'Paid for by', value: 'A state grant for digital permitting', cite: rfp(1, '1.2 Background', 'This grant program assists local governments in updating their permitting system through the Paper to Digital Permitting Grant Program.') },
    { label: 'Must finish by', value: 'June 15, 2025. No extensions', cite: rfp(2, '1.2 Background', 'Deadline to complete work is no later than June 15, 2025. No exceptions to this deadline as work is intended to be grant funded.') },
    { label: 'Proposals due', value: 'Oct 25, 2024 · 5:00 PM, by email', cite: rfp(2, '1.5 Timeline', 'Deadline for Receiving Proposals October 25, 2024 by 5:00 PM PST') },
    { label: 'Proposal length', value: 'Up to 20 pages', cite: rfp(3, '1.5 Instructions', 'Proposals shall not to exceed 20 pages and include at minimum:') },
  ],

  dates: [
    { label: 'RFP released', value: 'Mon, Oct 7, 2024', cite: rfp(2, '1.5 Timeline', 'RFP Release Date October 7, 2024') },
    { label: 'Questions due', value: 'Fri, Oct 18, 2024', cite: rfp(2, '1.5 Timeline', 'Question Submission Deadline October 18, 2024') },
    { label: 'Proposals due', value: 'Fri, Oct 25, 2024 · 5:00 PM', cite: rfp(2, '1.5 Timeline', 'Deadline for Receiving Proposals October 25, 2024 by 5:00 PM PST') },
    { label: 'Demonstrations', value: 'Nov 4 to 8, 2024, if asked', cite: rfp(2, '1.5 Timeline', 'Possible Demonstrations Schedule November 4-8, 2024') },
    { label: 'Award', value: 'Tue, Nov 12, 2024', cite: rfp(2, '1.5 Timeline', 'Notice of Award/Contract Negotiations November 12, 2024') },
    { label: 'Work finished', value: 'Sun, Jun 15, 2025', cite: rfp(4, '1.8 Budget', 'A successful firm will be awarded based on ability to deliver the scope of the project within budget and grant schedule, no later than June 15, 2025.') },
  ],

  addenda: [],
  qa: [],

  requirements: [
    { id: 'R1', text: 'Run fully in the cloud, with nothing on City servers', kind: 'Must', coverage: 'meets', evidence: 'PURLPal is hosted by Cadocary. The City installs nothing.', cite: rfp(1, '1.2 Background', 'We seek a tool that does not require additional City network server needs or housed on the City server.'), evidenceCite: { src: 'purlpal', page: 1, section: 'Hosting', quote: 'Fully hosted. Customers sign in from a browser.' } },
    { id: 'R2', text: 'Search federal and state law, agency rules, the Lakewood Municipal Code, and design manuals', kind: 'Must', coverage: 'partial', evidence: 'PURLPal searches plan documents today. Loading these sources is new work, about 48 hours.', cite: rfp(1, '1.2 Background', 'This search tool will draw off of applicable federal and state laws, agency rulemaking, Lakewood Municipal Codes, as well as adopted design and engineering manuals.'), evidenceCite: { src: 'purlpal', page: 1, section: 'Sources', quote: 'Answers questions over large document sets, kept current by a nightly pipeline.' } },
    { id: 'R3', text: 'Update the sources when rules are adopted or amended', kind: 'Nice to have', coverage: 'meets', evidence: "PURLPal's nightly pipeline already refreshes its documents.", cite: rfp(1, '1.2 Background', 'Validity, reliability and ability to update data sources as rules are adopted or amended is strongly desired.'), evidenceCite: { src: 'purlpal', page: 1, section: 'Sources', quote: 'Answers questions over large document sets, kept current by a nightly pipeline.' } },
    { id: 'R4', text: 'Staff review every answer before official use', kind: 'Must', coverage: 'meets', evidence: 'Answers are drafts by design. A review step is a setting.', cite: rfp(1, '1.2 Background', 'Outputs of this AI tool must also be reviewed by City personnel prior to be used in an official capacity.') },
    { id: 'R5', text: 'Cite the source for every answer', kind: 'Must', coverage: 'meets', evidence: 'Every PURLPal answer links to the passage it came from.', cite: rfp(1, '1.2 Background', 'Ensure prompts and outputs reference data sources and appropriate citations.'), evidenceCite: { src: 'purlpal', page: 2, section: 'Answers', quote: 'Every answer cites the document and page it came from.' } },
    { id: 'R6', text: 'Keep every answer for the Public Records Act', kind: 'Must', coverage: 'partial', evidence: 'PURLPal keeps answers for 90 days. Permanent retention and export is about 16 hours.', cite: rfp(1, '1.2 Background', 'Outputs must also be retained to ensure compliance with the Washington State Public Records Act (Chapter 42.56 RCW).') },
    { id: 'R7', text: "Follow the City's IT and cybersecurity policies", kind: 'Must', coverage: 'partial', evidence: 'The policies are not attached to the RFP. Cadocary needs to see them.', cite: rfp(1, '1.2 Background', 'The AI tool must be consistent with the City’s Information Technology policies.') },
    { id: 'R8', text: 'Address data integrity, privacy, and copyright', kind: 'Must', coverage: 'meets', evidence: 'Covered by the standard Cadocary security write-up.', cite: rfp(1, '1.2 Background', 'Respondents need to address cybersecurity, data integrity, privacy protections and possible copyrights or trademarks if awarded.') },
    { id: 'R9', text: 'Fill research into staff report and notice templates', kind: 'Must', coverage: 'meets', evidence: 'SpendLogic already builds documents from templates. Same engine.', cite: rfp(1, '1.2 Background', 'The search tool should be able to populate the research into custom templates such as a staff report and notices.'), evidenceCite: { src: 'spendlogic', page: 1, section: 'Templates', quote: 'Builds finished documents from approved templates.' } },
    { id: 'R10', text: 'Train staff to use it', kind: 'Must', coverage: 'meets', evidence: 'Cadocary trains every client.', cite: rfp(4, '1.8 Scope of Work', 'Step 5.2 Train staff on use of AI application.') },
  ],

  eligibility: [
    { item: 'Submission', required: 'By email, electronic only', ours: 'Ready', status: 'pass', cite: rfp(3, '1.5 Instructions', 'Only electronic submittals will be accepted.') },
    { item: 'Proposal length', required: 'Up to 20 pages', ours: 'Planned at 15', status: 'pass', cite: rfp(3, '1.5 Instructions', 'Proposals shall not to exceed 20 pages and include at minimum:') },
    { item: 'References', required: 'Jurisdictions using similar software', ours: 'None for AI research', status: 'answer', cite: rfp(3, '1.5 Instructions', 'Reference list of jurisdictions with similar software services.') },
    { item: 'Litigation', required: 'Disclose the past 3 years', ours: 'None', status: 'pass', cite: rfp(3, '1.5 Instructions', 'Reference to any pending litigation or judgement rendered in the past three years.') },
  ],

  scoring: {
    cite: rfp(3, '1.7 Selection Criteria', 'Firms experience and response addressing the ability to perform major objectives of this RFP;'),
    items: [
      { criterion: 'Ability to meet the objectives', points: 20, estimate: 17, read: '7 of 10 requirements are already built. The RFP gives no points, so each criterion is weighted equally here.' },
      { criterion: 'Experience of the assigned team', points: 20, estimate: 16, read: 'The PURLPal team would do the work.' },
      { criterion: 'Recent generative AI research tools', points: 20, estimate: 17, read: 'PURLPal is exactly this, for a different kind of document.' },
      { criterion: 'On time and on budget record', points: 20, estimate: 16, read: 'Past bids archive shows on-time delivery.' },
      { criterion: 'Proposal, demo, and price', points: 20, estimate: 15, read: 'A live demo would help. Price must stay under $30,000.' },
    ],
  },

  competition: {
    count: null,
    cite: rfp(3, '1.5 Instructions', 'Only electronic submittals will be accepted.'),
    planholders: [],
    incumbent: null,
    history: [],
    read: 'Proposals go by email, so there is no public list of who else is bidding.',
  },

  pricing: {
    budget: { text: '$30,000 maximum, not counting ongoing fees', cite: rfp(4, '1.8 Budget', 'This does not include monthly or annual fees following implementation.') },
    signals: [
      { text: 'Ongoing subscription fees are outside the $30,000 and must be listed.', cite: rfp(3, '1.5 Instructions', 'Complete pricing for services related to the proposal including all one- time implementation fees and annual subscription fees.') },
      { text: 'Price must include Washington sales tax.', cite: rfp(5, '1.9 Compensation', 'inclusive of Washington State sales tax and any other applicable government charges.') },
    ],
    phases: [
      { phase: 'Discovery and source list', hours: 16 },
      { phase: 'Load laws, code, and manuals', hours: 48 },
      { phase: 'Citations and the review step', hours: 16 },
      { phase: 'Staff report and notice templates', hours: 32 },
      { phase: 'Records retention and security write-up', hours: 24 },
      { phase: 'Training and launch', hours: 16 },
    ],
    rateCite: { src: 'rates', page: 1, section: 'Blended rate', quote: 'Blended project rate: $175 per hour.' },
  },

  risks: [
    { level: 'High', text: 'June 15, 2025 cannot move. It is a grant deadline.', fix: 'Plan the internal launch for May, as the City suggests, with a month of buffer.', cite: rfp(2, '1.2 Background', 'Deadline to complete work is no later than June 15, 2025. No exceptions to this deadline as work is intended to be grant funded.') },
    { level: 'Medium', text: 'No government references for an AI research tool.', fix: 'List the public defender offices using DocketBot and explain why the work is similar.', cite: rfp(3, '1.5 Instructions', 'Reference list of jurisdictions with similar software services.') },
    { level: 'Medium', text: "The City's IT policies are not in the RFP.", fix: 'Ask for them before the question deadline.', cite: rfp(1, '1.2 Background', 'The AI tool must be consistent with the City’s Information Technology policies.') },
    { level: 'Medium', text: '$30,000 covers about 170 hours.', fix: 'Keep the build small. The annual subscription is priced separately.', cite: rfp(4, '1.8 Budget', 'This does not include monthly or annual fees following implementation.') },
    { level: 'Low', text: 'Keeping answers for public records is new for PURLPal.', fix: 'About 16 hours, already in the estimate.', cite: rfp(1, '1.2 Background', 'Outputs must also be retained to ensure compliance with the Washington State Public Records Act (Chapter 42.56 RCW).') },
  ],

  questions: {
    due: 'Fri, Oct 18, 2024',
    list: [
      { text: 'Can the City share the IT and cybersecurity policies the tool must follow?', why: 'The RFP requires them but does not attach them.', cite: rfp(1, '1.2 Background', 'The AI tool must be consistent with the City’s Information Technology policies.') },
      { text: 'Which design and engineering manuals come first, and are they digital or scanned?', why: 'Scanned manuals take longer to load.', cite: rfp(1, '1.2 Background', 'This search tool will draw off of applicable federal and state laws, agency rulemaking, Lakewood Municipal Codes, as well as adopted design and engineering manuals.') },
      { text: 'Should the annual subscription be listed separately from the $30,000?', why: 'The budget excludes ongoing fees, but the proposal must price them.', cite: rfp(4, '1.8 Budget', 'This does not include monthly or annual fees following implementation.') },
    ],
  },

  log: [
    {
      text: 'Downloaded the RFP from the City of Lakewood website',
      adds: { sources: 1 },
      calls: [
        fetchPage(RFP_URL, 'PDF, 5 pages: Request for Proposals (RFP) for Generative Artificial Intelligence Research Tool.'),
        bash(`curl -sSO ${RFP_URL}`, '1 file saved: 2024-10-07-AI-Research-RFP.pdf', 2),
      ],
    },
    {
      text: 'Read all 5 pages',
      adds: { pages: 5 },
      calls: [
        bash('pdftotext -layout 2024-10-07-AI-Research-RFP.pdf -', '5 pages of text, 1,469 words.', 2),
        note('Lakewood wants an AI tool that researches laws, city code, and design manuals for permit staff, with a citation on every answer. Budget is $30,000. Work must be done by June 15, 2025, because a state grant pays for it.'),
      ],
    },
    {
      text: 'Pulled 10 requirements out of Sections 1.2 and 1.8',
      adds: { requirements: 10 },
      calls: [grep('must|shall|should|strongly desired', '2024-10-07-AI-Research-RFP.pdf', '14 matches on pages 1 to 4. 10 distinct requirements.')],
    },
    {
      text: 'Matched every requirement against the PURLPal and SpendLogic capability sheets',
      adds: { sources: 2 },
      calls: [
        driveRead('PURLPal capability sheet.pdf', '2 pages: hosted, answers over large document sets, nightly refresh, citations on every answer.'),
        driveRead('SpendLogic capability sheet.pdf', '2 pages: builds finished documents from approved templates.'),
        note('7 of 10 are already built. Loading the law and code sources, records retention, and the City IT policies are the open work.'),
      ],
    },
    {
      text: 'Checked the proposal rules: 20 pages, email only, references, litigation',
      calls: [
        read('/mnt/session/uploads/2024-10-07-AI-Research-RFP.pdf', 'Section 1.5 lists 7 things the proposal must include.'),
        note('The City wants references from jurisdictions using similar software. Cadocary has none for an AI research tool. The owner should decide what to list.'),
      ],
    },
    {
      text: 'Checked for pending litigation in the past 3 years: none',
      calls: [driveSearch('litigation judgement', 'No files found.')],
    },
    {
      text: 'Built a 152-hour estimate from the rate card',
      adds: { sources: 1 },
      calls: [
        driveRead('Rate card 2026.pdf', 'Blended project rate: $175 per hour.'),
        bash('python3 estimate.py --rate 175 --phases phases.json', '6 phases, 152 hours, $26,600 at $175 an hour.'),
      ],
    },
    {
      text: 'Scored Cadocary against the 5 selection criteria',
      calls: [bash('python3 score.py --criteria rfp_section_1_7.json', 'No points given in the RFP. Weighted equally: 81 of 100.')],
    },
    {
      text: 'Drafted 3 questions for the City, due Oct 18',
      calls: [note('Three questions for the City: its IT policies, which manuals come first, and how to list the annual subscription.')],
    },
    {
      text: 'Wrote the decision brief: 5 risks, 1 high',
      calls: [
        write('decision_brief.md', 'Saved decision_brief.md, 2 pages.'),
        note('Recommendation: bid. The fit is strong. The hard parts are the fixed June 15 deadline and the thin budget.'),
      ],
    },
  ],
  questionAt: 5,

  verdict: {
    title: 'Bid',
    text: 'Strong fit with PURLPal. The June 15 deadline cannot move and the budget is thin, so keep the build small.',
  },
}
