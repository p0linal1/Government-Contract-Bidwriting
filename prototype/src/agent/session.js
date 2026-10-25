import { sections, totalPages } from '../bid'
import { getResearch } from '../research'
import { OUTPUTS, bash, driveRead, driveSearch, note, read, write } from './calls'

export const MODEL = 'claude-opus-5-5'

// Events a person sees. Spans and usage are bookkeeping: they ride along with the next visible one.
const VISIBLE = new Set([
  'user.message',
  'session.status_running',
  'session.status_idle',
  'agent.thinking',
  'agent.message',
  'agent.tool_use',
  'agent.tool_result',
  'agent.mcp_tool_use',
  'agent.mcp_tool_result',
])

export const isVisible = (event) => VISIBLE.has(event.type)

const cache = new Map()
// When the sample runs began: 6:14 AM Pacific on the demo morning.
const STARTED = Date.parse('2026-10-26T13:14:00Z')

const slug = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')

// The steps the agent takes to draft a proposal once the owner says bid.
function draftLog(job) {
  const list = sections(job)
  const total = totalPages(job)
  return [
    {
      text: 'Read the decision brief and the proposal rules',
      calls: [
        read(`${OUTPUTS}/decision_brief.md`, 'Why Cadocary is competitive, the risks, the price, and the calls the agent made.', 2),
        driveSearch('past winning proposals', '14 past bids, 9 won. 3 are close to this one.'),
      ],
    },
    ...list.map((section, i) => ({
      text: `Drafted section ${i + 1}: ${section.title}`,
      calls: [
        i === list.length - 1 && driveRead('Reference letters.pdf', '6 reference letters.'),
        write(`proposal/${i + 1}_${slug(section.title)}.md`, `${section.title}: ${section.pages} ${section.pages === 1 ? 'page' : 'pages'}.`, 6 + section.pages * 4),
      ].filter(Boolean),
    })),
    job.forms > 0 && { text: `Filled in forms 1 to ${job.forms}`, calls: [write('forms.pdf', `${job.forms} forms filled in from your company file.`, 6)] },
    {
      text: 'Checked the page limit and font size',
      calls: [bash(`python3 check_format.py proposal/ --limit ${job.pageLimit} --min-font 11`, `${total} of ${job.pageLimit} pages. All text 11 point or larger.`)],
    },
    {
      text: 'Put the proposal together as one PDF',
      calls: [
        bash('pandoc proposal/*.md -o proposal.pdf', `proposal.pdf saved, ${total} pages.`),
        note(`The draft is ready: ${list.length} sections, ${total} pages. Each section needs your approval before anything is sent.`),
      ],
    },
  ].filter(Boolean)
}

// A run is one job the agent does on a bid, as the event stream a Managed Agents session
// emits (GET /v1/sessions/{id}/events/stream). It is deterministic, so the prototype replays it
// one event at a time and every screen can be rebuilt from a count of events alone.
function buildRun(job, kind, { log, opening, decision }) {
  const events = []
  const tag = `${job.id.replace(/-/g, '')}_${kind[0]}`
  let clock = 0
  let input = 18000
  let totalInput = 0
  let output = 0

  const emit = (step, event, seconds = 0) => {
    clock += seconds
    const id = `sevt_${tag}${String(events.length + 1).padStart(3, '0')}`
    events.push({ id, step, at: clock, ...event, processed_at: new Date(STARTED + clock * 1000).toISOString() })
    return id
  }

  // One model request: Claude reads the conversation so far and writes its next move.
  const modelTurn = (step, write, outputTokens) => {
    emit(step, { type: 'span.model_request_start' })
    write()
    input += 2400 + outputTokens * 2
    totalInput += input
    output += outputTokens
    emit(step, { type: 'span.model_request_end', is_error: false, model_usage: { input_tokens: input, output_tokens: outputTokens, cache_read_input_tokens: Math.round(input * 0.8) } }, 1)
  }

  const usage = (step) =>
    emit(step, {
      type: 'session.usage',
      usage: { input_tokens: totalInput, output_tokens: output, server_tool_use: { web_search_requests: events.filter((e) => e.name === 'web_search' && e.type === 'agent.tool_use').length } },
    })

  emit(0, { type: 'user.message', content: [{ type: 'text', text: opening }] })
  emit(0, { type: 'session.status_running' })

  log.forEach((entry, step) => {
    // Where the files leave a call open, the agent makes it and writes down why.
    if (decision && step === decision.at) {
      modelTurn(step, () => emit(step, { type: 'agent.message', content: [{ type: 'text', text: decision.text }] }, 4), 140)
    }

    emit(step, { type: 'agent.thinking' }, 2)
    for (const call of entry.calls ?? []) {
      if (call.message) {
        modelTurn(step, () => emit(step, { type: 'agent.message', content: [{ type: 'text', text: call.message }] }, call.seconds), Math.round(call.message.length / 3))
        continue
      }
      let useId
      const use = call.mcp ? { type: 'agent.mcp_tool_use', mcp_server_name: call.mcp } : { type: 'agent.tool_use' }
      modelTurn(step, () => (useId = emit(step, { ...use, name: call.name, input: call.input, evaluated_permission: 'allow' }, 2)), 90)
      const content = Array.isArray(call.result) ? call.result : [{ type: 'text', text: call.result }]
      emit(step, call.mcp ? { type: 'agent.mcp_tool_result', mcp_tool_use_id: useId, content, is_error: false } : { type: 'agent.tool_result', tool_use_id: useId, content, is_error: false }, call.seconds)
    }
    usage(step)
  })

  emit(log.length - 1, { type: 'session.status_idle', stop_reason: { type: 'end_turn' } }, 1)
  return { kind, log, events }
}

