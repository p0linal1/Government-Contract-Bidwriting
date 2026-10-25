---
name: sam-research
description: Run the SAM.gov contract research for the business in profile.json and report the opportunities worth pursuing. Use when the user asks to run SAM research, find contracts, or check for new opportunities.
---

Launch the `sam-researcher` agent with the prompt "Run the SAM.gov research." and relay its reply
to the user as-is. Do not run the research steps yourself; the agent keeps the hundred-odd notice
descriptions out of this conversation.

If the user asked for something narrower, such as "only deadlines in the next two weeks", pass that
along in the prompt.
