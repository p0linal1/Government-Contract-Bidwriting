// What the bid agent asks Doug, in the order he answers them. Most are one tap. The answers are
// saved by question id, so an id never changes once Doug may have answered it.

export const QUESTIONS = [
  {
    id: 'records',
    kind: 'one',
    title: 'We found these in public records. Are they right?',
    facts: [
      ['Formed', 'October 10, 2024, as a Washington LLC'],
      ['Business license (UBI)', '605 623 739'],
      ['Who signs', 'You, the only governor on the state record'],
      ['SAM.gov', 'Active, last updated August 5, 2026'],
      ['Set-asides', 'Small business, no SBA certifications'],
      ['Government contracts', 'None found, federal, state, or local'],
    ],
    options: ['All correct', "Something's off"],
    noteWhen: "Something's off",
    notePrompt: "What's off?",
  },
  { id: 'range', kind: 'one', title: 'When you say $1 million to $5 million, do you mean:', options: ['The total contract, all years', 'Per year', 'Either is fine'] },
  {
    id: 'small',
    kind: 'one',
    title: 'Most Washington prosecutor and public defender systems cost $80,000 to $500,000. Should the agent bring you those?',
    help: 'Only jail systems and the biggest counties pass $1 million.',
    options: ['Yes, show me those too', 'Only if they could lead to bigger work', 'No, $1 million and up only'],
  },
  { id: 'military', kind: 'one', title: "Would you bid ordinary IT work for a military office, such as a case system for a base's legal office?", options: ['Yes', 'No'] },
  { id: 'va', kind: 'one', title: 'Is Veterans Affairs work OK?', options: ['Yes', 'No'] },
  {
    id: 'partner',
    kind: 'one',
    title: "Would you team up with a bigger vendor on a deal you can't win alone?",
    help: 'For example Karpel, Journal Technologies, or Tyler. They win most Washington deals today.',
    options: ['Yes', 'Maybe, depends on the deal', 'No'],
  },
  {
    id: 'recent',
    kind: 'grid',
    title: 'Would you bid on these Washington deals?',
    rows: [
      ['bothell', 'Bothell', 'Prosecutor case system, closed July 2026'],
      ['kennewick', 'Kennewick', 'Police records and jail system, closed September 2026'],
      ['king', 'King County Prosecutor', 'Civil case system, closed October 2025'],
      ['kitsap-jail', 'Kitsap County jail', 'Jail system, about $1.1 million. Contract ends November 30, 2026, no RFP yet'],
    ],
    options: ['Would bid', 'Would pass', 'Not sure'],
    notePrompt: 'Why? A few words is plenty.',
  },
  { id: 'portals', kind: 'many', title: 'Which bid sites are you already registered on?', options: ['WEBS (Washington)', 'Public Purchase', 'OpenGov', 'BidNet Direct', 'MRSC Rosters', 'None yet'] },
  { id: 'bidkit', kind: 'one', title: "Can the team have bidkit's code? Never the saved logins.", options: ["Yes, I'll send it", "Let's talk first", 'No'] },
  { id: 'alerts', kind: 'text', title: 'Which email address gets your bid alerts?', placeholder: 'name@example.com', input: 'email' },
  {
    id: 'pastbids',
    kind: 'one',
    title: 'Have you sent government bids before?',
    options: ['Yes', 'No'],
    sendWhen: 'Yes',
    send: "Easiest: email Sheffield any past proposals, won or lost. We'll read them so you don't have to type.",
  },
  {
    id: 'insurance',
    kind: 'many',
    title: 'Which insurance do you carry?',
    options: ['General liability', 'Professional (errors and omissions)', 'Cyber', 'Auto', "Workers' comp", 'None', 'Not sure'],
    send: 'Easiest: ask your insurance agent for a certificate of insurance and email it to Sheffield. It has every limit and date we need.',
  },
  { id: 'certs', kind: 'many', title: 'Do you hold any of these?', options: ['Washington minority- or women-owned (OMWBE)', 'SOC 2 security audit', 'Applied for one', 'None'] },
  {
    id: 'checks',
    kind: 'one',
    title: "Could everyone who'd touch a buyer's data pass an FBI fingerprint background check?",
    help: 'Criminal justice buyers usually require it.',
    options: ['Yes', 'No', 'Not sure'],
  },
  { id: 'policies', kind: 'one', title: 'Do you have written security policies?', options: ['Yes', 'No', 'Not sure'] },
  {
    id: 'hosting',
    kind: 'one',
    title: 'If a buyer wants it hosted, where would it run?',
    options: ['AWS GovCloud', 'Azure Government', 'Regular AWS, Azure, or Google Cloud', "On the buyer's own servers", 'Not sure'],
  },
  { id: 'users', kind: 'one', title: 'About how many attorneys use DocketBot and ClientCheck today?', options: ['None yet', '1 to 10', '11 to 50', 'More than 50'] },
  { id: 'name-users', kind: 'one', title: 'Can a bid name any of the offices that use them?', options: ['Yes', 'Ask me first each time', 'No'] },
  {
    id: 'clients',
    kind: 'grid',
    title: 'Can a government bid name these clients?',
    rows: [
      ['spendlogic', 'SpendLogic', ''],
      ['hotels4truckers', 'Hotels4Truckers', ''],
      ['purlpal', 'PURLPal', ''],
    ],
    options: ['Yes', 'Ask them first', 'No'],
  },
  {
    id: 'references',
    kind: 'grid',
    title: 'Will your contact at each one speak for you as a reference?',
    rows: [
      ['spendlogic', 'SpendLogic', ''],
      ['hotels4truckers', 'Hotels4Truckers', ''],
      ['purlpal', 'PURLPal', ''],
    ],
    options: ['Yes', "I'd need to ask", 'No'],
  },
  {
    id: 'team',
    kind: 'one',
    title: 'How many people would work on a contract?',
    options: ['Just me', '2 or 3', '4 to 10', 'More than 10'],
    send: 'If you have resumes handy, email them to Sheffield.',
  },
  { id: 'rate', kind: 'money', title: "What's your typical hourly rate?", placeholder: '150', suffix: 'an hour' },
  { id: 'floor', kind: 'money', title: "What's the smallest total contract you'd take?", placeholder: '250,000', suffix: 'total' },
  { id: 'seats', kind: 'one', title: 'For a government office, DocketBot and ClientCheck would be:', options: ['$30 a user a month, same as now', 'One price for the whole office', "Let's discuss"] },
  {
    id: 'earlier',
    kind: 'one',
    title: 'Is there work from before October 2024, under another name, that counts as experience?',
    options: ['Yes', 'No'],
    noteWhen: 'Yes',
    notePrompt: 'What was it?',
  },
  { id: 'anything', kind: 'text', title: 'Anything the agent should know, avoid, or never say?', placeholder: 'Optional', multiline: true },
]

export const blankAnswer = () => ({ choice: '', choices: [], rows: {}, text: '', note: '', skipped: false })

export function isAnswered(question, answer) {
  if (!answer) return false
  if (question.kind === 'one') return Boolean(answer.choice)
  if (question.kind === 'many') return answer.choices.length > 0
  if (question.kind === 'grid') return Object.keys(answer.rows).length > 0
  return answer.text.trim().length > 0
}
