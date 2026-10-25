import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { BADGES, CANVAS, CHECKS, EDGES, FIRST_TEST, LABELS, NODES, NOTES, PORTS, PORT_LABELS, RUNS, STACK, STEPS, SUBS, beatLength, liveScene, panelFor, sceneAt, stepState, subportLabel, subsOf } from '../agent/graph'
import { isRunning, runFacts, useLiveRuns } from '../agent/live'
import { Steps } from '../agent/Steps'
import { Facts, Mark } from '../parts'
import { navigate } from '../router'
import { Icon } from '../ui'

// The bid agent as a picture: five Claude agents, what each is attached to, and either the
// real run the server reports or a replay of a sample run. Laptops get the full graph, scaled
// to fit. Phones get the same parts as a stack.

const GUIDE = 'Click any part to see what it does. Play the sample replay to watch a sample run.'

const PANEL_STATUS = { live: 'In the run happening now', last: 'In the real run shown' }

function PanelValue({ value }) {
  if (Array.isArray(value)) {
    return (
      <ul className="agent-list">
        {value.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    )
  }
  return value.split('`').map((part, i) => (i % 2 ? <code key={i}>{part}</code> : part))
}

function StatusChip({ status }) {
  return (
    <span className="agent-status">
      <Icon name="check" size={10} stroke={3.4} />
      {status}
    </span>
  )
}

function StepBadge({ step, scene, at }) {
  return (
    <span className={`agent-badge ${at ? 'is-placed' : ''}`} data-state={stepState(step, scene)} style={at && { left: at.x, top: at.y }}>
      {step}
    </span>
  )
}

function NodeCard({ id, scene, selected, onOpen, onCanvas }) {
  const node = NODES[id]
  const kind = `${node.kind === 'agent' ? 'is-agent' : ''} ${node.planned ? 'is-planned' : ''} ${node.large ? 'is-large' : ''}`
  return (
    <button
      className={`agent-node ${kind} ${selected ? 'selected' : ''}`}
      data-tour={`node-${id}`}
      data-status={scene.status[id]}
      style={onCanvas && { left: node.x, top: node.y, width: node.w, height: node.h }}
      aria-label={`${node.title}: ${node.sub}. Show details.`}
      onClick={(event) => onOpen(id, event.currentTarget)}
    >
      <span className="agent-node-icon">
        <Icon name={node.icon} size={node.large ? 24 : 20} />
      </span>
      <span className="agent-node-text">
        <span className="agent-node-title">{node.title}</span>
        <span className="agent-node-sub">{node.sub}</span>
      </span>
      <StatusChip status={scene.status[id]} />
    </button>
  )
}

function SubNode({ id, scene, selected, onOpen }) {
  const sub = SUBS[id]
  const state = `${scene.live.has(id) ? 'live' : ''} ${scene.dimmed.has(id) ? 'dim' : ''} ${selected ? 'selected' : ''}`
  return (
    <button
      className={`agent-sub ${sub.small ? 'is-small' : ''} ${state}`}
      style={{ left: sub.x - sub.r, top: sub.y - sub.r, width: sub.r * 2, height: sub.r * 2 }}
      aria-label={`${sub.label}. Show details.`}
      onClick={(event) => onOpen(id, event.currentTarget)}
    >
      <Icon name={sub.icon} size={sub.small ? 16 : 20} stroke={1.9} />
      <span className="agent-sub-label">{sub.label}</span>
    </button>
  )
}

function SubChip({ id, scene, selected, onOpen }) {
  const sub = SUBS[id]
  const state = `${scene.live.has(id) ? 'live' : ''} ${scene.dimmed.has(id) ? 'dim' : ''} ${selected ? 'selected' : ''}`
  return (
    <button className={`agent-subchip ${state}`} onClick={(event) => onOpen(id, event.currentTarget)}>
      <span className="agent-subchip-icon">
        <Icon name={sub.icon} size={14} />
      </span>
      <small>{subportLabel(NODES[sub.parent], sub.port)}</small>
      {sub.label}
    </button>
  )
}

function EdgeLabel({ id, scene, onCanvas }) {
  const label = LABELS[id]
  const place = onCanvas ? `is-placed ${label.side ? `is-${label.side}` : ''}` : ''
  const state = `${scene.litLabels.has(id) ? 'lit' : ''} ${scene.dimmed.has(id) ? 'dim' : ''}`
  return (
    <span className={`agent-elabel ${place} ${label.gate ? 'is-gate' : ''} ${state}`} style={onCanvas && { left: label.x, top: label.y }}>
      {scene.labels[id]}
    </span>
  )
}

const checkState = (id, scene) => `${scene.litChecks.has(id) ? 'lit' : ''} ${scene.dimmed.has(id) ? 'dim' : ''}`

function CheckChip({ id, scene }) {
  const check = CHECKS[id]
  return (
    <span className={`agent-checkchip ${checkState(id, scene)}`} style={{ left: check.x, top: check.y }}>
      <StepBadge step={check.step} scene={scene} />
      <span>
        <strong>{check.title}</strong>
        <span className="agent-check-round">{scene.checks[id]}</span>
      </span>
    </span>
  )
}

function LoopNote({ id, scene }) {
  const check = CHECKS[id]
  return (
    <div className={`agent-loopnote ${checkState(id, scene)}`}>
      <Icon name="replay" size={18} />
      <span>
        <strong>{check.title}</strong>
        <span className="agent-check-round">{scene.checks[id]}</span>
      </span>
    </div>
  )
}

function FirstTest({ lit, place }) {
  return (
    <div className={`agent-sticky ${lit ? 'lit' : ''}`} style={place && { left: place.x, top: place.y, width: place.w }}>
      <p className="agent-sticky-title">{FIRST_TEST.title}</p>
      <div className="agent-stats">
        {FIRST_TEST.stats.map(([figure, text]) => (
          <p key={text} className="agent-stat">
            <strong>{figure}</strong>
            <span>{text}</span>
          </p>
        ))}
      </div>
    </div>
  )
}

function wireClass(edge, scene) {
  const flow = scene.flows[edge.id]
  const live = !flow && edge.attach && scene.live.has(edge.to[0])
  return `agent-wire ${edge.cls} ${flow ? 'flow' : ''} ${flow === 'back' ? 'back' : ''} ${live ? 'live' : ''} ${scene.dimmed.has(edge.id) ? 'dim' : ''}`
}

function Wires({ scene }) {
  return (
    <svg className="agent-wires" viewBox={`0 0 ${CANVAS.width} ${CANVAS.height}`} width={CANVAS.width} height={CANVAS.height} aria-hidden="true">
      <defs>
        {['agent-arrow', 'agent-arrow-live'].map((id) => (
          <marker key={id} id={id} viewBox="0 0 10 10" refX="17" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
            <path className={`agent-arrow-head ${id === 'agent-arrow-live' ? 'live' : ''}`} d="M0 0.5L10 5L0 9.5z" />
          </marker>
        ))}
      </defs>
      {EDGES.map((edge) => (
        <path key={edge.id} className={wireClass(edge, scene)} d={edge.d} />
      ))}
    </svg>
  )
}

function Legend() {
  return (
    <div className="agent-legend">
      <span>
        <svg width="36" height="12" aria-hidden="true">
          <line className="agent-key-line" x1="1" y1="6" x2="27" y2="6" />
          <path className="agent-key-head" d="M27 1.5L35 6L27 10.5z" />
        </svg>
        Starts the run or delivers the result
      </span>
      <span>
        <svg width="36" height="12" aria-hidden="true">
          <line className="agent-key-line is-dashed" x1="1" y1="6" x2="35" y2="6" />
        </svg>
        Attached to an agent: its model, skill, memory, and tools
      </span>
      <span>
        <svg width="36" height="12" aria-hidden="true">
          <path className="agent-key-head" d="M9 1.5L1 6L9 10.5z" />
          <line className="agent-key-line is-helper" x1="9" y1="6" x2="27" y2="6" />
          <path className="agent-key-head" d="M27 1.5L35 6L27 10.5z" />
        </svg>
        The Operator hands work to a helper and gets it back
      </span>
      <span>
        <span className="agent-badge">1</span>
        Order of a run
      </span>
    </div>
  )
}

function Canvas({ scene, openId, onOpen }) {
  const frame = useRef(null)
  const [scale, setScale] = useState(1)

  useLayoutEffect(() => {
    const element = frame.current
    // The 24 leaves a little canvas showing on each side of the graph.
    const fit = () => setScale(Math.max(0, Math.min(1, (element.clientWidth - 24) / CANVAS.width)))
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return (
    <section className="agent-frame" ref={frame} aria-label="Diagram of the bid agent" data-tour="agent-map">
      <div className="agent-fit" style={{ width: CANVAS.width * scale, height: CANVAS.height * scale }}>
        <div className="agent-canvas" style={{ width: CANVAS.width, height: CANVAS.height, transform: `scale(${scale})` }}>
          <Wires scene={scene} />
          {Object.keys(NODES).map((id) => (
            <NodeCard key={id} id={id} scene={scene} selected={openId === id} onOpen={onOpen} onCanvas />
          ))}
          {Object.keys(SUBS).map((id) => (
            <SubNode key={id} id={id} scene={scene} selected={openId === id} onOpen={onOpen} />
          ))}
          <div className="agent-ports">
            {PORTS.map((port) => (
              <span key={port.at.join()} className={`agent-port is-${port.shape}`} style={{ left: port.at[0], top: port.at[1] }} />
            ))}
            {PORT_LABELS.map((port) => (
              <span key={port.key} className={`agent-port-label ${port.large ? 'is-large' : ''}`} style={{ left: port.x, top: port.y }}>
                {port.label}
              </span>
            ))}
          </div>
          {BADGES.map((badge) => (
            <StepBadge key={badge.step} step={badge.step} scene={scene} at={badge} />
          ))}
          {Object.keys(LABELS).map((id) => (
            <EdgeLabel key={id} id={id} scene={scene} onCanvas />
          ))}
          {Object.keys(CHECKS).map((id) => (
            <CheckChip key={id} id={id} scene={scene} />
          ))}
          {NOTES.map((note) => (
            <span key={note.text} className={`agent-note ${note.center ? 'is-centered' : ''}`} style={{ left: note.x, top: note.y }}>
              {note.icon && <Icon name={note.icon} size={14} />}
              {note.text}
            </span>
          ))}
          <FirstTest lit={scene.firstTestLit} place={FIRST_TEST.place} />
        </div>
      </div>
      <Legend />
    </section>
  )
}

function Stack({ scene, openId, onOpen }) {
  return (
    <div className="agent-stack" data-tour="agent-map">
      {STACK.map((item) => (
        <section key={item.step ?? item.label} className={`agent-st ${item.attached ? 'is-attached' : ''}`}>
          <div className="agent-st-rail">{item.step ? <StepBadge step={item.step} scene={scene} /> : <span className="agent-st-dot" />}</div>
          <div className="agent-st-body">
            {item.label && <p className="agent-st-label">{item.label}</p>}
            {item.nodes?.map((id) => (
              <Fragment key={id}>
                <NodeCard id={id} scene={scene} selected={openId === id} onOpen={onOpen} />
                {subsOf(id).length > 0 && (
                  <div className="agent-subchips">
                    {subsOf(id).map((subId) => (
                      <SubChip key={subId} id={subId} scene={scene} selected={openId === subId} onOpen={onOpen} />
                    ))}
                  </div>
                )}
              </Fragment>
            ))}
            {item.firstTest && <FirstTest lit={scene.firstTestLit} />}
            {item.out && (
              <p className="agent-st-out">
                <EdgeLabel id={item.out[0]} scene={scene} />
                {item.out[1]}
              </p>
            )}
            {item.check && <LoopNote id={item.check} scene={scene} />}
            {item.note && (
              <p className="agent-st-out">
                <Icon name="lock" size={14} />
                {item.note}
              </p>
            )}
          </div>
        </section>
      ))}
    </div>
  )
}

function Rail({ scene, onOpen }) {
  return (
    <ol className="agent-rail" aria-label="Steps of a run">
      {STEPS.map((step) => (
        <li key={step.step}>
          <button data-state={stepState(step.step, scene)} onClick={(event) => onOpen(step.node, event.currentTarget)}>
            <span className="agent-rail-num">{step.step}</span>
            {step.label}
          </button>
        </li>
      ))}
    </ol>
  )
}

function LiveRunbar({ run, newest }) {
  return (
    <div className="agent-runbar" data-mode={isRunning(run) ? 'live' : 'last'} aria-live="polite">
      <span className="agent-runbar-tag">{isRunning(run) ? 'Live' : newest ? 'Last run' : 'Earlier run'}</span>
      <span className="agent-runbar-text">{run.title}</span>
      <span className="agent-runbar-aside">{runFacts(run)}</span>
    </div>
  )
}

// The list marks borrow the sidebar's: pulsing while working, a check when finished.
const RUN_MARK = { running: 'researching', finished: 'submitted', stopped: 'passed' }

function RunPicker({ runs, chosenId, onChoose }) {
  return (
    <section className="agent-steps agent-runs" aria-label="Recent runs" data-tour="agent-runs">
      <p className="agent-steps-title">Recent runs</p>
      <ul>
        {runs.map((run) => (
          <li key={run.id}>
            <button className="list-item" aria-current={run.id === chosenId ? 'page' : undefined} onClick={() => onChoose(run.id)}>
              <Mark stage={RUN_MARK[run.status] ?? 'new'} current={run.id === chosenId} />
              <span className="list-text">
                <strong>{run.title}</strong>
                <span>{runFacts(run)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

function LiveSteps({ run, steps }) {
  return <Steps title={isRunning(run) ? 'Latest steps' : 'How this run ended'} label={isRunning(run) ? 'Latest steps of the live run' : 'Last steps of this run'} steps={steps} />
}

function Runbar({ scene }) {
  const { current } = scene
  return (
    <div className="agent-runbar" data-mode={current ? 'replay' : 'guide'} aria-live="polite">
      <span className="agent-runbar-tag">{current ? 'Replay' : 'Guide'}</span>
      {current && <span className="agent-runbar-step">{current.end ? 'Finished' : `Step ${current.step} of ${STEPS.length}`}</span>}
      <span className="agent-runbar-text">{current ? current.caption : GUIDE}</span>
      {current && <span className="agent-runbar-aside">Sample run, not live</span>}
    </div>
  )
}

function Panel({ id, open, scene, onClose }) {
  const closeButton = useRef(null)
  const body = useRef(null)

  useEffect(() => {
    if (!open) return
    body.current.scrollTop = 0
    closeButton.current.focus({ preventScroll: true })
  }, [open, id])

  const panel = id && panelFor(id)
  const node = id && NODES[id]
  return (
    <>
      <div className={`agent-scrim ${open ? 'show' : ''}`} onClick={onClose} />
      <aside className={`agent-panel ${open ? 'open' : ''}`} data-tour={open ? 'agent-panel' : undefined} role="dialog" aria-modal="false" aria-labelledby="agent-panel-title">
        {panel && (
          <>
            <div className="agent-panel-head">
              <span className={`agent-node-icon ${panel.round ? 'is-round' : ''}`}>
                <Icon name={panel.icon} size={20} />
              </span>
              <div className="agent-panel-titles">
                <p className="agent-panel-kicker">{panel.kicker}</p>
                <h2 id="agent-panel-title">{panel.title}</h2>
              </div>
              <button ref={closeButton} className="icon-button" aria-label="Close details" onClick={onClose}>
                <Icon name="close" size={18} stroke={2.2} />
              </button>
            </div>
            <div className="agent-panel-body" ref={body}>
              {node && !node.planned && (
                <p className="agent-panel-status" data-status={scene.status[id]}>
                  <StatusChip status={scene.status[id]} />
                  {PANEL_STATUS[scene.mode] ?? (scene.started ? 'In the replay of a sample run' : 'Before a run starts')}
                </p>
              )}
              <p className="agent-panel-lead">{panel.lead}</p>
              <Facts rows={panel.rows.map((row) => ({ label: row.label, value: <PanelValue value={row.value} />, tone: row.tone }))} />
            </div>
          </>
        )}
      </aside>
    </>
  )
}

export function Agent({ sessionId }) {
  const [outcome, setOutcome] = useState('pursue')
  const [beat, setBeat] = useState(-1)
  const [playing, setPlaying] = useState(false)
  const [panelId, setPanelId] = useState(null)
  const [panelOpen, setPanelOpen] = useState(false)
  const returnFocus = useRef(null)
  const live = useLiveRuns(sessionId)
  const beats = RUNS[outcome]
  const started = beat >= 0
  // The chosen real run shows until a replay starts, and comes back on Reset.
  const shown = live?.sessions.find((candidate) => candidate.id === live.session_id)
  const run = !started && shown
  const scene = run ? liveScene(run) : sceneAt(outcome, beat)

  useEffect(() => {
    if (!playing) return
    const timer = setTimeout(() => {
      setBeat(beat + 1)
      if (beat + 1 === beats.length - 1) setPlaying(false)
    }, beatLength(beats[beat]))
    return () => clearTimeout(timer)
  }, [playing, beat, beats])

  const closePanel = () => {
    setPanelOpen(false)
    returnFocus.current?.focus({ preventScroll: true })
  }

  useEffect(() => {
    if (!panelOpen) return
    const onKey = (event) => event.key === 'Escape' && closePanel()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [panelOpen])

  const openPanel = (id, trigger) => {
    returnFocus.current = trigger
    setPanelId(id)
    setPanelOpen(true)
  }

  const play = () => {
    setBeat(0)
    setPlaying(true)
  }

  const reset = () => {
    setPlaying(false)
    setBeat(-1)
  }

  const chooseOutcome = (next) => {
    setOutcome(next)
    reset()
  }

  const openId = panelOpen ? panelId : null
  return (
    <div className="agent">
      <header className="agent-head">
        <div className="agent-head-text">
          <h1 className="step-title">The bid agent</h1>
          <p className="step-intro">
            Five Claude agents work each RFP on their own. The Operator hands out the work, and four helpers read, qualify, research, and draft. Doug reads one finished packet, and nothing is sent without him.
          </p>
          <p className="agent-intro-note">All five run on Anthropic Managed Agents. When this page is online, it shows their real runs.</p>
        </div>
        <div className="agent-controls">
          <span className="agent-outcome">
            Sample outcome
            <span className="segmented" role="group" aria-label="Sample outcome">
              {['pursue', 'pass'].map((option) => (
                <button key={option} aria-pressed={outcome === option} disabled={playing} onClick={() => chooseOutcome(option)}>
                  {option === 'pursue' ? 'Pursue' : 'Pass'}
                </button>
              ))}
            </span>
          </span>
          {started && !playing && (
            <button className="btn btn-secondary" onClick={reset}>
              Reset
            </button>
          )}
          <button className="btn btn-primary" onClick={playing ? () => setPlaying(false) : play}>
            <Icon name={playing ? 'stop' : started ? 'replay' : 'play'} size={18} stroke={2.2} />
            {playing ? 'Stop' : started ? 'Replay again' : 'Play sample replay'}
          </button>
        </div>
      </header>

      {live && (
        <RunPicker
          runs={live.sessions}
          chosenId={shown?.id}
          onChoose={(id) => {
            reset()
            navigate(`/agent/${id}`)
          }}
        />
      )}
      {run ? <LiveRunbar run={run} newest={run.id === live.sessions[0].id} /> : <Runbar scene={scene} />}
      {run && <LiveSteps run={run} steps={live.steps} />}
      <Rail scene={scene} onOpen={openPanel} />
      <Canvas scene={scene} openId={openId} onOpen={openPanel} />
      <Stack scene={scene} openId={openId} onOpen={openPanel} />
      <Panel id={panelId} open={panelOpen} scene={scene} onClose={closePanel} />
    </div>
  )
}
