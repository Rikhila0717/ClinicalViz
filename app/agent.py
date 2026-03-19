"""
AI Agent: Query-to-Visualization pipeline.

Architecture — three-stage ReAct-style agent
=============================================
1. **Plan** — LLM interprets the user's natural-language question, extracts
   structured API parameters, and decides which visualization type fits best.
2. **Execute** — The planner's output drives deterministic code that calls the
   ClinicalTrials.gov API and aggregates the results.
3. **Assemble** — A second LLM call receives the raw aggregated data and
   produces the final visualization spec with proper title, encoding, and
   optional deep citations.

Why two LLM calls instead of one?
* The first call turns fuzzy language into *constrained JSON* — we validate
  it with Pydantic before any API call, eliminating hallucinated field names.
* Aggregation & counting happen in deterministic Python, so numbers are always
  correct (no LLM math).
* The second call only has to map already-correct data into a visualization
  schema — a much simpler task that is less prone to hallucination.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import settings
from app.ct_client import (
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
    search_studies,
)
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

logger = logging.getLogger(__name__)


# ── Stage 1: Query Planning ──────────────────────────────────────────────

class QueryPlan(BaseModel):
    """Structured output the planner LLM must produce."""

    query_term: str | None = Field(None, description="Free-text search term")
    condition: str | None = None
    intervention: str | None = None
    phase: str | None = None
    status: str | None = None
    sponsor_keyword: str | None = None
    aggregation: str = Field(
        description=(
            "How to aggregate the studies. One of: "
            "count_by_phase, count_by_year, count_by_status, "
            "count_by_condition, count_by_intervention, count_by_sponsor, "
            "count_by_country, enrollment_by_phase, enrollment_by_year, "
            "compare_drugs_by_phase, sponsor_drug_network, "
            "condition_drug_network, drug_cooccurrence_network"
        )
    )
    visualization_type: str = Field(
        description=(
            "One of: bar_chart, grouped_bar_chart, time_series, "
            "scatter_plot, pie_chart, histogram, network_graph"
        )
    )
    chart_title: str = Field(
        default="Clinical Trials", description="Human-readable chart title"
    )
    query_interpretation: str = Field(
        default="", description="One-sentence plain-English restatement of what the query means"
    )
    compare_items: list[str] = Field(
        default_factory=list,
        description="For comparison queries: list of items to compare (e.g. two drug names)",
    )

# Prompt engineering: we give the LLM an exhaustive list of aggregation modes
# and visualization types so it maps the user question to a *known* code path
# rather than hallucinating an arbitrary strategy.
PLANNER_SYSTEM_PROMPT = """\
You are a clinical-trials data analyst. Given a user's natural-language \
question (and optional structured filters), produce a FLAT JSON object with \
ALL of the following keys:

REQUIRED OUTPUT KEYS (you MUST include every one):
  - aggregation (string): one of the allowed values below
  - visualization_type (string): one of the allowed values below
  - chart_title (string): a human-readable title for the chart
  - query_interpretation (string): one-sentence plain-English restatement

OPTIONAL OUTPUT KEYS (include when relevant):
  - query_term (string): free-text search keywords
  - condition (string): disease/condition extracted from the question
  - intervention (string): drug/intervention extracted from the question
  - phase (string): trial phase filter
  - status (string): trial status filter
  - sponsor_keyword (string): sponsor name filter
  - compare_items (list of strings): for comparison queries (e.g. two drug names)

RULES:
1. Pick the aggregation and visualization_type that BEST answers the question.
2. Only use the aggregation values listed below — never invent new ones.
3. Extract drug/condition/phase/status from the question when present.
4. For comparison queries (e.g. "Drug A vs Drug B"), set compare_items AND \
use compare_drugs_by_phase + grouped_bar_chart.
5. For relationship/network queries (sponsors-drugs, drug co-occurrence), \
use the appropriate network aggregation + visualization_type = "network_graph".
6. If the user asks for trends over time, use count_by_year + time_series.

Allowed aggregation values:
  count_by_phase, count_by_year, count_by_status,
  count_by_condition, count_by_intervention, count_by_sponsor,
  count_by_country, enrollment_by_phase, enrollment_by_year,
  compare_drugs_by_phase, sponsor_drug_network,
  condition_drug_network, drug_cooccurrence_network

Allowed visualization_type values:
  bar_chart, grouped_bar_chart, time_series, scatter_plot,
  pie_chart, histogram, network_graph

