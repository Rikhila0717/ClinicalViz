"""
FastAPI application — single /query endpoint.

The server is deliberately minimal: validation lives in Pydantic schemas,
business logic lives in the agent module, and this file only wires HTTP
concerns (CORS, error handling, health check).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent import process_query
from app.config import settings
from app.schemas import QueryRequest, QueryResponse

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    detail: str


app = FastAPI(
    title="ClinicalTrials.gov Query-to-Visualization Agent",
    version="1.0.0",
    description=(
        "AI-powered backend that converts natural-language clinical-trial "
        "questions into structured visualization specifications, backed by "
        "live data from the ClinicalTrials.gov API.\n\n"
        "## How it works\n"
        "1. Send a natural-language `query` (with optional filters) to **POST /query**\n"
        "2. An AI agent interprets the question, fetches data from ClinicalTrials.gov, "
        "and selects the best visualization type\n"
        "3. You receive a structured JSON spec (type, encoding, data, citations) "
        "ready for any charting library\n\n"
        "## Supported visualization types\n"
        "`bar_chart` · `grouped_bar_chart` · `time_series` · `scatter_plot` · "
        "`pie_chart` · `histogram` · `network_graph`"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", summary="Health check", tags=["System"])
async def health():
    """Returns `{\"status\": \"ok\"}` when the service is running."""
    return {"status": "ok"}


@app.post(
    "/query",
    response_model=QueryResponse,
    response_model_exclude_none=True,
    summary="Query clinical trials and get a visualization spec",
    tags=["Query"],
    responses={
        200: {"description": "Visualization spec with data and metadata"},
        422: {
            "model": ErrorResponse,
            "description": "Validation error — missing or invalid request fields",
        },
        500: {
            "model": ErrorResponse,
            "description": (
                "Internal server error — typically caused by an upstream failure "
                "(ClinicalTrials.gov API error, LLM error, or invalid LLM output)"
            ),
        },
    },
)
async def query(request: QueryRequest):
    """
    Accept a natural-language question about clinical trials and return a
    structured visualization specification with data and metadata.

    **Example request:**
    ```json
    {
      "query": "How are Diabetes trials distributed across phases?",
      "condition": "Diabetes"
    }
    ```
    """
    try:
        return await process_query(request)
    except Exception as exc:
        logger.exception("Error processing query")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Frontend demo ────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
