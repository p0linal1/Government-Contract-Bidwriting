import { useEffect, useState } from 'react'

// The real bid agent's recent runs, from our server's /api/agent/live (server/live.py), with the
// steps of one chosen run, or of the newest when none is chosen. The offline click-through has no
// server, so it never asks, and a failed request means no live data: the page then shows the
// sample replay alone.

const POLL_MS = 5000

const fetchLive = (sessionId) =>
  fetch(sessionId ? `/api/agent/live?session=${encodeURIComponent(sessionId)}` : '/api/agent/live')
    .then((reply) => (reply.ok ? reply.json() : null))
    .catch(() => null)

// With no run chosen, the page follows the newest running run, or else the newest run. The server
// answers for the newest, so when a different run is working, it is asked again for that one.
function followed(answer) {
  const runs = answer?.sessions ?? []
  return (runs.find(isRunning) ?? runs[0])?.id
}

export function useLiveRuns(sessionId) {
  const [live, setLive] = useState(null)

  useEffect(() => {
    if (window.location.protocol === 'file:') return
    let stopped = false
    // A linked run that has dropped out of the recent list is not offered, so the newest shows instead.
    const poll = () =>
      fetchLive(sessionId)
        .then((answer) => answer ?? (sessionId ? fetchLive(null) : null))
        .then((answer) => (!sessionId && answer && followed(answer) !== answer.session_id ? fetchLive(followed(answer)) : answer))
        .then((answer) => !stopped && setLive(answer?.sessions?.length ? answer : null))
    poll()
    const timer = setInterval(poll, POLL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [sessionId])

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
