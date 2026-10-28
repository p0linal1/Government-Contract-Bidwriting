import { useEffect, useState } from 'react'
import { navigate, useRoute } from './router'
import { LibraryProvider, useLibrary } from './library'
import { Agent } from './screens/Agent'
import { Bids } from './screens/Bid'
import { Facts } from './screens/Facts'
import { Research } from './screens/Research'
import { Settings } from './screens/Settings'
import { SourceProvider } from './sources'
import { useStore } from './store'
import { Tour, tourStepInAddress } from './Tour'
import { Icon } from './ui'

function Toasts({ currentId }) {
  const { state, dispatch } = useStore()
  const { live } = useLibrary()
  const latest = state.toasts.at(-1)

  useEffect(() => {
    if (!latest) return
    const timer = setTimeout(() => dispatch({ type: 'dismissToast', toastId: latest.id }), 6000)
    return () => clearTimeout(timer)
  }, [latest, dispatch])

  // No need to announce a change to the bid already on screen. The sample bids' news means
  // nothing while the app shows the real library.
  if (live || !latest || (currentId && latest.to?.endsWith(`/${currentId}`))) return null
  return (
    <div className="toast" role="status">
      <span className="toast-text">{latest.text}</span>
      {latest.to && (
        <button
          className="toast-action"
          onClick={() => {
            dispatch({ type: 'dismissToast', toastId: latest.id })
            navigate(latest.to)
          }}
        >
          Open
        </button>
      )}
    </div>
  )
}

function Screen({ section, id, tab }) {
  if (section === 'settings') return <Settings id={id} />
  if (section === 'agent') return <Agent sessionId={id} />
  if (section === 'facts') return <Facts id={id} />
  if (id && tab === 'research') return <Research id={id} section="bids" />
  return <Bids id={id} today={section === 'today'} />
}

export function App() {
  const route = useRoute()
  const section = ['settings', 'today', 'agent', 'facts'].includes(route.section) ? route.section : 'bids'
  const [tourStep, setTourStep] = useState(tourStepInAddress)

  return (
    <LibraryProvider>
      <SourceProvider>
        <header className="topbar">
          <button className="wordmark" onClick={() => navigate('/bids')}>
            Cadocary
          </button>
          <div className="topbar-actions">
            <button className="top-button" aria-label="Start walkthrough" onClick={() => setTourStep(0)}>
              <Icon name="play" size={20} stroke={1.8} />
              <span>Start walkthrough</span>
            </button>
            <button className="top-button" aria-label="Agent" aria-current={section === 'agent' ? 'page' : undefined} onClick={() => navigate('/agent')}>
              <Icon name="agent" size={20} stroke={1.8} />
              <span>Agent</span>
            </button>
            <button className="top-button" aria-label="Facts" aria-current={section === 'facts' ? 'page' : undefined} onClick={() => navigate('/facts')}>
              <Icon name="checklist" size={20} stroke={1.8} />
              <span>Facts</span>
            </button>
            <button className="top-button" aria-label="Settings" aria-current={section === 'settings' ? 'page' : undefined} onClick={() => navigate('/settings')}>
              <Icon name="settings" size={20} stroke={1.8} />
              <span>Settings</span>
            </button>
          </div>
        </header>

        {/* Bids keep their list mounted while switching bids, so the list does not jump back to the top. */}
        <main className="screen" key={['settings', 'agent', 'facts'].includes(section) ? section : `bids/${route.tab ?? ''}`}>
          <Screen section={section} id={route.id} tab={route.tab} />
        </main>

        <Toasts currentId={route.id} />
        {tourStep != null && <Tour index={tourStep} onGo={setTourStep} onClose={() => setTourStep(null)} />}
      </SourceProvider>
    </LibraryProvider>
  )
}
