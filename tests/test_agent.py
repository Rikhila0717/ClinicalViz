"""Tests for the agent's deterministic aggregation functions.

We test the aggregation layer exhaustively because it is the component that
turns raw API data into numbers shown in the visualization — any bug here
would propagate to the final output. The LLM planner is tested via
integration tests (test_integration.py) since it requires an API key.
"""

from app.agent import (
    _aggregate_count_by_condition,
    _aggregate_count_by_country,
    _aggregate_count_by_intervention,
    _aggregate_count_by_phase,
    _aggregate_count_by_sponsor,
    _aggregate_count_by_status,
    _aggregate_count_by_year,
    _aggregate_drug_cooccurrence,
    _aggregate_enrollment_by_phase,
    _aggregate_enrollment_by_year,
    _aggregate_sponsor_drug_network,
    _build_encoding,
    _resolve_viz_type,
    _unwrap_llm_json,
    _year_from_date,
)
from app.schemas import VisualizationType


def _make_study(
    nct_id="NCT001",
    title="Test Study",
    phases=None,
    start_date="2022-01-01",
    status="RECRUITING",
    conditions=None,
    interventions=None,
    sponsor="TestCorp",
    countries=None,
    enrollment=100,
):
    """Factory that builds a realistic study dict for testing."""
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": title},
            "statusModule": {
                "overallStatus": status,
                "startDateStruct": {"date": start_date},
            },
            "designModule": {
                "phases": phases or ["PHASE2"],
                "enrollmentInfo": {"count": enrollment},
            },
            "conditionsModule": {"conditions": conditions or ["Diabetes"]},
            "armsInterventionsModule": {
                "interventions": interventions
                or [{"type": "DRUG", "name": "Metformin"}],
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {"name": sponsor},
            },
            "contactsLocationsModule": {
                "locations": [
                    {"country": c, "city": "City"} for c in (countries or ["US"])
                ],
            },
        }
    }


STUDIES = [
    _make_study(nct_id="NCT001", phases=["PHASE1"], start_date="2020-03-01", enrollment=50),
    _make_study(nct_id="NCT002", phases=["PHASE2"], start_date="2020-07-01", enrollment=100),
    _make_study(nct_id="NCT003", phases=["PHASE2"], start_date="2021-01-01", enrollment=200),
    _make_study(nct_id="NCT004", phases=["PHASE3"], start_date="2021-06-01", enrollment=500),
    _make_study(
        nct_id="NCT005", phases=["PHASE3"], start_date="2022-02-01",
        enrollment=300, status="COMPLETED",
    ),
]


class TestYearFromDate:
    def test_valid(self):
        assert _year_from_date("2023-06-15") == 2023

    def test_none(self):
        assert _year_from_date(None) is None

    def test_malformed(self):
        assert _year_from_date("bad") is None


class TestCountByPhase:
    def test_counts(self):
        rows, key = _aggregate_count_by_phase(STUDIES)
        phase_counts = {r["values"]["phase"]: r["values"]["trial_count"] for r in rows}
        assert phase_counts["PHASE2"] == 2
        assert phase_counts["PHASE3"] == 2
        assert phase_counts["PHASE1"] == 1

    def test_citations_present(self):
        rows, _ = _aggregate_count_by_phase(STUDIES)
        for r in rows:
            assert len(r["citations"]) > 0
            assert "nct_id" in r["citations"][0]

    def test_empty_input(self):
        rows, _ = _aggregate_count_by_phase([])
        assert rows == []


class TestCountByYear:
    def test_counts(self):
        rows, _ = _aggregate_count_by_year(STUDIES)
        year_counts = {r["values"]["year"]: r["values"]["trial_count"] for r in rows}
        assert year_counts[2020] == 2
        assert year_counts[2021] == 2
        assert year_counts[2022] == 1

    def test_sorted_by_year(self):
        rows, _ = _aggregate_count_by_year(STUDIES)
        years = [r["values"]["year"] for r in rows]
        assert years == sorted(years)

    def test_year_filter(self):
        rows, _ = _aggregate_count_by_year(STUDIES, start_year=2021, end_year=2021)
        assert all(r["values"]["year"] == 2021 for r in rows)


class TestCountByStatus:
    def test_counts(self):
        rows, _ = _aggregate_count_by_status(STUDIES)
        status_map = {r["values"]["status"]: r["values"]["trial_count"] for r in rows}
        assert status_map["RECRUITING"] == 4
        assert status_map["COMPLETED"] == 1


class TestCountByCondition:
    def test_counts(self):
        rows, _ = _aggregate_count_by_condition(STUDIES)
        assert rows[0]["values"]["condition"] == "Diabetes"
        assert rows[0]["values"]["trial_count"] == 5


