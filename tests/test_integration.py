"""
Integration tests — hit the real ClinicalTrials.gov API (no LLM).

These validate that our client correctly talks to the live API and that our
aggregation pipeline produces valid output from real data. They are slower
and network-dependent, so they are marked with a custom marker.

Run with: pytest -m integration
"""

import pytest

from app.agent import _aggregate_count_by_phase, _aggregate_count_by_year
from app.ct_client import extract_nct_id, search_studies


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_returns_studies():
    studies = await search_studies(intervention="Pembrolizumab", page_size=5, max_pages=1)
    assert len(studies) > 0
    assert extract_nct_id(studies[0]) != ""


@pytest.mark.integration
@pytest.mark.asyncio
async def test_aggregation_on_live_data():
    studies = await search_studies(condition="Diabetes", page_size=20, max_pages=1)
    rows, key = _aggregate_count_by_phase(studies)
    assert len(rows) > 0
    assert all("phase" in r["values"] for r in rows)
    assert all(r["values"]["trial_count"] > 0 for r in rows)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_year_aggregation_on_live_data():
    studies = await search_studies(intervention="Aspirin", page_size=20, max_pages=1)
    rows, _ = _aggregate_count_by_year(studies)
    if rows:
        years = [r["values"]["year"] for r in rows]
        assert years == sorted(years)
