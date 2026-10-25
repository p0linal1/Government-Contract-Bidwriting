# Government Contract Bidwriting

Built at the Seattle AI Week Claude Impact Lab on October 25, 2026, for Cadocary LLC. The goal is an agent that finds, qualifies, researches, and drafts government bids for the owner, Doug, who reviews each finished bid once and sends it himself.

The full project context, including Doug's decisions, the plan, what the reviews found, and the open decisions:

@docs/context.md

## Map

- `scripts/`, `bin/`, `.claude/agents/sam-researcher.md`: SAM.gov sourcing. See `README.md`.
- `docs/fact-sheet.md`: the first task, Doug's approved facts sheet.
- `docs/managed-agents.md`: reference for Anthropic Managed Agents, where the bid agent will run.
- `docs/reviews/`: the plan and the three full reviews of it.
- `docs/questions-for-doug.md`: what we still need from Doug to qualify and draft truthfully.

## Rules

- Scripts do every fetch and file write. Agents only make judgment calls.
- No agent may send, submit, upload, or email a bid. Doug sends.
- The agent may only claim what is on Doug's approved facts sheet. Every number carries a source or a "guess" label.
- Never commit prices, logins, or any key. `profile.json` is tracked on purpose — it holds only
  public SAM.gov registration data (UEI, CAGE, codes, capabilities). Nothing else real goes in.
- When a team decision in `docs/context.md` gets made, update that page.
