"""
Pydantic schemas for request validation and response serialization.

Design rationale:
- Request schema uses optional structured fields so the LLM agent can leverage
  them as hard constraints when building ClinicalTrials.gov API queries.
- Response schema mirrors a frontend-ready visualization spec (type, title,
  encoding, data) plus metadata and optional deep citations.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """Input accepted by the /query endpoint."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language question about clinical trials.",
        json_schema_extra={
            "examples": ["How has the number of trials for Pembrolizumab changed over time?"],
        },
    )
    drug_name: str | None = Field(
        None, description="Intervention / drug name to filter on."
    )
    condition: str | None = Field(
        None, description="Disease or condition to filter on."
    )
    trial_phase: str | None = Field(
        None,
        description="Phase filter (e.g. 'Phase 1', 'Phase 2', 'Phase 3').",
    )
    sponsor: str | None = Field(
        None, description="Lead sponsor organization."
    )
    country: str | None = Field(
        None, description="Country / location filter."
    )
    start_year: int | None = Field(
        None, ge=1900, le=2100, description="Earliest start year."
    )
    end_year: int | None = Field(
        None, ge=1900, le=2100, description="Latest start year."
    )
    status: str | None = Field(
        None,
        description="Overall study status (RECRUITING, COMPLETED, etc.).",
    )


# ---------------------------------------------------------------------------
# Visualization types
# ---------------------------------------------------------------------------

class VisualizationType(StrEnum):
    BAR_CHART = "bar_chart"
    GROUPED_BAR_CHART = "grouped_bar_chart"
    TIME_SERIES = "time_series"
    SCATTER_PLOT = "scatter_plot"
    PIE_CHART = "pie_chart"
    HISTOGRAM = "histogram"
    NETWORK_GRAPH = "network_graph"


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class FieldEncoding(BaseModel):
    field: str
    type: str | None = Field(None, description="nominal | quantitative | temporal")

class Encoding(BaseModel):
    """Maps visual channels to data fields (Vega-Lite inspired)."""
    model_config = {"json_schema_extra": {"description": "Only populated channels are included."}}

    x: FieldEncoding | None = None
    y: FieldEncoding | None = None
    color: FieldEncoding | None = None
    size: FieldEncoding | None = None
    source: FieldEncoding | None = None
    target: FieldEncoding | None = None
    weight: FieldEncoding | None = None
    label: FieldEncoding | None = None
    theta: FieldEncoding | None = None


class Citation(BaseModel):
    nct_id: str
    excerpt: str


class DataPoint(BaseModel):
    """
    A single row in the visualization dataset.
    Uses a flexible dict so it can represent any column set.
    """
    values: dict[str, Any]
    citations: list[Citation] = Field(default_factory=list)


class VisualizationSpec(BaseModel):
    type: VisualizationType
    title: str
    encoding: Encoding
    data: list[DataPoint]


class ResponseMeta(BaseModel):
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    source: str = "clinicaltrials.gov"
    total_studies_analyzed: int = 0
    query_interpretation: str = ""
    assumptions: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    visualization: VisualizationSpec
    meta: ResponseMeta
