import { COMPANY } from '../data'
import { useLibrary } from '../library'
import { Choice, Facts } from '../parts'
import { navigate } from '../router'
import { useStore } from '../store'
import { THEMES, useTheme } from '../theme'
import { Icon } from '../ui'

const CREDENTIAL_TONE = { good: 'good', warn: 'warn' }

function Company() {
  return (
    <>
      <h1 className="step-title">{COMPANY.name}</h1>
      <p className="step-intro">The agent checks every RFP against these facts to decide whether Cadocary can win, and uses them when it drafts.</p>
      <Facts
        rows={[
          { label: 'What it does', value: COMPANY.summary },
          { label: 'Website', value: COMPANY.website },
          { label: 'Bids it pursues', value: COMPANY.range },
          { label: 'Rate', value: COMPANY.rate },
          ...COMPANY.credentials.map((row) => ({ label: row.item, value: row.value, tone: CREDENTIAL_TONE[row.status] })),
        ]}
      />
    </>
  )
}

function Products() {
  return (
    <>
      <h1 className="step-title">What Cadocary has built</h1>
      <p className="step-intro">Requirements are matched against these.</p>
      <Facts rows={COMPANY.products.map((product) => ({ label: product.name, value: product.detail }))} />
    </>
  )
}

function Files() {
  return (
    <>
      <h1 className="step-title">Files the agent reads</h1>
      <p className="step-intro">From the Cadocary shared drive: products, past projects, and resumes. The agent reads them before every bid.</p>
      <Facts rows={COMPANY.files.map((file) => ({ label: `Updated ${file.updated}`, value: file.title }))} />
    </>
  )
}

function Sources() {
  return (
    <>
      <h1 className="step-title">Where the agent looks</h1>
      <p className="step-intro">Checked every night at 6:00 AM, and the bid inbox as emails arrive.</p>
      <Facts rows={COMPANY.watching.map((source) => ({ label: source.name, value: source.detail, detail: `Last check: ${source.last}` }))} />
    </>
  )
}

function Appearance() {
  const { theme, setTheme } = useTheme()
  return (
    <>
      <h1 className="step-title">Appearance</h1>
      <div className="choices" role="radiogroup" aria-label="Appearance">
        {THEMES.map((option) => (
          <Choice key={option.id} label={option.name} note={option.note} selected={option.id === theme} onChoose={() => setTheme(option.id)} />
        ))}
      </div>
    </>
  )
}

function Demo() {
  const { dispatch } = useStore()
  const { reach, sample, setSample } = useLibrary()
  const reachable = reach === 'live'
  return (
    <>
      <h1 className="step-title">Demo data</h1>
      <p className="step-intro">
        {reachable
          ? "Live data shows the real RFPs from SAM.gov and what the agent found. Sample data shows the made-up bids from the recorded walkthrough."
          : 'The RFP Library cannot be reached from here, so the app shows the sample bids.'}
      </p>
      <div className="choices" role="radiogroup" aria-label="Which bids to show">
        <Choice label="Live data" note="The real RFP Library" selected={reachable && !sample} disabled={!reachable} onChoose={() => setSample(false)} />
        <Choice label="Sample data" note="The sample bids from the walkthrough" selected={!reachable || sample} onChoose={() => setSample(true)} />
      </div>
      <p className="step-intro">Resetting starts the sample morning over.</p>
      <div className="alternates">
        <button className="btn btn-secondary" onClick={() => dispatch({ type: 'reset' })}>
          Reset the demo
        </button>
      </div>
    </>
  )
}

const PAGES = [
  { id: 'company', title: 'Company', note: 'Licenses, insurance, rate', Page: Company },
  { id: 'products', title: 'Products', note: `${COMPANY.products.length} things Cadocary has built`, Page: Products },
  { id: 'files', title: 'Files', note: `${COMPANY.files.length} files the agent reads`, Page: Files },
  { id: 'sources', title: 'Where it looks', note: `${COMPANY.watching.length} sources, checked nightly`, Page: Sources },
  { id: 'appearance', title: 'Appearance', note: 'Type, color, and corners', Page: Appearance },
  { id: 'demo', title: 'Demo data', note: 'Live or sample bids', Page: Demo },
]

export function Settings({ id }) {
  const open = PAGES.find((page) => page.id === id)
  // On a laptop the first page shows by default. On a phone the list comes first.
  const shown = open ?? PAGES[0]

  return (
    <div className={`desk ${open ? 'has-open' : ''}`}>
      <nav className="desk-list" aria-label="Settings">
        <section>
          <h2 className="list-title">Settings</h2>
          <ul>
            {PAGES.map((page) => (
              <li key={page.id}>
                <button className="list-item" aria-current={page.id === shown.id ? 'page' : undefined} onClick={() => navigate(`/settings/${page.id}`)}>
                  <span className="list-text">
                    <strong>{page.title}</strong>
                    <span>{page.note}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </nav>
      <div className="desk-main">
        <header className="step-head step-head-plain">
          <button className="all-bids" onClick={() => navigate('/settings')}>
            <Icon name="back" size={16} stroke={2.4} />
            Settings
          </button>
        </header>
        <div className="step-body" key={shown.id}>
          <shown.Page />
        </div>
      </div>
    </div>
  )
}