class TestCountByIntervention:
    def test_counts(self):
        rows, _ = _aggregate_count_by_intervention(STUDIES)
        assert rows[0]["values"]["intervention"] == "Metformin"


class TestCountBySponsor:
    def test_counts(self):
        rows, _ = _aggregate_count_by_sponsor(STUDIES)
        assert rows[0]["values"]["sponsor"] == "TestCorp"
        assert rows[0]["values"]["trial_count"] == 5


class TestCountByCountry:
    def test_counts(self):
        rows, _ = _aggregate_count_by_country(STUDIES)
        assert rows[0]["values"]["country"] == "US"


class TestEnrollmentByPhase:
    def test_totals(self):
        rows, _ = _aggregate_enrollment_by_phase(STUDIES)
        totals = {r["values"]["phase"]: r["values"]["total_enrollment"] for r in rows}
        assert totals["PHASE1"] == 50
        assert totals["PHASE2"] == 300
        assert totals["PHASE3"] == 800


class TestEnrollmentByYear:
    def test_totals(self):
        rows, _ = _aggregate_enrollment_by_year(STUDIES)
        totals = {r["values"]["year"]: r["values"]["total_enrollment"] for r in rows}
        assert totals[2020] == 150
        assert totals[2021] == 700


class TestSponsorDrugNetwork:
    def test_edges(self):
        rows, _ = _aggregate_sponsor_drug_network(STUDIES)
        assert len(rows) > 0
        first = rows[0]["values"]
        assert "sponsor" in first
        assert "drug" in first
        assert "weight" in first


class TestDrugCooccurrence:
    def test_multi_drug(self):
        studies = [
            _make_study(
                interventions=[
                    {"type": "DRUG", "name": "DrugA"},
                    {"type": "DRUG", "name": "DrugB"},
                ]
            ),
            _make_study(
                interventions=[
                    {"type": "DRUG", "name": "DrugA"},
                    {"type": "DRUG", "name": "DrugB"},
                    {"type": "DRUG", "name": "DrugC"},
                ]
            ),
        ]
        rows, _ = _aggregate_drug_cooccurrence(studies)
        edges = {
            (r["values"]["drug_a"], r["values"]["drug_b"]): r["values"]["weight"]
            for r in rows
        }
        assert edges[("DrugA", "DrugB")] == 2
        assert ("DrugA", "DrugC") in edges

    def test_single_drug_no_edges(self):
        studies = [_make_study()]
        rows, _ = _aggregate_drug_cooccurrence(studies)
        assert rows == []


class TestBuildEncoding:
    def test_known_aggregation(self):
        enc = _build_encoding("count_by_phase")
        assert enc.x is not None
        assert enc.x.field == "phase"

    def test_network_encoding(self):
        enc = _build_encoding("sponsor_drug_network")
        assert enc.source is not None
        assert enc.target is not None

    def test_unknown_aggregation(self):
        enc = _build_encoding("unknown_thing")
        assert enc.x is None


class TestResolveVizType:
    def test_valid(self):
        assert _resolve_viz_type("bar_chart") == VisualizationType.BAR_CHART
        assert _resolve_viz_type("network_graph") == VisualizationType.NETWORK_GRAPH

    def test_invalid_falls_back(self):
        assert _resolve_viz_type("invalid") == VisualizationType.BAR_CHART


class TestUnwrapLlmJson:
    """Gemini sometimes nests its output in an extra wrapper key."""

    FLAT = (
        '{"aggregation": "count_by_phase",'
        ' "visualization_type": "bar_chart",'
        ' "chart_title": "T", "query_interpretation": "Q"}'
    )
    WRAPPED = (
        '{"query_plan": {"aggregation": "count_by_phase",'
        ' "visualization_type": "bar_chart",'
        ' "chart_title": "T", "query_interpretation": "Q"}}'
    )

    def test_flat_passthrough(self):
        result = _unwrap_llm_json(self.FLAT)
        assert result["aggregation"] == "count_by_phase"

    def test_wrapped_unwrapped(self):
        result = _unwrap_llm_json(self.WRAPPED)
        assert result["aggregation"] == "count_by_phase"
        assert "query_plan" not in result

    def test_deeply_nested_single_key(self):
        raw = (
            '{"plan": {"aggregation": "count_by_year",'
            ' "visualization_type": "time_series",'
            ' "chart_title": "X", "query_interpretation": "Y"}}'
        )
        result = _unwrap_llm_json(raw)
        assert result["aggregation"] == "count_by_year"

    def test_multi_key_not_unwrapped(self):
        raw = '{"a": 1, "b": 2}'
        result = _unwrap_llm_json(raw)
        assert result == {"a": 1, "b": 2}
