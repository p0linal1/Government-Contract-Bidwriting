"""Serves the Cadocary app and the live view of the bid agent behind its Agent page.

    npm --prefix prototype run build
    ANTHROPIC_API_KEY=... uvicorn main:app --app-dir server --port 8080

The key stays on the server. The browser only ever sees /api/agent/live's answer.
"""

import os
import urllib.error
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

import live

APP_BUILD = Path(__file__).resolve().parent.parent / "prototype" / "dist"

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/api/agent/live")
def agent_live():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set on the server")
    try:
        return live.snapshot()
    except (urllib.error.URLError, TimeoutError) as error:
        raise HTTPException(502, f"Managed Agents request failed: {error}") from error


app.mount("/", StaticFiles(directory=APP_BUILD, html=True), name="app")
