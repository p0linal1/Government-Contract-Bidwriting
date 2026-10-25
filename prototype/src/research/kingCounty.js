import { UPLOADS, bash, driveRead, driveSearch, fetchPage, grep, note, read, search, write } from '../agent/calls'

const PORTAL = 'https://kingcounty.gov/procurement/solicitations'

const rfp = (page, section, quote) => ({ src: 'rfp', page, section, quote })
const attA = (page, section, quote) => ({ src: 'attA', page, section, quote })

export const kingCounty = {
  sources: {
    rfp: { title: 'RFP KC-DPD-2026-114', kind: 'Solicitation', pages: 60, from: 'King County supplier portal', date: 'Oct 25' },
    attA: { title: 'Attachment A: Functional Requirements', kind: 'Solicitation', pages: 14, from: 'King County supplier portal', date: 'Oct 25' },
    attB: { title: 'Attachment B: Price Form, version 2', kind: 'Solicitation', pages: 3, from: 'King County supplier portal', date: 'Oct 25' },
    add1: { title: 'Addendum 1', kind: 'Addendum', pages: 1, from: 'King County supplier portal', date: 'Oct 19' },
    add2: { title: 'Addendum 2', kind: 'Addendum', pages: 2, from: 'King County supplier portal', date: 'Oct 23' },
    qa: { title: 'Questions and Answers, round 1', kind: 'Addendum', pages: 4, from: 'King County supplier portal', date: 'Oct 24' },
    planholders: { title: 'Planholders list', kind: 'Portal record', pages: 1, from: 'King County supplier portal', date: 'Oct 25' },
    budget: { title: '2025–2026 Adopted Budget, Department of Public Defense', kind: 'Public record', pages: 112, from: 'kingcounty.gov', date: 'Oct 25' },
    prior: { title: 'Contract 5612 award notice (2019)', kind: 'Public record', pages: 2, from: 'King County procurement records', date: 'Oct 25' },
    exclusions: { title: 'SAM.gov exclusions search', kind: 'Public record', pages: 1, from: 'sam.gov', date: 'Oct 25' },
    docketbot: { title: 'DocketBot capability sheet', kind: 'Cadocary file', pages: 3, from: 'Cadocary shared drive', date: 'Sep 2026' },
    coi: { title: 'Certificate of insurance', kind: 'Cadocary file', pages: 1, from: 'Cadocary shared drive', date: 'Jan 2026' },
    rates: { title: 'Rate card 2026', kind: 'Cadocary file', pages: 1, from: 'Cadocary shared drive', date: 'Jan 2026' },
  },

  overview: [
    { label: 'Solicitation', value: 'RFP KC-DPD-2026-114', cite: rfp(1, 'Cover', 'Request for Proposals KC-DPD-2026-114: Public Defense Case Management System.') },
    { label: 'Buyer', value: 'King County Department of Public Defense', cite: rfp(1, 'Cover', 'Issued by the King County Department of Public Defense, Seattle, Washington.') },
    { label: 'What they are buying', value: 'One system for intake, conflicts, court dates, caseloads, and client contact', cite: rfp(5, '1.3 Purpose', 'The Department seeks a single case management system supporting client intake, conflict checks, court calendaring, caseload management, and client contact.') },
    { label: 'Replacing', value: 'A Microsoft Access database built in 2009', cite: rfp(2, '1.2 Background', 'The Department currently uses an internally developed Microsoft Access database implemented in 2009.') },
    { label: 'Contract', value: 'Fixed price. 2-year base, three 1-year options', cite: rfp(6, '2.4 Term', 'The initial term shall be two (2) years with up to three (3) one-year extensions at the County\'s option.') },
    { label: 'Budget', value: '$300,000 for the base term', cite: { src: 'budget', page: 47, section: 'DPD technology', quote: 'Case management system replacement: $300,000 (one-time, 2026).' } },
    { label: 'Go-live', value: 'By September 1, 2027', cite: rfp(7, '2.6 Schedule', 'The system shall be in production use by all four divisions no later than September 1, 2027.') },
    { label: 'How to submit', value: 'Online through the supplier portal', cite: rfp(10, '4.1 Submission', 'Proposals must be submitted electronically through the King County supplier portal. Emailed proposals will not be accepted.') },
  ],

  dates: [
    { label: 'RFP released', value: 'Mon, Oct 12', cite: rfp(3, '1.5 Schedule', 'RFP issued: October 12, 2026.') },
    { label: 'Pre-proposal meeting', value: 'Thu, Oct 22 · 10:00 AM, online', changed: 'Moved online by Addendum 1', cite: { src: 'add1', page: 1, section: 'Change 1', quote: 'The pre-proposal meeting will be held on Microsoft Teams. The in-person session at the Chinook Building is cancelled.' } },
    { label: 'Questions due', value: 'Sat, Oct 31 · 5:00 PM', changed: 'Was Oct 28. Moved by Addendum 2', cite: { src: 'add2', page: 1, section: 'Change 1', quote: 'The deadline for written questions is extended to October 31, 2026 at 5:00 PM Pacific.' } },
    { label: 'Answers posted', value: 'Fri, Nov 6', cite: rfp(3, '1.5 Schedule', 'Answers to written questions posted: November 6, 2026.') },
    { label: 'Proposals due', value: 'Sat, Nov 14 · 2:00 PM', unconfirmed: true, cite: rfp(3, '1.5 Schedule', 'Proposals due: November 14, 2026, 2:00 PM Pacific.') },
    { label: 'Award expected', value: 'Tue, Dec 15', cite: rfp(3, '1.5 Schedule', 'Anticipated contract award: December 15, 2026.') },
  ],

  addenda: [
    {
      title: 'Addendum 1',
      date: 'Oct 19',
      changes: [{ what: 'Pre-proposal meeting', before: 'In person, Chinook Building', after: 'Online, Microsoft Teams', cite: { src: 'add1', page: 1, section: 'Change 1', quote: 'The pre-proposal meeting will be held on Microsoft Teams.' } }],
    },
    {
      title: 'Addendum 2',
      date: 'Oct 23',
      changes: [
        { what: 'Questions deadline', before: 'Oct 28, 5:00 PM', after: 'Oct 31, 5:00 PM', cite: { src: 'add2', page: 1, section: 'Change 1', quote: 'The deadline for written questions is extended to October 31, 2026 at 5:00 PM Pacific.' } },
        { what: 'Price form', before: 'Attachment B, version 1', after: 'Version 2 adds a line for annual support', cite: { src: 'add2', page: 2, section: 'Change 2', quote: 'Attachment B is replaced in its entirety by Attachment B version 2, which adds a line item for annual support and maintenance.' } },
      ],
    },
  ],

  qa: [
    { q: 'Is a cloud-hosted solution acceptable?', a: 'Yes, if it meets the CJIS Security Policy and all data stays in the United States.', cite: { src: 'qa', page: 1, section: 'Q3', quote: 'A cloud-hosted solution is acceptable provided it complies with the CJIS Security Policy and all data remains within the United States.' } },
    { q: 'Will the County provide API access to the court calendar?', a: 'No. The County will send a nightly CSV file export instead.', cite: { src: 'qa', page: 2, section: 'Q7', quote: 'API access to the court calendar is not available. The County will provide a nightly file export in CSV format.' } },
    { q: 'Is $300,000 the budget ceiling?', a: 'The County will not disclose a ceiling. Price is scored as described in Section 7.', cite: { src: 'qa', page: 3, section: 'Q11', quote: 'The County will not disclose a budget ceiling. Price will be evaluated as described in Section 7.' } },
  ],

  requirements: [
    { id: 'R1', text: 'Create a client record from a court appointment in under 5 minutes', kind: 'Must', coverage: 'meets', evidence: 'DocketBot creates the client straight from the appointment order.', cite: attA(2, 'A.1', 'The system shall allow staff to create a client record from a court appointment in under five (5) minutes.'), evidenceCite: { src: 'docketbot', page: 1, section: 'Intake', quote: 'Intake: create a client and case from an appointment order in one step.' } },
    { id: 'R2', text: 'Check conflicts against all current and past clients before assignment', kind: 'Must', coverage: 'meets', evidence: 'DocketBot checks name, date of birth, and case number against every past client.', cite: attA(2, 'A.2', 'The system shall perform a conflict check against all current and former clients prior to attorney assignment.'), evidenceCite: { src: 'docketbot', page: 1, section: 'Conflicts', quote: 'Conflict checks run on name, date of birth, and case number across all historical clients.' } },
    { id: 'R3', text: 'Sync hearing dates from the court calendar daily', kind: 'Must', coverage: 'partial', evidence: 'DocketBot imports municipal court dates. King County sends a nightly CSV (see Q&A), which is a new but simple import.', cite: attA(4, 'B.1', 'The system shall update hearing dates from the court\'s calendar at least daily.'), evidenceCite: { src: 'docketbot', page: 2, section: 'Calendaring', quote: 'Calendar import supports municipal court feeds. Other formats by configuration.' } },
    { id: 'R4', text: 'Show each attorney\'s caseload, weighted by Washington standards', kind: 'Must', coverage: 'meets', evidence: 'DocketBot\'s caseload view already uses Washington weighting.', cite: attA(5, 'B.4', 'The system shall display weighted caseloads per attorney consistent with Washington State standards for indigent defense.'), evidenceCite: { src: 'docketbot', page: 2, section: 'Caseloads', quote: 'Caseload dashboard with weighting per Washington standards for indigent defense.' } },
    { id: 'R5', text: 'Log every client contact: calls, texts, and jail visits', kind: 'Must', coverage: 'meets', evidence: 'Contact log with timestamps is built in.', cite: attA(6, 'C.1', 'The system shall record all client contacts, including calls, text messages, and jail visits, with date and time.'), evidenceCite: { src: 'docketbot', page: 2, section: 'Client contact', quote: 'Contact log records calls, texts, and visits with timestamps.' } },
    { id: 'R6', text: 'Text clients court reminders in English and Spanish', kind: 'Nice to have', coverage: 'partial', evidence: 'Reminders are English only today. Spanish templates are about 20 hours.', cite: attA(6, 'C.3', 'It is desirable that the system send automated court date reminders to clients by text message in English and Spanish.'), evidenceCite: { src: 'docketbot', page: 3, section: 'Reminders', quote: 'Automated text reminders (English).' } },
    { id: 'R7', text: 'Separate access for attorneys, investigators, social workers, and supervisors', kind: 'Must', coverage: 'meets', evidence: 'Role-based access is built in.', cite: attA(8, 'D.1', 'The system shall provide role-based access for attorneys, investigators, social workers, and supervisors.'), evidenceCite: { src: 'docketbot', page: 3, section: 'Security', quote: 'Role-based permissions with custom roles.' } },
    { id: 'R8', text: 'Keep an audit log of every view and edit for 7 years', kind: 'Must', coverage: 'meets', evidence: 'Audit log exists. Retention is a setting.', cite: attA(8, 'D.3', 'The system shall log every view and modification of client data and retain the log for seven (7) years.'), evidenceCite: { src: 'docketbot', page: 3, section: 'Security', quote: 'Full audit trail of reads and writes, configurable retention.' } },
    { id: 'R9', text: 'Comply with the FBI CJIS Security Policy', kind: 'Must', coverage: 'gap', evidence: 'Not documented. DocketBot runs on standard cloud hosting. Needs CJIS controls written up and hosting moved.', cite: rfp(18, '5.2 Security', 'The Contractor shall comply with the FBI Criminal Justice Information Services (CJIS) Security Policy for all criminal justice information.'), evidenceCite: { src: 'docketbot', page: 3, section: 'Hosting', quote: 'Hosted on AWS, us-west-2 region. Encrypted at rest and in transit.' } },
    { id: 'R10', text: 'Move about 41,000 client records from the old system', kind: 'Must', coverage: 'partial', evidence: 'Cadocary has migrated spreadsheets, not Access. About 120 hours.', cite: attA(10, 'E.1', 'The Contractor shall migrate approximately 41,000 client records from the existing database.') },
    { id: 'R11', text: 'Train 210 staff across 4 offices', kind: 'Must', coverage: 'meets', evidence: 'Office-by-office training plan, 220 hours budgeted.', cite: attA(12, 'F.1', 'The Contractor shall train approximately 210 staff across four (4) divisions.') },
    { id: 'R12', text: 'Work on attorneys\' phones in court', kind: 'Nice to have', coverage: 'meets', evidence: 'DocketBot is built for phones first.', cite: attA(12, 'F.4', 'It is desirable that attorneys can access case information from mobile devices in court.'), evidenceCite: { src: 'docketbot', page: 1, section: 'Overview', quote: 'Mobile-first: built for attorneys between hearings.' } },
    { id: 'R13', text: 'Produce quarterly reports for the State Office of Public Defense', kind: 'Must', coverage: 'partial', evidence: 'Report templates exist for municipal courts. The State format is new, about 30 hours.', cite: attA(13, 'G.2', 'The system shall produce quarterly reports in the format required by the Washington State Office of Public Defense.') },
  ],

  eligibility: [
    { item: 'Washington business license', required: 'Active license', ours: 'Active', status: 'pass', cite: rfp(11, '4.1', 'Proposers shall hold a current Washington State business license.') },
    { item: 'General liability insurance', required: '$1M per occurrence', ours: '$1M', status: 'pass', cite: rfp(11, '4.2.1', 'Commercial general liability insurance of not less than $1,000,000 per occurrence.'), oursCite: { src: 'coi', page: 1, section: 'Coverages', quote: 'General liability: $1,000,000 each occurrence.' } },
    { item: 'Cyber liability insurance', required: '$2M, before contract signing', ours: '$1M', status: 'gap', cite: rfp(12, '4.2.3', 'Cyber liability insurance of not less than $2,000,000, to be in effect prior to contract execution.'), oursCite: { src: 'coi', page: 1, section: 'Coverages', quote: 'Cyber liability: $1,000,000 aggregate.' } },
    { item: 'CJIS compliance', required: 'Documented controls', ours: 'Not documented', status: 'gap', cite: rfp(18, '5.2', 'The Contractor shall comply with the FBI Criminal Justice Information Services (CJIS) Security Policy for all criminal justice information.') },
    { item: 'References', required: '3, similar work, last 5 years', ours: '2 strong', status: 'answer', cite: rfp(22, '6.3', 'Provide three (3) references for projects of similar scope completed within the last five (5) years.') },
    { item: 'Not debarred', required: 'No federal exclusions', ours: 'None found', status: 'pass', cite: rfp(11, '4.4', 'Proposers shall not be debarred or suspended from public contracting.'), oursCite: { src: 'exclusions', page: 1, section: 'Results', quote: 'No active exclusions found for Cadocary LLC.' } },
  ],

  scoring: {
    cite: rfp(24, '7.1 Evaluation', 'Proposals will be scored on a 100-point scale: Technical Approach 35, Experience and References 25, Price 25, Implementation and Training Plan 10, Small or Local Business 5.'),
    items: [
      { criterion: 'Technical approach', points: 35, estimate: 29, read: '8 of 13 requirements already built. CJIS is the weak spot.' },
      { criterion: 'Experience and references', points: 25, estimate: 18, read: 'Two strong references. The third decides this.' },
      { criterion: 'Price', points: 25, estimate: 21, read: 'Strong if we stay under $300,000. Larger vendors usually price higher.' },
      { criterion: 'Implementation and training', points: 10, estimate: 9, read: 'Office-by-office rollout matches what Section F asks for.' },
      { criterion: 'Small or local business', points: 5, estimate: 5, read: 'Full points if Cadocary is registered as a small business with the County.' },
    ],
  },

  competition: {
    count: 10,
    cite: { src: 'planholders', page: 1, section: 'Planholders', quote: '10 firms have downloaded solicitation KC-DPD-2026-114 as of October 25, 2026.' },
    planholders: [
      { name: 'Northwind Justice Systems', where: 'Dallas, TX', note: 'National. Bigger, pricier.' },
      { name: 'Cascade Case Software', where: 'Seattle, WA', note: 'Won a related DPD contract in 2019.' },
      { name: 'Summit Legal Technologies', where: 'Denver, CO', note: 'National.' },
      { name: 'Pioneer GovTech', where: 'Portland, OR' },
      { name: 'Evergreen Data Partners', where: 'Tacoma, WA' },
      { name: 'Harborline Consulting', where: 'Seattle, WA', note: 'Consultancy. May team with a software vendor.' },
      { name: 'Ridgeview Software', where: 'Boise, ID' },
      { name: 'Two independent consultants', where: 'Washington' },
      { name: 'Cadocary', where: 'Washington', note: 'You.' },
    ],
    incumbent: { text: 'No outside vendor. The current system was built in-house in 2009.', cite: rfp(2, '1.2 Background', 'The Department currently uses an internally developed Microsoft Access database implemented in 2009.') },
    history: [{ text: 'Cascade Case Software won Contract 5612 in 2019: a $164,000 records module for the same department.', cite: { src: 'prior', page: 1, section: 'Award', quote: 'Contract 5612 awarded to Cascade Case Software, Seattle, WA. Amount: $164,000. Scope: client records module.' } }],
    read: 'Cascade is the one to watch: local, and it has worked with this department before. The national vendors usually price above this budget.',
  },

  pricing: {
    budget: { text: '$300,000 budgeted for the base term', cite: { src: 'budget', page: 47, section: 'DPD technology', quote: 'Case management system replacement: $300,000 (one-time, 2026).' } },
    signals: [
      { text: 'The County will not disclose a ceiling. Price is worth 25 points.', cite: { src: 'qa', page: 3, section: 'Q11', quote: 'The County will not disclose a budget ceiling. Price will be evaluated as described in Section 7.' } },
      { text: 'A smaller module for the same department went for $164,000 in 2019.', cite: { src: 'prior', page: 1, section: 'Award', quote: 'Amount: $164,000. Scope: client records module.' } },
      { text: 'Price form version 2 adds a separate line for annual support.', cite: { src: 'add2', page: 2, section: 'Change 2', quote: 'Attachment B version 2 adds a line item for annual support and maintenance.' } },
    ],
    phases: [
      { phase: 'Discovery and setup', hours: 180 },
      { phase: 'Configure intake, conflicts, caseloads', hours: 320 },
      { phase: 'Court calendar import (nightly CSV)', hours: 260 },
      { phase: 'Move 41,000 records', hours: 120 },
      { phase: 'CJIS controls and hosting', hours: 160 },
      { phase: 'Training, 4 offices', hours: 220 },
      { phase: 'Year-one support', hours: 140 },
    ],
    rateCite: { src: 'rates', page: 1, section: 'Blended rate', quote: 'Blended project rate: $175 per hour.' },
  },

  risks: [
    { level: 'High', text: 'Cyber insurance is $1M. The RFP requires $2M.', fix: 'Only needed before contract signing, not to submit. Ask the broker now: a limit increase usually takes 1 to 2 weeks.', cite: rfp(12, '4.2.3', 'Cyber liability insurance of not less than $2,000,000, to be in effect prior to contract execution.') },
    { level: 'High', text: 'CJIS compliance is not documented.', fix: 'Write up the controls and move hosting to a CJIS-ready environment. 160 hours are already in the estimate.', cite: rfp(18, '5.2', 'The Contractor shall comply with the FBI CJIS Security Policy for all criminal justice information.') },
    { level: 'Medium', text: 'Only 2 strong references. Experience is worth 25 points.', fix: 'Pick the strongest third reference before writing Section 6.', cite: rfp(22, '6.3', 'Provide three (3) references for projects of similar scope completed within the last five (5) years.') },
    { level: 'Medium', text: 'Court calendar comes as a nightly file, not live.', fix: 'Simpler than an API. Attorneys see changes the next morning, so say that plainly in the proposal.', cite: { src: 'qa', page: 2, section: 'Q7', quote: 'API access to the court calendar is not available. The County will provide a nightly file export in CSV format.' } },
    { level: 'Low', text: '20-page limit is tight for 13 requirements.', fix: 'Answer requirements in a table, one row each. Saves about 4 pages.', cite: rfp(9, '4.3 Format', 'Proposals exceeding twenty (20) pages, or using a font smaller than 11 point, will not be evaluated.') },
    { level: 'Low', text: 'Spanish text reminders are wanted but not built.', fix: 'It is a nice-to-have. Offer it as a 20-hour option.', cite: attA(6, 'C.3', 'It is desirable that the system send automated court date reminders to clients by text message in English and Spanish.') },
  ],

  questions: {
    due: 'Sat, Oct 31 · 5:00 PM',
    list: [
      { text: 'Should hosting for the 2-year base term be priced inside the base price, or on the new annual support line in Attachment B version 2?', why: 'Hosting is about $14,000 over two years. Putting it on the wrong line could cost points or margin.', cite: { src: 'attB', page: 2, section: 'Line items', quote: 'Line 4: Annual support and maintenance (per year).' } },
      { text: 'Will the nightly court calendar file include hearing type and courtroom, or only dates?', why: 'Without hearing type and courtroom, attorneys still check the court site by hand, and the calendar sync stays partly built.', cite: { src: 'qa', page: 2, section: 'Q7', quote: 'The County will provide a nightly file export in CSV format.' } },
      { text: 'Can CJIS compliance be shown through a vendor attestation, or is a third-party audit required before award?', why: 'An audit adds 4 to 6 weeks and real cost. An attestation we can do now.', cite: rfp(18, '5.2', 'The Contractor shall comply with the FBI CJIS Security Policy for all criminal justice information.') },
    ],
  },

  log: [
    {
      text: 'Downloaded the RFP and Attachments A and B from the King County supplier portal',
      adds: { sources: 3 },
      calls: [
        fetchPage(`${PORTAL}/KC-DPD-2026-114`, 'Solicitation KC-DPD-2026-114, Public Defense Case Management System. Documents: RFP (60 pages), Attachment A (14 pages), Attachment B version 2 (3 pages). Notices: Addendum 1, Addendum 2, Questions and Answers round 1.'),
        bash(`cd ${UPLOADS} && curl -sSO ${PORTAL}/KC-DPD-2026-114/KC-DPD-2026-114_RFP.pdf -O ${PORTAL}/KC-DPD-2026-114/Attachment_A.pdf -O ${PORTAL}/KC-DPD-2026-114/Attachment_B_v2.pdf`, '3 files saved: KC-DPD-2026-114_RFP.pdf, Attachment_A.pdf, Attachment_B_v2.pdf', 6),
      ],
    },
    {
      text: 'Read RFP pages 1 to 20: purpose, term, schedule, proposal format',
      adds: { pages: 20 },
      calls: [
        bash(`pdftotext -f 1 -l 20 -layout ${UPLOADS}/KC-DPD-2026-114_RFP.pdf -`, '20 pages of text, 9,412 words.', 4),
        note('Fixed price: a 2-year base with three 1-year options. Proposals are due November 14 at 2:00 PM, through the supplier portal only. The page limit is 20, at 11 point or larger.'),
      ],
    },
    {
      text: 'Read RFP pages 21 to 60: eligibility, insurance, security, scoring',
      adds: { pages: 40 },
      calls: [
        bash(`pdftotext -f 21 -l 60 -layout ${UPLOADS}/KC-DPD-2026-114_RFP.pdf -`, '40 pages of text, 18,206 words.', 6),
        grep('insurance|liability|CJIS', 'KC-DPD-2026-114_RFP.pdf', '9 matches: pages 11, 12, and 18.'),
        note('Cyber liability must be $2M before contract signing. The system must meet the FBI CJIS Security Policy. Scoring is on page 24: technical 35, experience 25, price 25, implementation 10, small business 5.'),
      ],
    },
    {
      text: 'Found Addenda 1 and 2 and compared every change against the original',
      adds: { sources: 2, pages: 3 },
      calls: [
        bash(`cd ${UPLOADS} && curl -sSO ${PORTAL}/KC-DPD-2026-114/Addendum_1.pdf -O ${PORTAL}/KC-DPD-2026-114/Addendum_2.pdf -O ${PORTAL}/KC-DPD-2026-114/QA_Round_1.pdf`, '3 files saved: Addendum_1.pdf, Addendum_2.pdf, QA_Round_1.pdf', 3),
        read('Addendum_2.pdf', 'Change 1: written questions now due October 31, 5:00 PM. Change 2: Attachment B replaced by version 2, adding a line for annual support. Schedule table reissued.'),
        note('Addendum 2 reissued the schedule table. The proposal deadline still reads November 14, but the owner should confirm it on the portal.'),
      ],
    },
    {
      text: 'Read the first round of questions and answers. 3 of 14 answers affect us',
      adds: { sources: 1, pages: 4 },
      calls: [
        read('QA_Round_1.pdf', '14 questions and answers, 4 pages.'),
        note('Three answers matter. Q3: cloud hosting is fine if it meets CJIS. Q7: no live calendar connection, only a nightly CSV file. Q11: the County will not disclose a budget ceiling.'),
      ],
    },
    {
      text: 'Pulled 13 requirements out of Attachment A and Section 3',
      adds: { requirements: 13, pages: 14 },
      calls: [
        bash(`pdftotext -layout ${UPLOADS}/Attachment_A.pdf -`, '14 pages of text, 4,880 words.', 3),
        grep('shall|desirable', 'Attachment_A.pdf', '13 requirements: 11 marked "shall", 2 marked "desirable".'),
      ],
    },
    {
      text: 'Matched every requirement against the DocketBot capability sheet',
      adds: { sources: 1 },
      calls: [
        driveSearch('DocketBot capability sheet', '1 file: DocketBot capability sheet.pdf, updated Sep 2026.'),
        driveRead('DocketBot capability sheet.pdf', '3 pages: intake, conflicts, calendaring, caseloads, client contact, security, hosting.'),
        note('8 of the 13 requirements are already built in DocketBot. 4 are partly built. CJIS compliance is not documented anywhere in the files.'),
      ],
    },
    {
      text: 'Checked references against Section 6.3: found 2 that qualify',
      calls: [
        driveSearch('reference letters past projects', '6 reference letters and 14 past bids.'),
        note('DocketBot and SpendLogic qualify as similar work in the last 5 years. PURLPal is the closest third, but it is Medicare plan search. The owner should pick.'),
      ],
    },
    {
      text: 'Checked the insurance certificate against Section 4.2: cyber limit is short',
      adds: { sources: 1 },
      calls: [driveRead('Certificate of insurance 2026.pdf', 'General liability: $1,000,000 each occurrence. Cyber liability: $1,000,000 aggregate.')],
    },
    {
      text: 'Searched federal exclusions for Cadocary: none',
      adds: { sources: 1 },
      calls: [fetchPage('https://sam.gov/search/?index=ex&keywords=Cadocary%20LLC', 'Exclusions search for "Cadocary LLC": 0 active exclusions.')],
    },
    {
      text: 'Pulled the planholders list: 10 firms have the documents',
      adds: { sources: 1 },
      calls: [fetchPage(`${PORTAL}/KC-DPD-2026-114/planholders`, '10 firms have downloaded the solicitation, including Cascade Case Software (Seattle), Northwind Justice Systems (Dallas), and Harborline Consulting (Seattle).')],
    },
    {
      text: 'Searched County procurement records: found a related 2019 award',
      adds: { sources: 1 },
      calls: [
        search('King County Department of Public Defense case management contract award 2019', [
          ['Contract 5612 award notice', 'https://kingcounty.gov/procurement/awards/5612'],
          ['Department of Public Defense technology projects', 'https://kingcounty.gov/dpd/technology'],
          ['Cascade Case Software: King County client records', 'https://cascadecase.com/clients'],
        ]),
        fetchPage('https://kingcounty.gov/procurement/awards/5612', 'Contract 5612 awarded to Cascade Case Software, Seattle, WA. Amount: $164,000. Scope: client records module.'),
      ],
    },
    {
      text: 'Found the $300,000 line in the adopted County budget',
      adds: { sources: 1 },
      calls: [
        search('King County 2025-2026 adopted budget Department of Public Defense case management', [
          ['2025-2026 Adopted Budget, Department of Public Defense', 'https://kingcounty.gov/budget/2025-2026/dpd.pdf'],
          ['King County budget book 2025-2026', 'https://kingcounty.gov/budget/2025-2026'],
        ]),
        fetchPage('https://kingcounty.gov/budget/2025-2026/dpd.pdf', 'Page 47, DPD technology: case management system replacement, $300,000 (one-time, 2026).', 7),
      ],
    },
    {
      text: 'Built a 1,400-hour estimate from the 2026 rate card',
      adds: { sources: 1 },
      calls: [
        driveRead('Rate card 2026.pdf', 'Blended project rate: $175 per hour.'),
        bash('python3 estimate.py --rate 175 --phases phases.json', '7 phases, 1,400 hours, $245,000 at $175 an hour.'),
      ],
    },
    {
      text: 'Scored Cadocary against the 5 evaluation criteria',
      calls: [bash('python3 score.py --criteria rfp_section_7.json', 'Technical 29 of 35, experience 18 of 25, price 21 of 25, implementation 9 of 10, small business 5 of 5. Total 82 of 100.')],
    },
    {
      text: 'Drafted 3 questions for the County, due Oct 31',
      calls: [note('Three questions for the County: which price line hosting belongs on, what the nightly calendar file contains, and whether CJIS can be shown by attestation instead of an audit.')],
    },
    {
      text: 'Wrote the decision brief: 6 risks, 2 to fix before contract signing',
      calls: [
        write('decision_brief.md', 'Saved decision_brief.md, 2 pages.'),
        note('Recommendation: bid. Cyber insurance and CJIS controls must be fixed before contract signing, and both fit in the schedule.'),
      ],
    },
  ],
  questionAt: 8,

  verdict: {
    title: 'Bid',
    text: 'Cyber insurance and CJIS controls must be fixed before contract signing. Both fit in the schedule.',
  },
}
