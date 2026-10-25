import { useEffect, useState } from 'react'

export function navigate(path) {
  window.location.hash = path
}

function parse(hash) {
  const [, section, id, tab] = hash.replace(/^#/, '').split('/')
  return { section: section || 'bids', id: id ?? null, tab: tab ?? null }
}

// How it works became the Agent page. Old links land there without adding a step to history.
function readRoute() {
  const route = parse(window.location.hash)
  if (route.section !== 'how') return route
  window.history.replaceState(null, '', '#/agent')
  return parse('#/agent')
}

export function useRoute() {
  const [route, setRoute] = useState(readRoute)

  useEffect(() => {
    const onChange = () => {
      const next = readRoute()
      setRoute((previous) => {
        if (previous.section !== next.section || previous.id !== next.id) window.scrollTo(0, 0)
        return next
      })
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  return route
}
