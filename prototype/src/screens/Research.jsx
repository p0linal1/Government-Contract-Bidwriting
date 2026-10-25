import { useEffect } from 'react'
import { Brief } from '../bid/Brief'
import { JOBS_BY_ID } from '../data'
import { useStore } from '../store'
import { BackButton } from '../ui'

export function Research({ id, section }) {
  const { state } = useStore()
  const job = JOBS_BY_ID[id]

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [id])

  if (!job) return null
  return (
    <article className="bid-page">
      <BackButton to={`/${section}/${id}`} label={job.buyer} />
      <header className="bid-head">
        <p className="kicker">Full research</p>
        <h1 className="bid-title">{job.title}</h1>
      </header>
      <Brief job={job} progress={state.jobs[id]} />
    </article>
  )
}
