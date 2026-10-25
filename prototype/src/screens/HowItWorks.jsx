import { Facts } from '../parts'
import { Hint, Icon } from '../ui'

// The whole workflow on one page, in plain words, written to the owner: the proposal, what the
// agent does on its own, which of his bidkit tools it uses, and the one place it stops for him.
// `code` is the script's real name in bidkit, shown on hover for anyone who wants it.

const GLOSSARY = [
  { label: 'The agent', value: 'Claude, working on its own in the background. You can watch everything it does on each bid.' },
  { label: 'Bidkit', value: 'Your scripts, already built. They do the mechanical work: download, file, sort, check, and assemble. In this plan each one becomes a tool the agent can use.' },
  { label: 'A check', value: 'A yes or no question a bid must pass before it moves on. Your code calls these gates.' },
  { label: 'FGA, WEBS, Public Purchase', value: 'Websites where governments post bids. Bidkit searches them.' },
]

const CHECKS = [
  { name: 'Facts', question: 'Did it find every date, dollar amount, and rule, with a source for each?' },
  { name: 'Size', question: 'Is the contract big enough to be worth bidding?' },
  { name: 'Price', question: 'Can Cadocary come in under the budget and still make money?' },
  { name: 'Fit', question: 'Can Cadocary do the work, and does it meet every must-have rule?' },
  { name: 'Bid or not', question: 'Put together, can Cadocary win it? If not, the agent skips it and says why.' },
]

const PROPOSAL = [
  {
    title: 'Your scripts become tools',
    text: "Inbox, FGA search, downloads, facts, calendar, the five checks, and the PDF builder. They run as they do today, on Cadocary's server, with your logins kept there.",
  },
  {
    title: 'The agent does the work in between',
    text: 'It finds bids in your range, researches every one, decides whether Cadocary can win, and drafts the ones it can. It makes the small calls itself.',
  },
  {
    title: 'You review the finished bid',
    text: 'It stops for you once, when the bid is drafted. You upload it or pass. It never submits on its own.',
  },
]

const PHASES = [
  {
    name: 'Every morning',
    note: 'Nobody presses start.',
    steps: [{ who: 'agent', title: 'Wakes up at 6:00 AM on its own', text: 'Anthropic starts it on a schedule, every day.' }],
  },
  {
    name: 'Find',
    note: 'Only bids in your range.',
    steps: [
      {
        who: 'agent',
        title: 'Reads the bid inbox and the bid websites',
        text: 'Turns each bid email into a bid, files follow-ups with the right bid, and looks up new postings under your work categories.',
        scripts: [
          { name: 'Inbox tool', code: 'bidkit.inbox' },
          { name: 'FGA search tool', code: 'bidkit.fga' },
        ],
        sources: ['Bid inbox', 'FGA', 'WEBS'],
        hosted: ['Gmail connection'],
      },
      {
        who: 'agent',
        title: 'Keeps the ones in your range',
        text: 'Software work in Washington, $25,000 and up, with at least 7 days to respond. Everything else is left out, with the reason written down.',
        scripts: [
          { name: 'Scoring tool', code: 'bidkit.triage' },
          { name: 'Duplicate checker', code: 'bidkit.dedup' },
        ],
      },
    ],
  },
  {
    name: 'Research',
    note: 'Every bid in your range, without stopping.',
    steps: [
      {
        who: 'agent',
        title: 'Downloads and reads the whole RFP',
        text: 'Every page and every change, with each date, dollar amount, and rule tied to the exact line it came from.',
        scripts: [
          { name: 'Download tool', code: 'bidkit.portal' },
          { name: 'Facts tool', code: 'bidkit.brief' },
          { name: 'Calendar tool', code: 'bidkit.calendar' },
        ],
        sources: ['WEBS', 'Public Purchase'],
        hosted: ['Website logins'],
      },
      {
        who: 'agent',
        title: 'Decides whether Cadocary can win',
        text: 'Checks each requirement against your website, past projects, and resumes. Estimates what the contract is worth and who else is bidding. Writes down why.',
        checks: true,
        scripts: [{ name: 'Check tools', code: 'bidkit.harness, gate_intake, gate_value, gate_pricing, gate_fit, gate_gonogo' }],
        sources: ['Product sheets', 'Past awards'],
        hosted: ['Google Drive connection'],
      },
      {
        who: 'agent',
        title: 'Makes the small calls',
        text: 'Which references to list, which questions to send the buyer, and the price. Each call comes with the reason, so you can check it later.',
      },
    ],
  },
  {
    name: 'Draft',
    note: 'Only the bids Cadocary can win.',
    steps: [
      {
        who: 'agent',
        title: 'Writes the whole proposal',
        text: 'Section by section, in the order the RFP asks, built on the reasons Cadocary can win, inside the page limit. Then checks the format.',
        scripts: [{ name: 'PDF builder', code: 'bidkit generators, html_render, pdf_assemble' }],
      },
    ],
  },
  {
    name: 'Review',
    note: 'The one step that needs you.',
    steps: [
      {
        who: 'you',
        title: 'Read the finished bid, then upload it or pass',
        text: "Why the agent went ahead, the draft page by page with its notes, and every call it made. Cadocary is responsible for what is sent, so you upload it.",
        pause: 'Brings it to you',
      },
      { who: 'agent', title: 'Keeps watching', text: 'For changes, posted answers, and the award, every morning after.', sources: ['Bid inbox', 'Bid websites'] },
    ],
  },
]

