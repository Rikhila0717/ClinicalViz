"""Tests for request/response schema validation."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    Citation,
    DataPoint,
    Encoding,
    FieldEncoding,
    QueryRequest,
    QueryResponse,
    ResponseMeta,
    VisualizationSpec,
    VisualizationType,
)


class TestQueryRequest:
    def test_minimal_valid(self):
        req = QueryRequest(query="How many trials for aspirin?")
        assert req.query == "How many trials for aspirin?"
        assert req.drug_name is None

    def test_full_valid(self):
        req = QueryRequest(
            query="Trials over time",
            drug_name="Pembrolizumab",
            condition="Lung Cancer",
            trial_phase="Phase 3",
            sponsor="Merck",
            country="United States",
            start_year=2015,
            end_year=2024,
            status="RECRUITING",
        )
        assert req.drug_name == "Pembrolizumab"
        assert req.start_year == 2015

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="")

    def test_query_too_long_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="x" * 2001)

    def test_year_bounds(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="test", start_year=1800)
        with pytest.raises(ValidationError):
            QueryRequest(query="test", end_year=2200)


class TestVisualizationType:
    def test_all_types_exist(self):
        expected = {
            "bar_chart", "grouped_bar_chart", "time_series",
            "scatter_plot", "pie_chart", "histogram", "network_graph",
        }
        actual = {vt.value for vt in VisualizationType}
        assert expected == actual


class TestDataPoint:
    def test_with_citations(self):
        dp = DataPoint(
            values={"phase": "Phase 1", "count": 10},
            citations=[Citation(nct_id="NCT001", excerpt="A study")],
        )
        assert dp.values["count"] == 10
        assert dp.citations[0].nct_id == "NCT001"

    def test_without_citations(self):
        dp = DataPoint(values={"x": 1})
        assert dp.citations == []


class TestQueryResponse:
    def test_round_trip(self):
        resp = QueryResponse(
            visualization=VisualizationSpec(
                type=VisualizationType.BAR_CHART,
                title="Test",
                encoding=Encoding(
                    x=FieldEncoding(field="phase", type="nominal"),
                    y=FieldEncoding(field="count", type="quantitative"),
                ),
                data=[DataPoint(values={"phase": "Phase 1", "count": 5})],
            ),
            meta=ResponseMeta(
                total_studies_analyzed=5,
                query_interpretation="Test interpretation",
            ),
        )
        d = resp.model_dump()
        assert d["visualization"]["type"] == "bar_chart"
        rebuilt = QueryResponse.model_validate(d)
        assert rebuilt.visualization.title == "Test"
