import { useEffect } from 'react'
import { navigate, useRoute } from './router'
import { Bids } from './screens/Bid'
import { HowItWorks } from './screens/HowItWorks'
import { Research } from './screens/Research'
import { Settings } from './screens/Settings'
import { SourceProvider } from './sources'
import { useStore } from './store'
import { Icon } from './ui'

function Toasts({ currentId }) {
  const { state, dispatch } = useStore()
  const latest = state.toasts.at(-1)

  useEffect(() => {
    if (!latest) return
    const timer = setTimeout(() => dispatch({ type: 'dismissToast', toastId: latest.id }), 6000)
    return () => clearTimeout(timer)
  }, [latest, dispatch])

  // No need to announce a change to the bid already on screen.
  if (!latest || (currentId && latest.to?.endsWith(`/${currentId}`))) return null
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
  if (section === 'how') return <HowItWorks />
  if (id && tab === 'research') return <Research id={id} section="bids" />
  return <Bids id={id} today={section === 'today'} />
}

export function App() {
  const route = useRoute()
  const section = ['settings', 'today', 'how'].includes(route.section) ? route.section : 'bids'

  return (
    <SourceProvider>
      <header className="topbar">
        <button className="wordmark" onClick={() => navigate('/bids')}>
          Cadocary
        </button>
        <div className="topbar-actions">
          <button className="top-button" aria-label="How it works" aria-current={section === 'how' ? 'page' : undefined} onClick={() => navigate('/how')}>
            <Icon name="flow" size={20} stroke={1.8} />
            <span>How it works</span>
          </button>
          <button className="top-button" aria-label="Settings" aria-current={section === 'settings' ? 'page' : undefined} onClick={() => navigate('/settings')}>
            <Icon name="settings" size={20} stroke={1.8} />
            <span>Settings</span>
          </button>
        </div>
      </header>

      {/* Bids keep their list mounted while switching bids, so the list does not jump back to the top. */}
      <main className="screen" key={['settings', 'how'].includes(section) ? section : `bids/${route.tab ?? ''}`}>
        <Screen section={section} id={route.id} tab={route.tab} />
      </main>

      <Toasts currentId={route.id} />
    </SourceProvider>
  )
}