function cached(key, make) {
  if (!cache.has(key)) cache.set(key, make())
  return cache.get(key)
}

// Researching the RFP, start to finish, without stopping.
export function researchRun(job) {
  const research = getResearch(job)
  const pick = job.question?.options.find((o) => o.id === job.question.agentPick)
  return cached(`${job.id}:research`, () =>
    buildRun(job, 'research', {
      log: research.log,
      opening: `Research ${job.solicitation} for Cadocary. Read every document, check each requirement against Cadocary's files, decide whether Cadocary is competitive and why, and make any call the files leave open.`,
      decision: pick && { at: research.questionAt, text: `Decided: ${pick.label}. ${job.question.agentReason}` },
    }),
  )
}

// Drafting the proposal after the owner decides to bid.
export function draftRun(job) {
  return cached(`${job.id}:draft`, () =>
    buildRun(job, 'draft', {
      log: draftLog(job),
      opening: `Draft the proposal for ${job.solicitation} from the decision brief. Lead with the reasons Cadocary is competitive, and stay inside the ${job.pageLimit}-page limit.`,
    }),
  )
}

// The run the agent is on right now for this bid, and how far into it.
export function activeRun(job, progress) {
  return progress.stage === 'drafting' ? [draftRun(job), progress.draftCount] : [researchRun(job), progress.eventCount]
}

// How many events have been emitted when a run has reached a given step.
export function eventsBeforeStep(run, step) {
  const index = run.events.findIndex((event) => event.step >= step)
  return index === -1 ? run.events.length : index
}

// Steps whose events have all been emitted.
export function stepsDone(run, count) {
  return count >= run.events.length ? run.log.length : run.events[count].step
}

const fileName = (path) => path.split('/').pop()
const host = (url) => new URL(url).hostname.replace(/^www\./, '')
const quoted = (text) => `“${text}”`

