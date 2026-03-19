"""Tests for the ClinicalTrials.gov API client layer."""

from app.ct_client import (
    _normalize_status,
    extract_brief_title,
    extract_conditions,
    extract_enrollment,
    extract_interventions,
    extract_locations,
    extract_nct_id,
    extract_overall_status,
    extract_phases,
    extract_sponsor,
    extract_start_date,
)

# Realistic fixture mimicking the ClinicalTrials.gov v2 API response shape
SAMPLE_STUDY = {
    "protocolSection": {
        "identificationModule": {
            "nctId": "NCT06000001",
            "briefTitle": "A Phase 3 Study of Pembrolizumab in NSCLC",
        },
        "statusModule": {
            "overallStatus": "RECRUITING",
            "startDateStruct": {"date": "2023-06-15"},
        },
        "designModule": {
            "phases": ["PHASE3"],
            "enrollmentInfo": {"count": 500, "type": "ESTIMATED"},
        },
        "conditionsModule": {
            "conditions": ["Non-Small Cell Lung Cancer", "Carcinoma"],
        },
        "armsInterventionsModule": {
            "interventions": [
                {"type": "DRUG", "name": "Pembrolizumab"},
                {"type": "DRUG", "name": "Placebo"},
            ],
        },
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": "Merck Sharp & Dohme LLC"},
        },
        "contactsLocationsModule": {
            "locations": [
                {"facility": "Site 1", "country": "United States", "city": "Boston"},
                {"facility": "Site 2", "country": "Germany", "city": "Berlin"},
            ],
        },
    }
}

EMPTY_STUDY: dict = {}


class TestExtractors:
    def test_nct_id(self):
        assert extract_nct_id(SAMPLE_STUDY) == "NCT06000001"
        assert extract_nct_id(EMPTY_STUDY) == ""

    def test_brief_title(self):
        assert "Pembrolizumab" in extract_brief_title(SAMPLE_STUDY)
        assert extract_brief_title(EMPTY_STUDY) == ""

    def test_phases(self):
        assert extract_phases(SAMPLE_STUDY) == ["PHASE3"]
        assert extract_phases(EMPTY_STUDY) == []

    def test_start_date(self):
        assert extract_start_date(SAMPLE_STUDY) == "2023-06-15"
        assert extract_start_date(EMPTY_STUDY) is None

    def test_overall_status(self):
        assert extract_overall_status(SAMPLE_STUDY) == "RECRUITING"
        assert extract_overall_status(EMPTY_STUDY) == ""

    def test_conditions(self):
        conds = extract_conditions(SAMPLE_STUDY)
        assert "Non-Small Cell Lung Cancer" in conds
        assert extract_conditions(EMPTY_STUDY) == []

    def test_interventions(self):
        intrs = extract_interventions(SAMPLE_STUDY)
        assert len(intrs) == 2
        assert intrs[0]["name"] == "Pembrolizumab"
        assert extract_interventions(EMPTY_STUDY) == []

    def test_sponsor(self):
        assert "Merck" in extract_sponsor(SAMPLE_STUDY)
        assert extract_sponsor(EMPTY_STUDY) == ""

    def test_locations(self):
        locs = extract_locations(SAMPLE_STUDY)
        assert len(locs) == 2
        assert locs[0]["country"] == "United States"
        assert extract_locations(EMPTY_STUDY) == []

    def test_enrollment(self):
        assert extract_enrollment(SAMPLE_STUDY) == 500
        assert extract_enrollment(EMPTY_STUDY) is None


class TestNormalizeStatus:
    def test_valid_passthrough(self):
        assert _normalize_status("RECRUITING") == "RECRUITING"
        assert _normalize_status("COMPLETED") == "COMPLETED"

    def test_comma_separated_valid(self):
        assert _normalize_status("RECRUITING,COMPLETED") == "RECRUITING,COMPLETED"

    def test_alias_active(self):
        result = _normalize_status("active")
        assert "RECRUITING" in result
        assert "ACTIVE_NOT_RECRUITING" in result

    def test_alias_ongoing(self):
        result = _normalize_status("ongoing")
        assert "RECRUITING" in result

    def test_alias_closed(self):
        result = _normalize_status("closed")
        assert "COMPLETED" in result

    def test_none_input(self):
        assert _normalize_status(None) is None

    def test_empty_string(self):
        assert _normalize_status("") is None

    def test_garbage_dropped(self):
        assert _normalize_status("nonsense_value") is None