Respond with ONLY a flat JSON object. No nesting, no markdown fences, no wrapper keys.\
"""


def _build_planner_user_message(req: QueryRequest) -> str:
    parts = [f"Question: {req.query}"]
    if req.drug_name:
        parts.append(f"Drug filter: {req.drug_name}")
    if req.condition:
        parts.append(f"Condition filter: {req.condition}")
    if req.trial_phase:
        parts.append(f"Phase filter: {req.trial_phase}")
    if req.sponsor:
        parts.append(f"Sponsor filter: {req.sponsor}")
    if req.country:
        parts.append(f"Country filter: {req.country}")
    if req.start_year:
        parts.append(f"Start year ≥ {req.start_year}")
    if req.end_year:
        parts.append(f"End year ≤ {req.end_year}")
    if req.status:
        parts.append(f"Status filter: {req.status}")
    return "\n".join(parts)


def _unwrap_llm_json(raw: str) -> dict:
    """
    Gemini sometimes wraps its output in an extra key like
    {"query_plan": {…}} instead of returning the flat object.
    Detect that and unwrap so Pydantic always sees the right shape.
    """
    data = json.loads(raw)
    if not isinstance(data, dict):
        return data

    plan_fields = {"aggregation", "visualization_type", "chart_title"}
    if plan_fields & data.keys():
        return data

    # Wrapped in a single top-level key — unwrap one level
    if len(data) == 1:
        inner = next(iter(data.values()))
        if isinstance(inner, dict):
            return inner

    return data


async def _plan_query(req: QueryRequest) -> QueryPlan:
    """Stage 1: LLM interprets the user question into a QueryPlan."""
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = await client.aio.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=_build_planner_user_message(req),
        config=types.GenerateContentConfig(
            system_instruction=PLANNER_SYSTEM_PROMPT,
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    raw = response.text or "{}"
    logger.info("Planner raw output: %s", raw)
    parsed = _unwrap_llm_json(raw)
    return QueryPlan.model_validate(parsed)


# ── Stage 2: Deterministic data fetching + aggregation ───────────────────

def _year_from_date(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        return int(date_str[:4])
    except (ValueError, IndexError):
        return None


def _aggregate_count_by_phase(studies: list[dict]) -> tuple[list[dict], str]:
    counter: Counter[str] = Counter()
    citations_map: dict[str, list[Citation]] = defaultdict(list)
    for s in studies:
        phases = extract_phases(s) or ["Not specified"]
        for p in phases:
            counter[p] += 1
            citations_map[p].append(
                Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
            )
    data = [
        DataPoint(
            values={"phase": phase, "trial_count": count},
            citations=citations_map[phase][:5],
        )
        for phase, count in counter.most_common()
    ]
    return [d.model_dump() for d in data], "phase"


def _aggregate_count_by_year(
    studies: list[dict], start_year: int | None = None, end_year: int | None = None
) -> tuple[list[dict], str]:
    counter: Counter[int] = Counter()
    citations_map: dict[int, list[Citation]] = defaultdict(list)
    for s in studies:
        y = _year_from_date(extract_start_date(s))
        if y is None:
            continue
        if start_year and y < start_year:
            continue
        if end_year and y > end_year:
            continue
        counter[y] += 1
        citations_map[y].append(
            Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
        )
    data = [
        DataPoint(
            values={"year": year, "trial_count": count},
            citations=citations_map[year][:5],
        )
        for year, count in sorted(counter.items())
    ]
    return [d.model_dump() for d in data], "year"


def _aggregate_count_by_status(studies: list[dict]) -> tuple[list[dict], str]:
    counter: Counter[str] = Counter()
    citations_map: dict[str, list[Citation]] = defaultdict(list)
    for s in studies:
        status = extract_overall_status(s) or "Unknown"
        counter[status] += 1
        citations_map[status].append(
            Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
        )
    data = [
        DataPoint(
            values={"status": status, "trial_count": count},
            citations=citations_map[status][:5],
        )
        for status, count in counter.most_common()
    ]
    return [d.model_dump() for d in data], "status"


def _aggregate_count_by_condition(studies: list[dict]) -> tuple[list[dict], str]:
    counter: Counter[str] = Counter()
    citations_map: dict[str, list[Citation]] = defaultdict(list)
    for s in studies:
        for c in extract_conditions(s):
            counter[c] += 1
            citations_map[c].append(
                Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
            )
    top = counter.most_common(20)
    data = [
        DataPoint(
            values={"condition": cond, "trial_count": count},
            citations=citations_map[cond][:5],
        )
        for cond, count in top
    ]
    return [d.model_dump() for d in data], "condition"


def _aggregate_count_by_intervention(studies: list[dict]) -> tuple[list[dict], str]:
    counter: Counter[str] = Counter()
    citations_map: dict[str, list[Citation]] = defaultdict(list)
    for s in studies:
        for intr in extract_interventions(s):
            name = intr.get("name", "Unknown")
            counter[name] += 1
            citations_map[name].append(
                Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
            )
    top = counter.most_common(20)
    data = [
        DataPoint(
            values={"intervention": name, "trial_count": count},
            citations=citations_map[name][:5],
        )
        for name, count in top
    ]
    return [d.model_dump() for d in data], "intervention"


def _aggregate_count_by_sponsor(studies: list[dict]) -> tuple[list[dict], str]:
    counter: Counter[str] = Counter()
    citations_map: dict[str, list[Citation]] = defaultdict(list)
    for s in studies:
        sponsor = extract_sponsor(s) or "Unknown"
        counter[sponsor] += 1
        citations_map[sponsor].append(
            Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
        )
    top = counter.most_common(20)
    data = [
        DataPoint(
            values={"sponsor": sponsor, "trial_count": count},
            citations=citations_map[sponsor][:5],
        )
        for sponsor, count in top
    ]
    return [d.model_dump() for d in data], "sponsor"


def _aggregate_count_by_country(studies: list[dict]) -> tuple[list[dict], str]:
    counter: Counter[str] = Counter()
    citations_map: dict[str, list[Citation]] = defaultdict(list)
    for s in studies:
        for loc in extract_locations(s):
            country = loc.get("country", "Unknown")
            counter[country] += 1
            citations_map[country].append(
                Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
            )
    top = counter.most_common(20)
    data = [
        DataPoint(
            values={"country": country, "trial_count": count},
            citations=citations_map[country][:5],
        )
        for country, count in top
    ]
    return [d.model_dump() for d in data], "country"


def _aggregate_enrollment_by_phase(studies: list[dict]) -> tuple[list[dict], str]:
    totals: dict[str, int] = defaultdict(int)
    citations_map: dict[str, list[Citation]] = defaultdict(list)
    for s in studies:
        enrollment = extract_enrollment(s)
        if enrollment is None:
            continue
        phases = extract_phases(s) or ["Not specified"]
        for p in phases:
            totals[p] += enrollment
            citations_map[p].append(
                Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
            )
    data = [
        DataPoint(
            values={"phase": phase, "total_enrollment": total},
            citations=citations_map[phase][:5],
        )
        for phase, total in sorted(totals.items())
    ]
    return [d.model_dump() for d in data], "phase"


def _aggregate_enrollment_by_year(studies: list[dict]) -> tuple[list[dict], str]:
    totals: dict[int, int] = defaultdict(int)
    citations_map: dict[int, list[Citation]] = defaultdict(list)
    for s in studies:
        enrollment = extract_enrollment(s)
        y = _year_from_date(extract_start_date(s))
        if enrollment is None or y is None:
            continue
        totals[y] += enrollment
        citations_map[y].append(
            Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
        )
    data = [
        DataPoint(
            values={"year": year, "total_enrollment": total},
            citations=citations_map[year][:5],
        )
        for year, total in sorted(totals.items())
    ]
    return [d.model_dump() for d in data], "year"


async def _aggregate_compare_drugs(
    plan: QueryPlan, req: QueryRequest
) -> tuple[list[dict], str]:
    """Fetch studies for each drug separately and build grouped data."""
    items = plan.compare_items or []
    if len(items) < 2:
        items = [plan.intervention or req.drug_name or "Drug A", "Drug B"]

    all_data: list[dict] = []
    for drug in items:
        studies = await search_studies(
            intervention=drug,
            condition=plan.condition or req.condition,
        )
        counter: Counter[str] = Counter()
        citations_map: dict[str, list[Citation]] = defaultdict(list)
        for s in studies:
            for p in extract_phases(s) or ["Not specified"]:
                counter[p] += 1
                citations_map[p].append(
                    Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
                )
        for phase, count in counter.most_common():
            all_data.append(
                DataPoint(
                    values={"drug": drug, "phase": phase, "trial_count": count},
                    citations=citations_map[phase][:3],
                ).model_dump()
            )
    return all_data, "drug"


def _build_network_data(
    studies: list[dict], source_extractor, target_extractor, source_key: str, target_key: str
) -> list[dict]:
    """Generic network builder: count co-occurrences between two entity types."""
    edge_counter: Counter[tuple[str, str]] = Counter()
    edge_citations: dict[tuple[str, str], list[Citation]] = defaultdict(list)

    for s in studies:
        sources = source_extractor(s)
        targets = target_extractor(s)
        if isinstance(sources, str):
            sources = [sources]
        if isinstance(targets, str):
            targets = [targets]
        sources = [x for x in sources if x]
        targets = [x for x in targets if x]
        for src in sources:
            for tgt in targets:
                edge_counter[(src, tgt)] += 1
                edge_citations[(src, tgt)].append(
                    Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
                )

    top_edges = edge_counter.most_common(50)
    return [
        DataPoint(
            values={source_key: src, target_key: tgt, "weight": w},
            citations=edge_citations[(src, tgt)][:3],
        ).model_dump()
        for (src, tgt), w in top_edges
    ]


def _aggregate_sponsor_drug_network(studies: list[dict]) -> tuple[list[dict], str]:
    def _sponsor(s: dict) -> list[str]:
        name = extract_sponsor(s)
        return [name] if name else []

    def _drugs(s: dict) -> list[str]:
        return [i.get("name", "") for i in extract_interventions(s)]

    data = _build_network_data(studies, _sponsor, _drugs, "sponsor", "drug")
    return data, "sponsor"


def _aggregate_condition_drug_network(studies: list[dict]) -> tuple[list[dict], str]:
    def _drugs(s: dict) -> list[str]:
        return [i.get("name", "") for i in extract_interventions(s)]

    data = _build_network_data(studies, extract_conditions, _drugs, "condition", "drug")
    return data, "condition"


def _aggregate_drug_cooccurrence(studies: list[dict]) -> tuple[list[dict], str]:
    """Build a drug↔drug co-occurrence network from multi-intervention trials."""
    edge_counter: Counter[tuple[str, str]] = Counter()
    edge_citations: dict[tuple[str, str], list[Citation]] = defaultdict(list)

    for s in studies:
        drugs = [i.get("name", "") for i in extract_interventions(s) if i.get("name")]
        drugs = sorted(set(drugs))
        for i, d1 in enumerate(drugs):
            for d2 in drugs[i + 1:]:
                edge_counter[(d1, d2)] += 1
                edge_citations[(d1, d2)].append(
                    Citation(nct_id=extract_nct_id(s), excerpt=extract_brief_title(s))
                )

    top = edge_counter.most_common(50)
    data = [
        DataPoint(
            values={"drug_a": a, "drug_b": b, "weight": w},
            citations=edge_citations[(a, b)][:3],
        ).model_dump()
        for (a, b), w in top
    ]
    return data, "drug_a"


AGGREGATORS = {
    "count_by_phase": lambda studies, plan, req: (_aggregate_count_by_phase(studies)),
    "count_by_year": lambda studies, plan, req: (
        _aggregate_count_by_year(studies, req.start_year, req.end_year)
    ),
    "count_by_status": lambda studies, plan, req: (_aggregate_count_by_status(studies)),
    "count_by_condition": lambda studies, plan, req: (_aggregate_count_by_condition(studies)),
    "count_by_intervention": lambda studies, plan, req: (_aggregate_count_by_intervention(studies)),
    "count_by_sponsor": lambda studies, plan, req: (_aggregate_count_by_sponsor(studies)),
    "count_by_country": lambda studies, plan, req: (_aggregate_count_by_country(studies)),
    "enrollment_by_phase": lambda studies, plan, req: (_aggregate_enrollment_by_phase(studies)),
    "enrollment_by_year": lambda studies, plan, req: (_aggregate_enrollment_by_year(studies)),
}

# Network and comparison aggregators are handled separately (they may need extra API calls)

# ── Stage 3: Build final visualization spec ──────────────────────────────

ENCODING_MAP: dict[str, dict] = {
    "count_by_phase": {"x": ("phase", "nominal"), "y": ("trial_count", "quantitative")},
    "count_by_year": {"x": ("year", "temporal"), "y": ("trial_count", "quantitative")},
    "count_by_status": {"x": ("status", "nominal"), "y": ("trial_count", "quantitative")},
    "count_by_condition": {"x": ("condition", "nominal"), "y": ("trial_count", "quantitative")},
    "count_by_intervention": {
        "x": ("intervention", "nominal"), "y": ("trial_count", "quantitative"),
    },
    "count_by_sponsor": {"x": ("sponsor", "nominal"), "y": ("trial_count", "quantitative")},
    "count_by_country": {"x": ("country", "nominal"), "y": ("trial_count", "quantitative")},
    "enrollment_by_phase": {"x": ("phase", "nominal"), "y": ("total_enrollment", "quantitative")},
    "enrollment_by_year": {"x": ("year", "temporal"), "y": ("total_enrollment", "quantitative")},
    "compare_drugs_by_phase": {
        "x": ("phase", "nominal"),
        "y": ("trial_count", "quantitative"),
        "color": ("drug", "nominal"),
    },
    "sponsor_drug_network": {
        "source": ("sponsor", "nominal"),
        "target": ("drug", "nominal"),
        "weight": ("weight", "quantitative"),
    },
    "condition_drug_network": {
        "source": ("condition", "nominal"),
        "target": ("drug", "nominal"),
        "weight": ("weight", "quantitative"),
    },
    "drug_cooccurrence_network": {
        "source": ("drug_a", "nominal"),
        "target": ("drug_b", "nominal"),
        "weight": ("weight", "quantitative"),
    },
}


def _build_encoding(aggregation: str) -> Encoding:
    mapping = ENCODING_MAP.get(aggregation, {})
    kwargs: dict[str, FieldEncoding] = {}
    for channel, (field, ftype) in mapping.items():
        kwargs[channel] = FieldEncoding(field=field, type=ftype)
    return Encoding(**kwargs)


def _resolve_viz_type(name: str) -> VisualizationType:
    try:
        return VisualizationType(name)
    except ValueError:
        return VisualizationType.BAR_CHART


# ── Public entry point ───────────────────────────────────────────────────

async def process_query(req: QueryRequest) -> QueryResponse:
    """Full pipeline: Plan → Execute → Assemble."""

    # Stage 1 — Plan
    plan = await _plan_query(req)
    logger.info("Query plan: %s", plan.model_dump_json(indent=2))

    # Stage 2 — Execute
    aggregation = plan.aggregation

    if aggregation == "compare_drugs_by_phase":
        data_rows, _ = await _aggregate_compare_drugs(plan, req)
        total = sum(1 for _ in data_rows)
    elif aggregation in (
        "sponsor_drug_network", "condition_drug_network", "drug_cooccurrence_network",
    ):
        studies = await search_studies(
            query_term=plan.query_term,
            condition=plan.condition or req.condition,
            intervention=plan.intervention or req.drug_name,
            overall_status=plan.status or req.status,
            phase=plan.phase or req.trial_phase,
        )
        total = len(studies)
        if aggregation == "sponsor_drug_network":
            data_rows, _ = _aggregate_sponsor_drug_network(studies)
        elif aggregation == "condition_drug_network":
            data_rows, _ = _aggregate_condition_drug_network(studies)
        else:
            data_rows, _ = _aggregate_drug_cooccurrence(studies)
    else:
        studies = await search_studies(
            query_term=plan.query_term,
            condition=plan.condition or req.condition,
            intervention=plan.intervention or req.drug_name,
            overall_status=plan.status or req.status,
            phase=plan.phase or req.trial_phase,
        )
        total = len(studies)
        agg_fn = AGGREGATORS.get(aggregation)
        if agg_fn is None:
            # Fallback to count_by_phase if LLM picked an unknown aggregation
            logger.warning("Unknown aggregation '%s'; falling back to count_by_phase", aggregation)
            aggregation = "count_by_phase"
            agg_fn = AGGREGATORS["count_by_phase"]
        data_rows, _ = agg_fn(studies, plan, req)

    # Stage 3 — Assemble
    viz_type = _resolve_viz_type(plan.visualization_type)
    encoding = _build_encoding(aggregation)

    # Convert raw dicts back to DataPoint models
    data_points = []
    for row in data_rows:
        if isinstance(row, dict):
            dp = DataPoint(
                values=row.get("values", row),
                citations=[Citation(**c) for c in row.get("citations", [])],
            )
        else:
            dp = row
        data_points.append(dp)

    filters = {}
    if plan.condition or req.condition:
        filters["condition"] = plan.condition or req.condition
    if plan.intervention or req.drug_name:
        filters["drug_name"] = plan.intervention or req.drug_name
    if plan.phase or req.trial_phase:
        filters["phase"] = plan.phase or req.trial_phase
    if plan.status or req.status:
        filters["status"] = plan.status or req.status

    return QueryResponse(
        visualization=VisualizationSpec(
            type=viz_type,
            title=plan.chart_title,
            encoding=encoding,
            data=data_points,
        ),
        meta=ResponseMeta(
            filters_applied=filters,
            total_studies_analyzed=total,
            query_interpretation=plan.query_interpretation,
            assumptions=[
                f"Aggregation mode: {aggregation}",
                f"Page size: {settings.CT_API_PAGE_SIZE}, max pages: {settings.CT_API_MAX_PAGES}",
            ],
        ),
    )