function Step({ step }) {
  const isYou = step.who === 'you'
  const card = (
    <div className={`how-card ${isYou ? 'how-you' : 'how-agent'}`}>
      {isYou ? (
        <span className="how-tag">You decide</span>
      ) : (
        <span className="how-tag how-tag-agent">
          <Icon name="agent" size={12} stroke={2.2} />
          Agent
        </span>
      )}
      <h3>{step.title}</h3>
      <p>{step.text}</p>
      {step.checks && (
        <ol className="how-checks">
          {CHECKS.map((check) => (
            <li key={check.name}>
              <strong>{check.name}</strong>
              <span>{check.question}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
  return (
    <div className="how-step">
      {card}
      {isYou && (
        <span className="how-handoff">
          <Icon name="back" size={14} stroke={2.4} />
          {step.pause}
        </span>
      )}
      <div className="how-tools">
        {(step.scripts ?? []).map((script) => (
          <Hint key={script.name} text={`Bidkit tool. In your code: ${script.code}`} align="end">
            <span className="how-chip how-script">{script.name}</span>
          </Hint>
        ))}
        {(step.sources ?? []).map((source) => (
          <span key={source} className="how-chip how-source">
            {source}
          </span>
        ))}
        {(step.hosted ?? []).map((piece) => (
          <Hint key={piece} text="Kept on Cadocary's server with the bidkit tools, so the login never leaves." align="end">
            <span className="how-chip how-hosted">{piece}</span>
          </Hint>
        ))}
      </div>
    </div>
  )
}

export function HowItWorks() {
  return (
    <div className="how">
      <header className="how-head">
        <h1 className="step-title">How the agent works</h1>
        <p className="step-intro">The agent runs every morning: it finds, researches, and drafts on its own, and stops for you once, when a bid is ready. Nothing goes to a buyer without you.</p>
      </header>

      <section className="how-proposal" aria-label="The proposal">
        <p className="how-proposal-label">The proposal</p>
        <p className="how-proposal-line">
          Turn your bidkit scripts and your workflow into tools an agent can use. It runs them, thinks in between, sources everything it finds, and brings you finished bids.
        </p>
        <ol className="how-proposal-steps">
          {PROPOSAL.map((item) => (
            <li key={item.title}>
              <strong>{item.title}</strong>
              <span>{item.text}</span>
            </li>
          ))}
        </ol>
      </section>

      <Facts rows={GLOSSARY} />

      <div className="how-legend" aria-label="Legend">
        <span>
          <i className="how-swatch how-agent" />
          The agent does this
        </span>
        <span>
          <i className="how-swatch how-you" />
          You decide
        </span>
        <span>
          <i className="how-swatch how-script" />
          One of your bidkit tools
        </span>
        <span>
          <i className="how-swatch how-hosted" />
          Kept on Cadocary's server
        </span>
      </div>

      <div className="how-lanes" aria-hidden="true">
        <span className="lane-you">You</span>
        <span className="lane-agent">The agent</span>
        <span className="lane-tools">Bidkit tools and sources</span>
      </div>

      {PHASES.map((phase) => (
        <section key={phase.name} className="how-phase" aria-label={phase.name}>
          <div className="how-phase-head">
            <h2>{phase.name}</h2>
            <p>{phase.note}</p>
          </div>
          {phase.steps.map((step) => (
            <Step key={step.title} step={step} />
          ))}
        </section>
      ))}
    </div>
  )
}
