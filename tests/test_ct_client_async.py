"""Tests for the async HTTP layer of ct_client (mocked network)."""

from unittest.mock import MagicMock, patch

import pytest

from app.ct_client import _rate_limited_get, _sync_get, search_studies

FAKE_STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT001", "briefTitle": "Test"},
        "statusModule": {"overallStatus": "RECRUITING"},
        "designModule": {"phases": ["PHASE2"]},
        "conditionsModule": {"conditions": ["Diabetes"]},
        "armsInterventionsModule": {"interventions": []},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Corp"}},
        "contactsLocationsModule": {"locations": []},
    }
}


class TestSyncGet:
    @patch("app.ct_client._session")
    def test_success(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"studies": [FAKE_STUDY]}
        mock_resp.raise_for_status.return_value = None
        mock_session.get.return_value = mock_resp

        result = _sync_get("https://example.com", {"pageSize": 1})
        assert result["studies"][0] == FAKE_STUDY

    @patch("app.ct_client._session")
    def test_http_error_propagates(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("403 Forbidden")
        mock_session.get.return_value = mock_resp

        with pytest.raises(Exception, match="403"):
            _sync_get("https://example.com", {})


class TestRateLimitedGet:
    @pytest.mark.asyncio
    @patch("app.ct_client._sync_get")
    async def test_returns_result(self, mock_get):
        mock_get.return_value = {"studies": []}
        result = await _rate_limited_get("https://example.com", {})
        assert result == {"studies": []}


class TestSearchStudies:
    @pytest.mark.asyncio
    @patch("app.ct_client._rate_limited_get")
    async def test_basic_search(self, mock_get):
        mock_get.return_value = {"studies": [FAKE_STUDY], "nextPageToken": None}
        studies = await search_studies(condition="Diabetes", page_size=10, max_pages=1)
        assert len(studies) == 1
        assert studies[0] == FAKE_STUDY

    @pytest.mark.asyncio
    @patch("app.ct_client._rate_limited_get")
    async def test_pagination(self, mock_get):
        mock_get.side_effect = [
            {"studies": [FAKE_STUDY], "nextPageToken": "page2"},
            {"studies": [FAKE_STUDY], "nextPageToken": None},
        ]
        studies = await search_studies(condition="Diabetes", page_size=1, max_pages=3)
        assert len(studies) == 2
        assert mock_get.call_count == 2

    @pytest.mark.asyncio
    @patch("app.ct_client._rate_limited_get")
    async def test_stops_on_empty_page(self, mock_get):
        mock_get.side_effect = [
            {"studies": [FAKE_STUDY], "nextPageToken": "page2"},
            {"studies": [], "nextPageToken": "page3"},
        ]
        studies = await search_studies(page_size=1, max_pages=5)
        assert len(studies) == 1

    @pytest.mark.asyncio
    @patch("app.ct_client._rate_limited_get")
    async def test_all_params_forwarded(self, mock_get):
        mock_get.return_value = {"studies": [], "nextPageToken": None}
        await search_studies(
            query_term="cancer",
            condition="Lung",
            intervention="Drug",
            overall_status="RECRUITING",
            phase="PHASE3",
            page_size=5,
            max_pages=1,
        )
        call_params = mock_get.call_args[0][1]
        assert call_params["query.term"] == "cancer"
        assert call_params["query.cond"] == "Lung"
        assert call_params["query.intr"] == "Drug"
        assert call_params["filter.overallStatus"] == "RECRUITING"
        assert call_params["filter.phase"] == "PHASE3"

    @pytest.mark.asyncio
    @patch("app.ct_client._rate_limited_get")
    async def test_status_normalized(self, mock_get):
        """LLM sends 'active', should be normalized before API call."""
        mock_get.return_value = {"studies": [], "nextPageToken": None}
        await search_studies(overall_status="active", page_size=5, max_pages=1)
        call_params = mock_get.call_args[0][1]
        assert "RECRUITING" in call_params["filter.overallStatus"]

    @pytest.mark.asyncio
    @patch("app.ct_client._rate_limited_get")
    async def test_invalid_status_dropped(self, mock_get):
        mock_get.return_value = {"studies": [], "nextPageToken": None}
        await search_studies(overall_status="nonsense", page_size=5, max_pages=1)
        call_params = mock_get.call_args[0][1]
        assert "filter.overallStatus" not in call_params
