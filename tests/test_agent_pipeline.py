"""Tests for the full agent pipeline with mocked LLM and API calls."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agent import (
    QueryPlan,
    _aggregate_compare_drugs,
    _aggregate_condition_drug_network,
    _build_planner_user_message,
    process_query,
)
from app.schemas import QueryRequest


def _make_study(
    nct_id="NCT001", title="Test", phases=None, condition="Diabetes",
    intervention="Metformin", sponsor="Corp", start_date="2022-01-01",
):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": title},
            "statusModule": {
                "overallStatus": "RECRUITING",
                "startDateStruct": {"date": start_date},
            },
            "designModule": {
                "phases": phases or ["PHASE2"],
                "enrollmentInfo": {"count": 100},
            },
            "conditionsModule": {"conditions": [condition]},
            "armsInterventionsModule": {
                "interventions": [{"type": "DRUG", "name": intervention}],
            },
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor}},
            "contactsLocationsModule": {"locations": []},
        }
    }


FAKE_STUDIES = [_make_study(), _make_study(nct_id="NCT002", phases=["PHASE3"])]


class TestBuildPlannerUserMessage:
    def test_minimal(self):
        req = QueryRequest(query="Test question")
        msg = _build_planner_user_message(req)
        assert "Question: Test question" in msg

    def test_all_fields(self):
        req = QueryRequest(
            query="Test",
            drug_name="Aspirin",
            condition="Headache",
            trial_phase="Phase 1",
            sponsor="Bayer",
            country="Germany",
            start_year=2020,
            end_year=2025,
            status="RECRUITING",
        )
        msg = _build_planner_user_message(req)
        assert "Drug filter: Aspirin" in msg
        assert "Condition filter: Headache" in msg
        assert "Phase filter: Phase 1" in msg
        assert "Sponsor filter: Bayer" in msg
        assert "Country filter: Germany" in msg
        assert "Start year" in msg
        assert "End year" in msg
        assert "Status filter: RECRUITING" in msg


class TestProcessQuery:
    """Test the full pipeline with mocked LLM and API."""

    def _mock_plan(self, aggregation="count_by_phase", viz="bar_chart", **kwargs):
        return QueryPlan(
            aggregation=aggregation,
            visualization_type=viz,
            chart_title="Test Chart",
            query_interpretation="Test interpretation",
            condition=kwargs.get("condition"),
            intervention=kwargs.get("intervention"),
            status=kwargs.get("status"),
            phase=kwargs.get("phase"),
            compare_items=kwargs.get("compare_items", []),
        )

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    @patch("app.agent._plan_query", new_callable=AsyncMock)
    async def test_count_by_phase(self, mock_plan, mock_search):
        mock_plan.return_value = self._mock_plan()
        mock_search.return_value = FAKE_STUDIES
        req = QueryRequest(query="Trials by phase")

        resp = await process_query(req)
        assert resp.visualization.type == "bar_chart"
        assert resp.visualization.title == "Test Chart"
        assert len(resp.visualization.data) > 0
        assert resp.meta.total_studies_analyzed == 2

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    @patch("app.agent._plan_query", new_callable=AsyncMock)
    async def test_count_by_year(self, mock_plan, mock_search):
        mock_plan.return_value = self._mock_plan("count_by_year", "time_series")
        mock_search.return_value = FAKE_STUDIES
        req = QueryRequest(query="Trials over time")

        resp = await process_query(req)
        assert resp.visualization.type == "time_series"

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    @patch("app.agent._plan_query", new_callable=AsyncMock)
    async def test_count_by_status(self, mock_plan, mock_search):
        mock_plan.return_value = self._mock_plan("count_by_status", "bar_chart")
        mock_search.return_value = FAKE_STUDIES
        req = QueryRequest(query="Status breakdown")

        resp = await process_query(req)
        assert any(
            d.values.get("status") == "RECRUITING"
            for d in resp.visualization.data
        )

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    @patch("app.agent._plan_query", new_callable=AsyncMock)
    async def test_sponsor_drug_network(self, mock_plan, mock_search):
        mock_plan.return_value = self._mock_plan(
            "sponsor_drug_network", "network_graph"
        )
        mock_search.return_value = FAKE_STUDIES
        req = QueryRequest(query="Sponsor network")

        resp = await process_query(req)
        assert resp.visualization.type == "network_graph"
        assert resp.visualization.encoding.source is not None
        assert resp.visualization.encoding.target is not None

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    @patch("app.agent._plan_query", new_callable=AsyncMock)
    async def test_condition_drug_network(self, mock_plan, mock_search):
        mock_plan.return_value = self._mock_plan(
            "condition_drug_network", "network_graph"
        )
        mock_search.return_value = FAKE_STUDIES
        req = QueryRequest(query="Condition drug network")

        resp = await process_query(req)
        assert resp.visualization.type == "network_graph"

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    @patch("app.agent._plan_query", new_callable=AsyncMock)
    async def test_drug_cooccurrence_network(self, mock_plan, mock_search):
        studies = [
            _make_study(nct_id="NCT001"),
        ]
        studies[0]["protocolSection"]["armsInterventionsModule"]["interventions"] = [
            {"type": "DRUG", "name": "DrugA"},
            {"type": "DRUG", "name": "DrugB"},
        ]
        mock_plan.return_value = self._mock_plan(
            "drug_cooccurrence_network", "network_graph"
        )
        mock_search.return_value = studies
        req = QueryRequest(query="Drug co-occurrence")

        resp = await process_query(req)
        assert resp.visualization.type == "network_graph"

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    @patch("app.agent._plan_query", new_callable=AsyncMock)
    async def test_compare_drugs(self, mock_plan, mock_search):
        mock_plan.return_value = self._mock_plan(
            "compare_drugs_by_phase", "grouped_bar_chart",
            compare_items=["Aspirin", "Ibuprofen"],
        )
        mock_search.return_value = FAKE_STUDIES
        req = QueryRequest(query="Compare Aspirin vs Ibuprofen")

        resp = await process_query(req)
        assert resp.visualization.type == "grouped_bar_chart"

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    @patch("app.agent._plan_query", new_callable=AsyncMock)
    async def test_unknown_aggregation_fallback(self, mock_plan, mock_search):
        mock_plan.return_value = self._mock_plan("totally_bogus", "bar_chart")
        mock_search.return_value = FAKE_STUDIES
        req = QueryRequest(query="Something weird")

        resp = await process_query(req)
        assert resp.visualization.type == "bar_chart"
        assert "count_by_phase" in resp.meta.assumptions[0]

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    @patch("app.agent._plan_query", new_callable=AsyncMock)
    async def test_filters_in_meta(self, mock_plan, mock_search):
        mock_plan.return_value = self._mock_plan(
            condition="Diabetes", intervention="Metformin",
            phase="PHASE2", status="RECRUITING",
        )
        mock_search.return_value = FAKE_STUDIES
        req = QueryRequest(query="Test")

        resp = await process_query(req)
        assert resp.meta.filters_applied["condition"] == "Diabetes"
        assert resp.meta.filters_applied["drug_name"] == "Metformin"
        assert resp.meta.filters_applied["phase"] == "PHASE2"
        assert resp.meta.filters_applied["status"] == "RECRUITING"

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    @patch("app.agent._plan_query", new_callable=AsyncMock)
    async def test_empty_studies(self, mock_plan, mock_search):
        mock_plan.return_value = self._mock_plan()
        mock_search.return_value = []
        req = QueryRequest(query="No results")

        resp = await process_query(req)
        assert resp.meta.total_studies_analyzed == 0
        assert resp.visualization.data == []


class TestAggregateCompareDrugs:
    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    async def test_with_items(self, mock_search):
        mock_search.return_value = FAKE_STUDIES
        plan = QueryPlan(
            aggregation="compare_drugs_by_phase",
            visualization_type="grouped_bar_chart",
            compare_items=["DrugA", "DrugB"],
        )
        req = QueryRequest(query="Compare")
        data, key = await _aggregate_compare_drugs(plan, req)
        drugs = {d["values"]["drug"] for d in data}
        assert "DrugA" in drugs
        assert "DrugB" in drugs

    @pytest.mark.asyncio
    @patch("app.agent.search_studies", new_callable=AsyncMock)
    async def test_fallback_items(self, mock_search):
        """When compare_items is empty, falls back to intervention or defaults."""
        mock_search.return_value = FAKE_STUDIES
        plan = QueryPlan(
            aggregation="compare_drugs_by_phase",
            visualization_type="grouped_bar_chart",
            compare_items=[],
            intervention="Aspirin",
        )
        req = QueryRequest(query="Compare")
        data, _ = await _aggregate_compare_drugs(plan, req)
        drugs = {d["values"]["drug"] for d in data}
        assert "Aspirin" in drugs


class TestConditionDrugNetwork:
    def test_builds_edges(self):
        studies = [_make_study(), _make_study(condition="Cancer", intervention="Chemo")]
        data, key = _aggregate_condition_drug_network(studies)
        assert len(data) > 0
        assert data[0]["values"]["condition"]
        assert data[0]["values"]["drug"]
