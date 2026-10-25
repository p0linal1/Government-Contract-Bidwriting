# Prototype

A clickable mock-up of the app Doug would use. The agent finds bids overnight, researches and drafts the ones Cadocary can win, and Doug reads each finished bid once and decides. No real agent runs here. Every bid is sample data except the City of Lakewood RFP, whose text and page quotes are real.

## Open it

Double-click `click-through.html`. It is one self-contained file, so it opens in any browser with no setup. You can also send it to someone as an attachment. It needs an internet connection only for fonts.

To start the morning over, go to Settings, then Demo data, then Reset the demo. Progress is saved in the browser.

## Where to look

| Screen | What it shows |
| --- | --- |
| Today | The morning brief: bids ready for Doug, what the agent is working on, what it skipped, and upcoming deadlines |
| A bid in the sidebar | That bid's path: Find, Research, Draft, Review. Each step shows the agent's live work, translated into plain English |
| Review the bid | Why Cadocary is competitive, the expected worth, the calls the agent made, and the proposal page by page with highlights and margin notes |
| How it works | The workflow: which steps are scripts and which are the agent |
| Settings | Company facts, products, files the agent reads, and the sources it checks |

Every claim links to its source: the RFP page, a web page, or a Cadocary file.

## Change it

Needs Node 20.19 or later.

```bash
npm ci
npm run dev                     # http://localhost:5180, and phones on the same Wi-Fi
npm run build:click-through     # rebuilds click-through.html after a change
```

`click-through.html` is generated. Rebuild it after any change instead of editing it by hand.

## How it's built

- `src/data.js`: the sample bids, company facts, and sources.
- `src/research/`: research notes and sources per bid. `lakewood.js` and `lakewoodPages.js` hold the real RFP text.
- `src/agent/session.js`: builds the simulated agent runs. It uses Managed Agents' real event names (`agent.tool_use`, `agent.tool_result`, `session.status_idle`, and so on), so real sessions can replace the simulated ones without changing the screens.
- `src/store.jsx`: app state and the clock that moves bids forward through the stages.
- `src/screens/` and `src/bid/`: the screens.

React 19 on Vite, with no other dependencies.
