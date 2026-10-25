import { useEffect, useState } from 'react'

export function navigate(path) {
  window.location.hash = path
}

function parse(hash) {
  const [, section, id, tab] = hash.replace(/^#/, '').split('/')
  return { section: section || 'bids', id: id ?? null, tab: tab ?? null }
}

export function useRoute() {
  const [route, setRoute] = useState(() => parse(window.location.hash))

  useEffect(() => {
    const onChange = () => {
      const next = parse(window.location.hash)
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
