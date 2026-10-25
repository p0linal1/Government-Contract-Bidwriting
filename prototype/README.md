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
| Agent | The five Claude agents as a graph. Online, it lights up from the real runs. Click any part for what it does, or play a replay of a sample run |
| Settings | Company facts, products, files the agent reads, and the sources it checks |
| Start walkthrough | A guided tour of the live app in 12 steps. It dims the page, points at each part, and explains it. `?tour=4` in the address opens it at step 4 |

Every claim links to its source: the RFP page, a web page, or a Cadocary file.

## Change it

Needs Node 20.19 or later.

```bash
npm ci
npm run dev                     # http://localhost:5180, and phones on the same Wi-Fi
npm run build:click-through     # rebuilds click-through.html after a change
```

`click-through.html` is generated. Rebuild it after any change instead of editing it by hand.

## Online, with the real agent

The app is live at https://cadocary-bids-875086386085.us-west1.run.app. There, the Agent page shows the bid agent's real runs: it asks the small server in `server/` every 5 seconds, lights each agent from its real status, and lists the latest steps in plain English. When nothing is running, it shows the last run. The sample replay is still one click away. The offline `click-through.html` has no server, so it shows the replay alone.

The rest of the app reads the real RFP Library the same way. `/api/library` lists every stored SAM.gov notice with the newest run on each, and `/api/rfp/<id>` gives one RFP's packet, qualification, research, and summary. The sidebar groups them (working now, ready for you, to read, passed), Today counts them, and opening one shows the agent's reasons with their quotes and pages. The app has no login, so these answers carry only the fields the pages show, never a draft, and the server strips email addresses, phone numbers, and street addresses. Settings, Demo data, switches back to the sample bids for the recorded walkthrough. When the server does not answer, as in `click-through.html`, the app shows the sample bids on its own.

The server keeps the Anthropic key to itself; the browser never sees it. To run it on a laptop, from the repo root:

```bash
npm --prefix prototype run build
secret() { gcloud secrets versions access latest --project finchat-495622 --secret "$1"; }
ANTHROPIC_API_KEY="$(secret anthropic-api-key)" uvicorn main:app --app-dir server --port 8080   # needs fastapi and uvicorn from server/requirements.txt
```

To deploy a change, from the repo root:

```bash
gcloud run deploy cadocary-bids --source . --project finchat-495622 --region us-west1 \
  --allow-unauthenticated --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest --memory 512Mi
```

## How it's built

- `src/data.js`: the sample bids, company facts, and sources.
- `src/research/`: research notes and sources per bid. `lakewood.js` and `lakewoodPages.js` hold the real RFP text.
- `src/agent/live.js`: asks the server for the real runs. `server/live.py` reads them from Managed Agents.
- `src/agent/session.js`: builds the simulated agent runs. It uses Managed Agents' real event names (`agent.tool_use`, `agent.tool_result`, `session.status_idle`, and so on), so real sessions can replace the simulated ones without changing the screens.
- `src/store.jsx`: app state and the clock that moves bids forward through the stages.
- `src/screens/` and `src/bid/`: the screens.

React 19 on Vite, with no other dependencies.
