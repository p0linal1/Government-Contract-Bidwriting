"""Serves the Cadocary app, the live view of the bid agent behind its Agent page, and the RFP Library.

    npm --prefix prototype run build
    ANTHROPIC_API_KEY=... uvicorn main:app --app-dir server --port 8080

The key stays on the server. The browser only ever sees these endpoints' answers.
"""

import os
import re
import urllib.error
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import answers
import live
import rfp_library

REPO = Path(__file__).resolve().parent.parent
APP_BUILD = REPO / "prototype" / "dist"

# The files the Facts page shows. Only these: private.md, with prices and contacts, never leaves the team.
FACT_FILES = {
    "facts": REPO / "agent" / "memory" / "cadocary-facts" / "README.md",
    "questions": REPO / "docs" / "questions-for-doug.md",
    "tracker": REPO / "docs" / "context-tracker.md",
}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


# A SAM.gov notice id, which is also the RFP's id in the library.
RFP_ID = re.compile(r"[0-9a-f]{32}")
SESSION_ID = re.compile(r"sesn_\w+")
QUESTION_ID = re.compile(r"[a-z0-9-]{1,40}")


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


@app.get("/api/rfp/{rfp_id}/proposal")
def proposal(rfp_id: str):
    found = RFP_ID.fullmatch(rfp_id) and answer(lambda: rfp_library.proposal(rfp_id))
    if not found:
        raise HTTPException(404, "No draft for that RFP in the library")
    return found


@app.get("/api/facts/{name}", response_class=PlainTextResponse)
def facts(name: str):
    path = FACT_FILES.get(name)
    if path is None:
        raise HTTPException(404, "No such facts file")
    return path.read_text()


class Answer(BaseModel):
    choice: str = Field("", max_length=200)
    choices: list[str] = Field(default_factory=list, max_length=20)
    rows: dict[str, str] = Field(default_factory=dict, max_length=20)
    text: str = Field("", max_length=5000)
    note: str = Field("", max_length=5000)
    skipped: bool = False


def answers_allowed(code):
    if not answers.configured():
        raise HTTPException(503, "Answers are not set up on this server")
    if not answers.code_matches(code):
        raise HTTPException(403, "Open the private link to see or change the answers")


@app.get("/api/answers")
def doug_answers(x_answers_code: str = Header("")):
    answers_allowed(x_answers_code)
    try:
        saved, _ = answers.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise HTTPException(502, f"Could not read the answers: {error}") from error
    return {"answers": saved}


@app.put("/api/answers/{question_id}")
def save_answer(question_id: str, answer: Answer, x_answers_code: str = Header("")):
    answers_allowed(x_answers_code)
    if not QUESTION_ID.fullmatch(question_id):
        raise HTTPException(404, "No such question")
    try:
        return {"savedAt": answers.save(question_id, answer.model_dump())}
    except (urllib.error.URLError, TimeoutError) as error:
        raise HTTPException(502, f"Could not save the answer: {error}") from error


app.mount("/", StaticFiles(directory=APP_BUILD, html=True), name="app")
