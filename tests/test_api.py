"""Tests for the FastAPI endpoints (unit-level with mocked agent)."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    DataPoint,
    Encoding,
    FieldEncoding,
    QueryResponse,
    ResponseMeta,
    VisualizationSpec,
    VisualizationType,
)

client = TestClient(app)


def _fake_response() -> QueryResponse:
    return QueryResponse(
        visualization=VisualizationSpec(
            type=VisualizationType.BAR_CHART,
            title="Trials by Phase",
            encoding=Encoding(
                x=FieldEncoding(field="phase", type="nominal"),
                y=FieldEncoding(field="trial_count", type="quantitative"),
            ),
            data=[
                DataPoint(values={"phase": "Phase 1", "trial_count": 10}),
                DataPoint(values={"phase": "Phase 2", "trial_count": 25}),
            ],
        ),
        meta=ResponseMeta(
            total_studies_analyzed=35,
            query_interpretation="Count trials by phase.",
        ),
    )


class TestHealthEndpoint:
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestQueryEndpoint:
    @patch("app.main.process_query", new_callable=AsyncMock)
    def test_valid_request(self, mock_pq):
        mock_pq.return_value = _fake_response()
        resp = client.post("/query", json={"query": "Trials by phase for aspirin"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["visualization"]["type"] == "bar_chart"
        assert len(body["visualization"]["data"]) == 2

    def test_empty_query_rejected(self):
        resp = client.post("/query", json={"query": ""})
        assert resp.status_code == 422

    def test_missing_query_rejected(self):
        resp = client.post("/query", json={})
        assert resp.status_code == 422

    @patch("app.main.process_query", new_callable=AsyncMock)
    def test_optional_fields_forwarded(self, mock_pq):
        mock_pq.return_value = _fake_response()
        resp = client.post(
            "/query",
            json={
                "query": "Trials for Pembrolizumab",
                "drug_name": "Pembrolizumab",
                "condition": "Lung Cancer",
                "start_year": 2015,
            },
        )
        assert resp.status_code == 200
        call_arg = mock_pq.call_args[0][0]
        assert call_arg.drug_name == "Pembrolizumab"
        assert call_arg.start_year == 2015

    @patch("app.main.process_query", new_callable=AsyncMock)
    def test_agent_error_returns_500(self, mock_pq):
        mock_pq.side_effect = RuntimeError("LLM unavailable")
        resp = client.post("/query", json={"query": "test"})
        assert resp.status_code == 500

    def test_response_has_meta(self):
        with patch("app.main.process_query", new_callable=AsyncMock) as mock_pq:
            mock_pq.return_value = _fake_response()
            resp = client.post("/query", json={"query": "test"})
            body = resp.json()
            assert "meta" in body
            assert body["meta"]["source"] == "clinicaltrials.gov"