// Shell commands, read as what they are for: [while running, once done].
function describeCommand(command) {
  const pages = command.match(/-f (\d+) -l (\d+)/)
  const pdf = command.match(/([\w.-]+\.pdf)/)
  const downloads = (command.match(/https?:\/\//g) ?? []).length
  if (command.includes('pdftotext')) {
    const what = pages ? `${fileName(pdf[1])}, pages ${pages[1]} to ${pages[2]}` : fileName(pdf[1])
    return [`Pulling the text out of ${what}`, `Pulled the text out of ${what}`]
  }
  if (command.includes('curl')) {
    const what = `${downloads} ${downloads === 1 ? 'document' : 'documents'}`
    return [`Downloading ${what}`, `Downloaded ${what}`]
  }
  if (command.includes('munpack')) return ['Saving the email attachments', 'Saved the email attachments']
  if (command.includes('estimate.py')) return ['Adding up the hours and cost', 'Added up the hours and cost']
  if (command.includes('score.py')) return ['Scoring the bid against the RFP criteria', 'Scored the bid against the RFP criteria']
  if (command.includes('check_format.py')) return ['Checking the page limit and font size', 'Checked the page limit and font size']
  if (command.includes('pandoc')) return ['Putting the proposal together as a PDF', 'Put the proposal together as a PDF']
  return ['Running a command', 'Ran a command']
}

// One tool call in plain words: what it is doing now, and what it did once done.
export function describeCall(use) {
  const { name, input } = use
  switch (name) {
    case 'web_search':
      return { icon: 'search', now: `Searching the web for ${quoted(input.query)}`, done: `Searched the web for ${quoted(input.query)}` }
    case 'web_fetch':
      return { icon: 'globe', now: `Opening ${host(input.url)}`, done: `Opened ${host(input.url)}`, link: input.url }
    case 'read':
      return { icon: 'doc', now: `Reading ${fileName(input.file_path)}`, done: `Read ${fileName(input.file_path)}` }
    case 'grep':
      return { icon: 'search', now: `Searching ${fileName(input.path)} for ${quoted(input.pattern.replaceAll('|', ', '))}`, done: `Searched ${fileName(input.path)} for ${quoted(input.pattern.replaceAll('|', ', '))}` }
    case 'bash': {
      const [now, done] = describeCommand(input.command)
      return { icon: 'terminal', now, done }
    }
    case 'write':
      return { icon: 'pen', now: `Saving ${fileName(input.file_path)}`, done: `Saved ${fileName(input.file_path)}` }
    case 'search_files':
      return { icon: 'folder', now: `Searching your Google Drive for ${quoted(input.query)}`, done: `Searched your Google Drive for ${quoted(input.query)}` }
    case 'read_file':
      return { icon: 'folder', now: `Opening ${input.name} from your Google Drive`, done: `Read ${input.name} from your Google Drive` }
    default:
      return { icon: 'terminal', now: `Using ${name}`, done: `Used ${name}` }
  }
}

function resultText(event) {
  const results = event.content.filter((block) => block.type === 'search_result')
  if (results.length) return `${results.length} results: ${results.map((r) => r.title).join('; ')}`
  return event.content.map((block) => block.text).join(' ')
}

// The emitted events, grouped by step and translated for a person. A tool call and its
// result become one line that is running until the result arrives.
export function translate(run, count) {
  const { events, log } = run
  const shown = events.slice(0, count)
  const latest = shown.filter(isVisible).at(-1)
  const steps = log.map((entry) => ({ text: entry.text, items: [] }))
  const calls = new Map()

  for (const event of shown) {
    const items = steps[event.step].items
    switch (event.type) {
      case 'user.message':
        items.push({ id: event.id, icon: 'you', title: run.kind === 'draft' ? 'Cadocary is competitive, so the agent drafts the bid' : 'Found a bid in your range, so the agent researches it', detail: event.content[0].text, at: event.at })
        break
      case 'agent.thinking':
        if (event === latest) items.push({ id: event.id, icon: 'think', title: 'Thinking', state: 'running', at: event.at })
        break
      case 'agent.message':
        items.push({ id: event.id, icon: 'note', note: event.content[0].text, at: event.at, live: event === latest })
        break
      case 'agent.tool_use':
      case 'agent.mcp_tool_use': {
        const said = describeCall(event)
        const item = { id: event.id, icon: said.icon, title: said.now, done: said.done, link: said.link, state: 'running', at: event.at }
        calls.set(event.id, item)
        items.push(item)
        break
      }
      case 'agent.tool_result':
      case 'agent.mcp_tool_result': {
        const item = calls.get(event.tool_use_id ?? event.mcp_tool_use_id)
        Object.assign(item, { title: item.done, detail: resultText(event), state: event.is_error ? 'error' : 'done', seconds: event.at - item.at })
        break
      }
      default:
        break
    }
  }

  const finished = count >= events.length
  const current = finished ? -1 : events[count].step
  return {
    steps: steps.map((step, i) => ({ ...step, status: finished || i < current ? 'done' : i === current ? 'now' : 'pending' })),
    latest,
    finished,
    clock: shown.at(-1)?.at ?? 0,
    toolCalls: shown.filter((e) => e.type === 'agent.tool_use' || e.type === 'agent.mcp_tool_use').length,
    written: shown.filter((e) => e.type === 'agent.tool_use' && e.name === 'write' && e.input.file_path.includes('/proposal/')).length,
  }
}

// The single line for the bid list: what the agent is doing this moment.
export function nowDoing(run, count) {
  const { steps, latest } = translate(run, count)
  const items = steps.flatMap((step) => step.items)
  const running = items.findLast((item) => item.state === 'running' && item.icon !== 'think')
  if (running) return running.title
  if (latest?.type === 'agent.thinking') return 'Thinking about the next step'
  if (latest?.type === 'agent.message') return 'Writing a note'
  return items.filter((item) => item.icon !== 'you').at(-1)?.title ?? 'Starting'
}
