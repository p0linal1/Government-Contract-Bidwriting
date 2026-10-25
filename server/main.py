"""Serves the Cadocary app, the live view of the bid agent behind its Agent page, and the RFP Library.

    npm --prefix prototype run build
    ANTHROPIC_API_KEY=... uvicorn main:app --app-dir server --port 8080

The key stays on the server. The browser only ever sees these endpoints' answers.
"""

import os
import re
import urllib.error
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

import live
import rfp_library

APP_BUILD = Path(__file__).resolve().parent.parent / "prototype" / "dist"

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


# A SAM.gov notice id, which is also the RFP's id in the library.
RFP_ID = re.compile(r"[0-9a-f]{32}")
SESSION_ID = re.compile(r"sesn_\w+")


def answer(read):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set on the server")
    try:
        return read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise HTTPException(502, f"Anthropic API request failed: {error}") from error


@app.get("/api/agent/live")
def agent_live(session: str | None = None):
    """The latest runs, and the steps of the run asked for, or of the newest one."""
    found = (session is None or SESSION_ID.fullmatch(session)) and answer(lambda: live.snapshot(session))
    if not found:
        raise HTTPException(404, "No recent run with that id")
    return rfp_library.scrubbed(found)


@app.get("/api/library")
def library():
    return answer(rfp_library.library)


@app.get("/api/rfp/{rfp_id}")
def rfp(rfp_id: str):
    found = RFP_ID.fullmatch(rfp_id) and answer(lambda: rfp_library.rfp(rfp_id))
    if not found:
        raise HTTPException(404, "No RFP with that id in the library")
    return found


app.mount("/", StaticFiles(directory=APP_BUILD, html=True), name="app")
