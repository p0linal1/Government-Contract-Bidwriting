import { useEffect, useState } from 'react'

// The real bid agent's recent runs, from our server's /api/agent/live (server/live.py). The
// offline click-through has no server, so it never asks, and a failed request means no live
// data: the page then shows the sample replay alone.

const POLL_MS = 5000

const fetchLive = () =>
  fetch('/api/agent/live')
    .then((reply) => (reply.ok ? reply.json() : null))
    .catch(() => null)

export function useLiveRuns() {
  const [live, setLive] = useState(null)

  useEffect(() => {
    if (window.location.protocol === 'file:') return
    let stopped = false
    const poll = () => fetchLive().then((answer) => !stopped && setLive(answer?.sessions?.length ? answer : null))
    poll()
    const timer = setInterval(poll, POLL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [])

  return live
}

export const isRunning = (run) => run.status === 'running'

const money = (dollars) => `$${dollars.toFixed(2)}`

// One line under the title: where the run stands, what it has cost, and how long it has worked.
export function runFacts(run) {
  const state = isRunning(run) ? 'Running' : run.status === 'stopped' ? 'Stopped' : 'Finished'
  return `${state}, ${money(run.cost_usd)}, ${run.active_minutes} min of work`
}

export const stepTime = (at) => new Date(at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
