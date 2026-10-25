import { getResearch } from '../research'

// The call the agent made where the files left one open, such as which reference to use.
export function agentPick(job) {
  return job.question?.options.find((o) => o.id === job.question.agentPick) ?? null
}

// Whether Cadocary is a competitive bidder, as the agent judged it at the end of research. When it
// is not, `reason` is the one thing that rules it out, with the line in the RFP behind it.
export function assess(job) {
  const research = getResearch(job)
  const pick = agentPick(job)
  if (pick?.verdict) return { competitive: false, reason: pick.risk, detail: job.question.agentReason, cite: job.question.cite }
  if (research.verdict.title !== 'Bid') {
    const gap = research.requirements.find((r) => r.coverage === 'gap' && r.kind === 'Must')
    return { competitive: false, reason: `${gap.text}: Cadocary has never built this.`, detail: gap.evidence, cite: gap.cite }
  }
  return { competitive: true }
}
