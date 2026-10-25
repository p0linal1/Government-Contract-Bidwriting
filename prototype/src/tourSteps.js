// The guided walkthrough, in order. `route` is where the step happens, `target` is the part of the
// page it points at, and `open` is a fold or a panel to open first. A step with no target, or
// whose target does not appear, shows its card in the middle of the screen.

const VA_RFP = 'f50d635e4b9d4404916c47df2357fc66'
const DOT_RFP = 'e75a0aa6a1ad4cd1966d5f88f093d546'

export const TOUR_STEPS = [
  {
    title: 'Welcome',
    text: "This is Cadocary Bids: an agent that finds government RFPs, reads them, decides which ones Cadocary can win, researches them, and drafts the proposal. Everything here is today's real data.",
  },
  {
    route: '/bids',
    target: '[data-tour="library"]',
    title: 'The library',
    text: 'Every RFP the agent found on SAM.gov, grouped by where each one stands.',
  },
  {
    route: '/bids',
    target: '[data-tour="group-passed"]',
    title: 'Passed',
    text: 'The RFPs the agent worked today and decided to pass on. Each one shows its reason in one line.',
  },
  {
    route: `/bids/${VA_RFP}`,
    target: '[data-tour="rfp-progress"]',
    title: 'One RFP is one run',
    text: 'Opening an RFP shows the run that worked it. The tracker shows how far it got: Read, Qualify, Research, Draft, Packet.',
  },
  {
    route: `/bids/${VA_RFP}`,
    target: '[data-tour="rfp-reasons"]',
    title: 'The decision and why',
    text: 'The agent recommends passing on this one. Every reason quotes the RFP, with the page it came from.',
  },
  {
    route: `/bids/${VA_RFP}`,
    target: '[data-tour="run-steps"]',
    title: 'Every tool call',
    text: 'This is every step the agent took. Open one to see what it read or searched, and what came back.',
  },
  {
    route: `/bids/${DOT_RFP}`,
    target: '[data-tour="rfp-facts"]',
    title: 'Research and a draft',
    text: 'This one went further. Research estimated what it is worth, with sources, and the draft is written. The draft stays private to Doug.',
  },
  {
    route: '/agent',
    target: '[data-tour="agent-map"]',
    title: 'Five agents',
    text: 'The Operator hands out the work. Four helpers read, qualify, research, and draft, and each one reports back only to the Operator.',
  },
  {
    route: '/agent',
    target: '[data-tour="agent-runs"]',
    title: 'Pick a run',
    text: 'Pick any run to see its agents light up, from what really happened.',
  },
  {
    route: '/agent',
    open: '[data-tour="node-qualifier"]',
    target: '[data-tour="agent-panel"]',
    title: 'Inside an agent',
    text: 'Click any agent to see its model, its skill, and the tools it can use. This is the Qualifier, which decides go or no-go.',
  },
  {
    route: '/today',
    target: '[data-tour="today-cards"]',
    title: 'Today',
    text: "Today's real counts: what is ready, what is working, what passed, and what is waiting. The nearest deadlines are further down.",
  },
  {
    title: 'Doug decides',
    text: 'Doug reads one finished packet and decides. Nothing is sent without him.',
  },
]
