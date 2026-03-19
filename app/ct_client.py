"""
Async HTTP client for the ClinicalTrials.gov v2 API.

Key design decisions
--------------------
* **Async + rate-limiting**: Uses asyncio.Semaphore + run_in_executor to stay
  under the 3 req/s hard cap without blocking the event loop.
* **Auto-pagination**: Follows nextPageToken up to CT_API_MAX_PAGES so we can
  aggregate hundreds of studies while bounding latency.
* **Thin wrapper**: Returns raw dicts so the agent layer can pick whichever
  fields it needs — no premature abstraction.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

_semaphore = asyncio.Semaphore(int(settings.CT_API_RATE_LIMIT_RPS))

# Valid overallStatus values accepted by the ClinicalTrials.gov v2 API
VALID_STATUSES = {
    "ACTIVE_NOT_RECRUITING",
    "COMPLETED",
    "ENROLLING_BY_INVITATION",
    "NOT_YET_RECRUITING",
    "RECRUITING",
    "SUSPENDED",
    "TERMINATED",
    "WITHDRAWN",
    "AVAILABLE",
    "NO_LONGER_AVAILABLE",
    "TEMPORARILY_NOT_AVAILABLE",
    "APPROVED_FOR_MARKETING",
    "WITHHELD",
    "UNKNOWN",
}

# Common LLM mistakes → correct API values
_STATUS_ALIASES: dict[str, str] = {
    "active": "ACTIVE_NOT_RECRUITING,RECRUITING",
    "open": "RECRUITING,ENROLLING_BY_INVITATION",
    "closed": "COMPLETED,TERMINATED,WITHDRAWN",
    "ongoing": "RECRUITING,ACTIVE_NOT_RECRUITING,ENROLLING_BY_INVITATION",
    "not recruiting": "ACTIVE_NOT_RECRUITING",
    "enrolling": "RECRUITING,ENROLLING_BY_INVITATION",
}


def _normalize_status(raw: str | None) -> str | None:
    """Map free-text or LLM-generated status strings to valid API enum(s)."""
    if not raw:
        return None
    upper = raw.strip().upper()

    # Already a valid value (possibly comma-separated)
    parts = [p.strip() for p in upper.split(",")]
    if all(p in VALID_STATUSES for p in parts):
        return upper

    # Check alias table (case-insensitive)
    alias = _STATUS_ALIASES.get(raw.strip().lower())
    if alias:
        return alias

    logger.warning("Dropping unrecognised status filter: %s", raw)
    return None

# Persistent session for connection pooling and consistent TLS fingerprint
_session = requests.Session()
_session.headers.update({"Accept": "application/json"})


def _sync_get(url: str, params: dict) -> dict:
    resp = _session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


async def _rate_limited_get(url: str, params: dict) -> dict:
    """GET with concurrency-based rate limiting, offloaded to a thread."""
    async with _semaphore:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, partial(_sync_get, url, params))
        await asyncio.sleep(1.0 / settings.CT_API_RATE_LIMIT_RPS)
        return result


async def search_studies(
    query_term: str | None = None,
    condition: str | None = None,
    intervention: str | None = None,
    overall_status: str | None = None,
    phase: str | None = None,
    sponsor: str | None = None,
    page_size: int | None = None,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """
    Search ClinicalTrials.gov and return a flat list of study dicts.

    Handles pagination transparently; callers receive the merged list.
    """
    page_size = page_size or settings.CT_API_PAGE_SIZE
    max_pages = max_pages or settings.CT_API_MAX_PAGES

    params: dict[str, Any] = {
        "pageSize": page_size,
        "countTotal": "true",
    }
    if query_term:
        params["query.term"] = query_term
    if condition:
        params["query.cond"] = condition
    if intervention:
        params["query.intr"] = intervention
    normalized_status = _normalize_status(overall_status)
    if normalized_status:
        params["filter.overallStatus"] = normalized_status
    if phase:
        params["filter.phase"] = phase

    url = f"{settings.CT_API_BASE}/studies"
    all_studies: list[dict[str, Any]] = []

    for _ in range(max_pages):
        body = await _rate_limited_get(url, params)
        studies = body.get("studies", [])
        all_studies.extend(studies)
        next_token = body.get("nextPageToken")
        if not next_token or not studies:
            break
        params["pageToken"] = next_token

    logger.info("Fetched %d studies from ClinicalTrials.gov", len(all_studies))
    return all_studies


# ---------------------------------------------------------------------------
# Convenience field extractors
# ---------------------------------------------------------------------------

def extract_nct_id(study: dict) -> str:
    return (
        study.get("protocolSection", {})
        .get("identificationModule", {})
        .get("nctId", "")
    )


def extract_brief_title(study: dict) -> str:
    return (
        study.get("protocolSection", {})
        .get("identificationModule", {})
        .get("briefTitle", "")
    )


def extract_phases(study: dict) -> list[str]:
    return (
        study.get("protocolSection", {})
        .get("designModule", {})
        .get("phases", [])
    )


def extract_start_date(study: dict) -> str | None:
    return (
        study.get("protocolSection", {})
        .get("statusModule", {})
        .get("startDateStruct", {})
        .get("date")
    )


def extract_overall_status(study: dict) -> str:
    return (
        study.get("protocolSection", {})
        .get("statusModule", {})
        .get("overallStatus", "")
    )


def extract_conditions(study: dict) -> list[str]:
    return (
        study.get("protocolSection", {})
        .get("conditionsModule", {})
        .get("conditions", [])
    )


def extract_interventions(study: dict) -> list[dict]:
    return (
        study.get("protocolSection", {})
        .get("armsInterventionsModule", {})
        .get("interventions", [])
    )


def extract_sponsor(study: dict) -> str:
    return (
        study.get("protocolSection", {})
        .get("sponsorCollaboratorsModule", {})
        .get("leadSponsor", {})
        .get("name", "")
    )


def extract_locations(study: dict) -> list[dict]:
    return (
        study.get("protocolSection", {})
        .get("contactsLocationsModule", {})
        .get("locations", [])
    )


def extract_enrollment(study: dict) -> int | None:
    info = (
        study.get("protocolSection", {})
        .get("designModule", {})
        .get("enrollmentInfo", {})
    )
    count = info.get("count")
    return int(count) if count is not None else None
