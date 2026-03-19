# CLINICALVIZ: ClinicalTrials.gov Query-to-Visualization Agent

An AI-powered backend that converts natural-language clinical-trial questions into **structured visualization specifications**, backed by live data from the [ClinicalTrials.gov API (v2)](https://clinicaltrials.gov/data-api/api).

---

## Quick Start - Guide to installation, configuration from GitHub/docker

### 1. Prerequisites

- Python 3.11+
- A Google AI Studio API key (get one free at [aistudio.google.com](https://aistudio.google.com/) — `gemini-2.5-flash` is the default model)

### 2. Install

```bash
git clone https://github.com/Rikhila0717/ClinicalViz && cd ClinicalTrialsAgent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env and set your GEMINI_API_KEY
```

### 4. Run

```bash
uvicorn app.main:app --reload
# Server starts at http://localhost:8000
```

### 5. Try it

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How are Diabetes trials distributed across phases?", "condition": "Diabetes"}'
```

### Docker

**Option A — Pull the pre-built image from Docker Hub:**

```bash
docker pull rikhila07/clinical-trials-agent:latest
docker run -e GEMINI_API_KEY=your-key -p 8000:8000 rikhila07/clinical-trials-agent:latest
```

**Option B — Build locally:**

```bash
docker build -t clinical-trials-agent .
docker run -e GEMINI_API_KEY=your-key -p 8000:8000 clinical-trials-agent
```

Then open:
- **http://localhost:8000** — Interactive HTML-based UI
- **http://localhost:8000/docs** — Swagger API docs


### 6. Run tests

```bash
# Unit tests (fast, no network)
pytest tests/ -m "not integration" -v

# Integration tests (hits ClinicalTrials.gov API)
pytest tests/ -m integration -v

# With coverage
pytest tests/ -m "not integration" --cov=app --cov-report=term-missing
```

---

## Request Schema

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | **Yes** | Natural-language question about clinical trials |
| `drug_name` | string | No | Intervention / drug filter |
| `condition` | string | No | Disease or condition filter |
| `trial_phase` | string | No | Phase filter (e.g. "Phase 1") |
| `sponsor` | string | No | Lead sponsor organization |
| `country` | string | No | Country / location filter |
| `start_year` | int | No | Earliest start year (≥ 1900) |
| `end_year` | int | No | Latest start year (≤ 2100) |
| `status` | string | No | Study status (RECRUITING, COMPLETED, etc.) |

**Example request:**
```json
{
  "query": "How has the number of trials for Pembrolizumab changed per year since 2015?",
  "drug_name": "Pembrolizumab",
  "start_year": 2015
}
```

---

## Response Schema

```json
{
  "visualization": {
    "type": "bar_chart | grouped_bar_chart | time_series | scatter_plot | pie_chart | histogram | network_graph",
    "title": "Human-readable chart title",
    "encoding": {
      "x": {"field": "phase", "type": "nominal"},
      "y": {"field": "trial_count", "type": "quantitative"},
      "color": {"field": "...", "type": "..."},
      "source": {"field": "...", "type": "..."},
      "target": {"field": "...", "type": "..."},
      "weight": {"field": "...", "type": "..."}
    },
    "data": [
      {
        "values": {"phase": "Phase 1", "trial_count": 32},
        "citations": [
          {"nct_id": "NCT06000001", "excerpt": "A Phase 1 study of..."}
        ]
      }
    ]
  },
  "meta": {
    "filters_applied": {"drug_name": "Pembrolizumab"},
    "source": "clinicaltrials.gov",
    "total_studies_analyzed": 250,
    "query_interpretation": "Count Pembrolizumab trials grouped by year, starting from 2015",
    "assumptions": ["Aggregation mode: count_by_year", "Page size: 50, max pages: 5"]
  }
}
```

### Encoding channels

- **Standard charts** (bar, time_series, scatter, pie, histogram): `x`, `y`, `color`, `theta`
- **Network graphs**: `source`, `target`, `weight`, `label`
- **Grouped bar charts**: `x`, `y`, `color` (color = the grouping variable)

This backend can easily be rendered using Vega-Lite, D3, Chart.js, or any charting library by mapping `encoding` fields directly to chart channels. My design is inspired by Vega-Lite (https://vega.github.io/vega-lite/), which provides simple, declarative JSON syntax to generate a wide range of visualizations.

---

## Supported Visualization Types

| Type | Use Case |
|---|---|
| `bar_chart` | Distributions (by phase, status, sponsor, condition) |
| `grouped_bar_chart` | Comparisons (Drug A vs Drug B by phase) |
| `time_series` | Trends over time (trial counts or enrollment by year) |
| `scatter_plot` | Enrollment vs. other metrics |
| `pie_chart` | Proportional breakdowns |
| `histogram` | Frequency distributions |
| `network_graph` | Relationships (sponsor↔drug, drug↔drug co-occurrence, condition↔drug) |

---

## Supported Query Types

| Category | Example Query | Aggregation | Viz Type |
|---|---|---|---|
| **Time trends** | "How has the number of trials for Pembrolizumab changed per year?" | `count_by_year` | `time_series` |
| **Distributions** | "How are Diabetes trials distributed across phases?" | `count_by_phase` | `bar_chart` |
| **Status** | "What is the status breakdown for COVID-19 trials?" | `count_by_status` | `bar_chart` |
| **Interventions** | "What are the most common interventions for Lung Cancer?" | `count_by_intervention` | `bar_chart` |
| **Sponsors** | "Which sponsors run the most Breast Cancer trials?" | `count_by_sponsor` | `bar_chart` |
| **Geographic** | "Which countries have the most recruiting trials for Alzheimer's?" | `count_by_country` | `bar_chart` |
| **Enrollment** | "How does enrollment vary by phase for Metformin trials?" | `enrollment_by_phase` | `bar_chart` |
| **Comparisons** | "Compare phases for Aspirin vs Ibuprofen trials" | `compare_drugs_by_phase` | `grouped_bar_chart` |
| **Sponsor network** | "Show sponsors and drugs for Breast Cancer" | `sponsor_drug_network` | `network_graph` |
| **Drug network** | "Which drugs co-occur in combination studies for Melanoma?" | `drug_cooccurrence_network` | `network_graph` |
| **Condition network** | "Show the relationship between conditions and drugs for oncology trials" | `condition_drug_network` | `network_graph` |

---

## Architecture & Key Design Decisions

### Three-Stage Agent Pipeline

```

│  1. PLAN    │────▶│  2. EXECUTE    │────▶│  3. VISUALIZE    │
│  (LLM call) │     │ (Deterministic │     │  (Build visual)  │
│             │     │   Python)      │     │                  │

```

1. **Plan (LLM)** — The LLM interprets the user's natural-language question and produces a structured `QueryPlan` JSON: which API parameters to use, which aggregation strategy to apply, and which visualization type fits best. The planner uses constrained JSON output (Gemini JSON mode via `response_mime_type`) and the result is validated with Pydantic before further use.

2. **Execute (Deterministic Python)** — Since this is a relatively simple task, I am not involving any LLM math. Aggregation, counting, and grouping are done entirely in Python using `collections.Counter` and `defaultdict`. This ensures correctness — the LLM never invents numbers, making this a neat anti-hallucination strategy.

3. **Visualize (Schema builder)** — Maps aggregated data into a frontend-ready `VisualizationSpec` with encoding, data points, and metadata. Deep citations (NCT IDs + text excerpts) are attached at the data-point level.

### Why this design?

| Decision | Rationale |
|---|---|
| **Two narrow LLM calls instead of one big one** | Instead of flooding one gigantic prompt through the LLM, the planner maps language → structured query (simple, low hallucination risk). Aggregation calculations are in Python (zero hallucination risk). This avoids the classic failure mode where an LLM can invent plausible-but-wrong counts. |
| **Constrained output (JSON mode + Pydantic validation)** | The LLM must produce valid JSON matching the `QueryPlan` schema. If it doesn't, Pydantic raises the error before any API call happens - a fail-fast mechanism. |
| **Whitelisting possible aggregations** | The planner prompt lists every allowed aggregation value. The LLM picks from this list rather than inventing strategies. Unknown values fall back to `count_by_phase`. This ensures the LLM does not create new aggregation values which might result in unexpected outputs. |
| **Thin API client, no ORM** | The CT.gov API returns deeply nested JSON. I used simple dict accessors with `.get()` — any missing field returns `""` or `[]`, never crashes. |
| **Rate-limited async client** | ClinicalTrials.gov enforces 3 req/s. I used an `asyncio.Semaphore` + sleep combination to stay under the limit without blocking the loop. |
| **Auto-pagination** | Many queries return hundreds of studies. The client follows `nextPageToken` up to a configurable max (default 5 pages × 50 = 250 studies), balancing completeness vs. latency. |
| **Deep citations at the data-point level** | Each aggregated bucket (e.g. "Phase 3: 41 trials") carries up to 5 citations with the NCT ID and brief title, so every number is traceable to source records. |

### Anti-hallucination measures

- The LLM **never produces data values**. It only selects which *code path* to run.
- All counts, sums, and groupings happen in tested Python functions.
- Unknown aggregation types fall back gracefully, without any runtime issues.
- Additional validation barrier - Pydantic validates both the LLM output and the final response.

---

## Project Structure

```
ClinicalTrialsAgent/
├── app/
│   ├── __init__.py
│   ├── config.py          # Environment-based settings (12-factor)
│   ├── schemas.py         # Pydantic request/response models
│   ├── ct_client.py       # Async ClinicalTrials.gov API client
│   ├── agent.py           # AI agent (plan → execute → visualize)
│   └── main.py            # FastAPI application
├── tests/
│   ├── test_schemas.py    # Schema validation tests
│   ├── test_ct_client.py  # Field extractor tests
│   ├── test_agent.py      # Aggregation logic tests
│   ├── test_api.py        # Endpoint tests (mocked agent)
│   └── test_integration.py# Live API integration tests
├── examples.py            # Generate example query/response pairs
├── .github/workflows/ci.yml  # CI pipeline
├── Dockerfile
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

---

## Testing Strategy

| Layer | What's tested | Count | Requires network? |
|---|---|---|---|
| `test_schemas.py` | Request validation, response serialization, round-trip | 9 | No |
| `test_ct_client.py` | Field extractors against realistic fixtures | 10 | No |
| `test_agent.py` | All 13 aggregation functions, encoding builder, viz type resolver | 24 | No |
| `test_api.py` | FastAPI endpoint behavior (mocked agent) | 7 | No |
| `test_integration.py` | Live API fetching + aggregation on real data | 3 | Yes |
| **Total** | | **53** | |

Unit tests run in <1 second. Integration tests are gated behind `pytest -m integration`.

---

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`):
- Runs on push/PR to `main`
- Matrix: Python 3.11
- Steps: lint (ruff) → unit tests with coverage → integration tests (main branch only) -> sonarcloud scan -> docker build and push 

---

## Example Runs

Run `python examples.py` with your API key set to generate live examples, or execute them from swagger endpoint. Below are five representative queries:

### Example 1: Time Trend

**Request:**
```json
{
  "query": "How has the number of trials for Pembrolizumab changed per year since 2015?",
  "drug_name": "Pembrolizumab",
  "start_year": 2015
}
```
**Response:**

```json
{
  "visualization": {
    "type": "time_series",
    "title": "Number of Trials for Pembrolizumab Per Year Since 2015",
    "encoding": {
      "x": {
        "field": "year",
        "type": "temporal"
      },
      "y": {
        "field": "trial_count",
        "type": "quantitative"
      }
    },
    "data": [
      {
        "values": {
          "year": 2015,
          "trial_count": 8
        },
        "citations": [
          {
            "nct_id": "NCT02452424",
            "excerpt": "A Combination Clinical Study of PLX3397 and Pembrolizumab To Treat Advanced Melanoma and Other Solid Tumors"
          },
          {
            "nct_id": "NCT02434354",
            "excerpt": "A Tissue Collection Study of Pembrolizumab (MK-3475) in Subjects With Resectable Advanced Melanoma"
          },
          {
            "nct_id": "NCT02446457",
            "excerpt": "Rituximab and Pembrolizumab With or Without Lenalidomide in Treating Patients With Relapsed Follicular Lymphoma and Diffuse Large B-Cell Lymphoma"
          },
          {
            "nct_id": "NCT02423863",
            "excerpt": "In Situ, Autologous Therapeutic Vaccination Against Solid Cancers With Intratumoral Hiltonol®"
          },
          {
            "nct_id": "NCT02298959",
            "excerpt": "Testing the PD-1 Antibody, MK3475, Given With Ziv-aflibercept in Patients With Advanced Cancer"
          }
        ]
      },
      {
        "values": {
          "year": 2016,
          "trial_count": 12
        },
        "citations": [
          {
            "nct_id": "NCT02919969",
            "excerpt": "Pembrolizumab in Metastatic Anal Cancer"
          },
          {
            "nct_id": "NCT02826486",
            "excerpt": "Study Assessing Safety and Efficacy of Combination of BL-8040 and Pembrolizumab in Metastatic Pancreatic Cancer Patients"
          },
          {
            "nct_id": "NCT02625337",
            "excerpt": "Study Comparing Pembrolizumab With Dual MAPK Pathway Inhibition Plus Pembrolizumab in Melanoma Patients"
          },
          {
            "nct_id": "NCT02939651",
            "excerpt": "A Study of Pembrolizumab in Patients With Neuroendocrine Tumors"
          },
          {
            "nct_id": "NCT02728830",
            "excerpt": "A Study of Pembrolizumab on the Tumoral Immunoprofile of Gynecologic Cancers"
          }
        ]
      },
      {
        "values": {
          "year": 2017,
          "trial_count": 26
        },
        "citations": [
          {
            "nct_id": "NCT03083808",
            "excerpt": "Phase II Trial of Continuation Therapy in Advanced NSCLC"
          },
          {
            "nct_id": "NCT03058289",
            "excerpt": "A Phase 1/2 Safety Study of Intratumorally Dosed INT230-6"
          },
          {
            "nct_id": "NCT03035890",
            "excerpt": "Hypofractionated Radiation Therapy to Improve Immunotherapy Response in Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT02875132",
            "excerpt": "Pembrolizumab in Advanced/Metastatic Acral Lentiginous Melanoma"
          },
          {
            "nct_id": "NCT03276832",
            "excerpt": "Imiquimod and Pembrolizumab in Treating Patients With Stage IIIB-IV Melanoma"
          }
        ]
      },
      {
        "values": {
          "year": 2018,
          "trial_count": 25
        },
        "citations": [
          {
            "nct_id": "NCT03633110",
            "excerpt": "Safety, Tolerability, Immunogenicity, and Antitumor Activity of GEN-009 Adjuvanted Vaccine"
          },
          {
            "nct_id": "NCT03666273",
            "excerpt": "Phase 1 Study of BAY1905254 - An Early Clinical Research Study to Evaluate a New Drug Called Bapotulimab (BAY1905254) in the Expansion Cohort in Combination With Pembrolizumab in Head and Neck Cancer That Has Returned or is Discovered to be Metastatic and is Expressing PDL1."
          },
          {
            "nct_id": "NCT03367754",
            "excerpt": "A Single Dose of Pembrolizumab in HIV-Infected People"
          },
          {
            "nct_id": "NCT05023837",
            "excerpt": "Efficacy and Safety of Immunotherapy in Non-small Cell Lung Cancer With Uncommon Histological Type"
          },
          {
            "nct_id": "NCT03382600",
            "excerpt": "Safety and Efficacy of Pembrolizumab (MK-3475) in Combination With TS-1+Cisplatin or TS-1+Oxaliplatin as First Line Chemotherapy in Gastric Cancer (MK-3475-659/KEYNOTE-659)"
          }
        ]
      },
      {
        "values": {
          "year": 2019,
          "trial_count": 23
        },
        "citations": [
          {
            "nct_id": "NCT03726515",
            "excerpt": "CART-EGFRvIII + Pembrolizumab in GBM"
          },
          {
            "nct_id": "NCT03586024",
            "excerpt": "Pembrolizumab in Relapsed or Refractory Extranodal NK/T- Cell Lymphoma, Nasal Type and EBV-associated Diffuse Large B Cell Lymphomas"
          },
          {
            "nct_id": "NCT03894540",
            "excerpt": "Dose Escalation and Dose Expansion Study of IPN60090 in Patients With Advanced Solid Tumours"
          },
          {
            "nct_id": "NCT03813394",
            "excerpt": "Bevacizumab and Pembrolizumab Combination in Platinum-resistant Recurrent/Metastatic NPC"
          },
          {
            "nct_id": "NCT03895970",
            "excerpt": "Lenvatinib Combined Pembrolizumab in Advanced Hepatobiliary Tumors"
          }
        ]
      },
      {
        "values": {
          "year": 2020,
          "trial_count": 25
        },
        "citations": [
          {
            "nct_id": "NCT04387461",
            "excerpt": "Study of CG0070 Given in Combination With Pembrolizumab, in Non-Muscle Invasive Bladder Cancer, Unresponsive to Bacillus Calmette-Guerin"
          },
          {
            "nct_id": "NCT06119347",
            "excerpt": "Acute Kidney Injury in Cancer Patients Receiving Anti-Vascular Endothelial Growth Factor Monoclonal Antibody vs Immune Checkpoint Inhibitors"
          },
          {
            "nct_id": "NCT06195254",
            "excerpt": "Stereotactic Body Radiotherapy Combined With PD-1 Blockers for Locally Advanced or Locally Recurrent Pancreatic Cancer"
          },
          {
            "nct_id": "NCT04265872",
            "excerpt": "Bortezomib Followed by Pembrolizumab and Cisplatin in metTNBC"
          },
          {
            "nct_id": "NCT04205227",
            "excerpt": "ENB003 Plus Pembrolizumab Phase 1b/2a in Solid Tumors"
          }
        ]
      },
      {
        "values": {
          "year": 2021,
          "trial_count": 27
        },
        "citations": [
          {
            "nct_id": "NCT04632459",
            "excerpt": "Pembrolizumab Plus Ramucirumab in Metastatic Gastric Cancer"
          },
          {
            "nct_id": "NCT04677361",
            "excerpt": "Feasibility Study on Expandion of MILs From NSCLC and SCLC Patients and Infusion With Pembrolizumab"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          },
          {
            "nct_id": "NCT04887870",
            "excerpt": "Study of Sitravatinib With or Without Other Anticancer Therapies Receiving Clinical Benefit From Parent Study"
          },
          {
            "nct_id": "NCT04997382",
            "excerpt": "Chemotherapy Combined with ICIs in First-line Alectinib Failed Patients with ALK-rearranged NSCLC"
          }
        ]
      },
      {
        "values": {
          "year": 2022,
          "trial_count": 29
        },
        "citations": [
          {
            "nct_id": "NCT04118868",
            "excerpt": "Pembrolizumab Administered Via the Sofusa® DoseConnect™ in Patients With Relapsed/Refractory Cutaneous T-cell Lymphoma."
          },
          {
            "nct_id": "NCT03492918",
            "excerpt": "Pembrolizumab in Combination With Paclitaxel in the Hormone Receptor-positive Metastatic Breast Cancer With High Tumor Mutational Burden Selected by Whole Exome Sequencing: Korean Cancer Study Group Trial (KCSG BR20-16)"
          },
          {
            "nct_id": "NCT06781450",
            "excerpt": "Study in Patients With Relapsed/Refractory Primary Mediastinal Lymphoma Treated With Pembrolizumab or Nivolumab in Combination With Brentuximab Vedotin in a Real-life Context"
          },
          {
            "nct_id": "NCT07192926",
            "excerpt": "Sarcopenia and CRP-TyG Index (CTI) as Predictors of Immunotherapy Response in Metastatic Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT05382559",
            "excerpt": "A Study of ASP3082 in Adults With Advanced Solid Tumors"
          }
        ]
      },
      {
        "values": {
          "year": 2023,
          "trial_count": 18
        },
        "citations": [
          {
            "nct_id": "NCT05349890",
            "excerpt": "Personalized TCR-T: Study of Adoptively Transferred T-cell Receptor Gene-engineered T Cells (TCR-T)"
          },
          {
            "nct_id": "NCT05568550",
            "excerpt": "Pembro With Radiation With or Without Olaparib"
          },
          {
            "nct_id": "NCT04616248",
            "excerpt": "In Situ Immunomodulation With CDX-301, Radiation Therapy, CDX-1140 and Poly-ICLC in Patients w/ Unresectable and Metastatic Solid Tumors"
          },
          {
            "nct_id": "NCT05558982",
            "excerpt": "BXCL701 and Pembrolizumab in Patients With Metastatic Pancreatic Ductal Adenocarcinoma"
          },
          {
            "nct_id": "NCT05784688",
            "excerpt": "Study of TU2218 in Combination With KEYTRUDA®(Pembrolizumab) in Patients With Advanced Solid Tumors"
          }
        ]
      },
      {
        "values": {
          "year": 2024,
          "trial_count": 23
        },
        "citations": [
          {
            "nct_id": "NCT07066917",
            "excerpt": "Mechanisms of Response and Resistance to Innovative Treatments in Patients With Locally Advanced or Metastatic Breast Cancer"
          },
          {
            "nct_id": "NCT06480552",
            "excerpt": "An Open-label Dose Escalation/Expansion Trial to Evaluate the Safety and Anti-tumor Activity of TEV-56278 Alone or in Combination With Pembrolizumab in Participants With Advanced or Metastatic Solid Tumors"
          },
          {
            "nct_id": "NCT04838652",
            "excerpt": "Pembrolizumab in Combination With Salvage Chemotherapy for First-relapsed or Refractory Classical Hodgkin Lymphoma"
          },
          {
            "nct_id": "NCT05846724",
            "excerpt": "Pembrolizumab Plus Lenvatinib in Previously Treated Classic Kaposi Sarcoma"
          },
          {
            "nct_id": "NCT07207928",
            "excerpt": "Evaluation of Clinical Outcomes, Tolerability, and Costs of Avelumab Maintenance and Pembrolizumab Second-Line Therapy in Advanced Urothelial Cancer."
          }
        ]
      },
      {
        "values": {
          "year": 2025,
          "trial_count": 26
        },
        "citations": [
          {
            "nct_id": "NCT06725368",
            "excerpt": "Carboplatin + Paclitaxel + Cetuximab (PCC) After Failure of Pembrolizumab +/- First-line Chemotherapy in Recurrent/Metastatic Squamous Cell Carcinoma of the Head and Neck"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06640283",
            "excerpt": "Dynamic ctDNA Assessment in Cervical and Anal Canal Tumors: Optimizing Follow-up and Clinical Outcomes"
          },
          {
            "nct_id": "NCT06901531",
            "excerpt": "A Study of Zolbetuximab Together With Pembrolizumab and Chemotherapy in Adults With Gastric Cancer"
          },
          {
            "nct_id": "NCT06888037",
            "excerpt": "Fruquintinib Combined With PD-1 Inhibitor as First-line Maintenance Therapy for Advanced Gastric Cancer"
          }
        ]
      },
      {
        "values": {
          "year": 2026,
          "trial_count": 4
        },
        "citations": [
          {
            "nct_id": "NCT07232602",
            "excerpt": "KEYMAKER-U04 Substudy 04D: A Clinical Study of New Treatments Given With Enfortumab Vedotin and Pembrolizumab in People With Urothelial Cancer (MK-3475-04D/KEYMAKER-U04)"
          },
          {
            "nct_id": "NCT07484139",
            "excerpt": "H&N NEO-COMBAT XL: Neoadjuvant XL-092 (Zanzalintinib) and Pembrolizumab (Keytruda) in Surgically Resectable, HPV Negative Oral Cavity Squamous Cell Carcinoma (OCSCC)"
          },
          {
            "nct_id": "NCT07365319",
            "excerpt": "A Safety and Efficacy Study of EIK1001 in Combination With Pembrolizumab and Chemotherapy in Participants With Stage 4 Non-Small Cell Lung Cancer."
          },
          {
            "nct_id": "NCT06093425",
            "excerpt": "Combination of Osemitamab (TST001), Pembrolizumab and Chemotherapy as First-line Therapy in Advanced or Metastatic GC/GEJ Adenocarcinoma"
          }
        ]
      }
    ]
  },
  "meta": {
    "filters_applied": {
      "drug_name": "Pembrolizumab"
    },
    "source": "clinicaltrials.gov",
    "total_studies_analyzed": 250,
    "query_interpretation": "This query shows the annual trend in the number of clinical trials for Pembrolizumab since 2015.",
    "assumptions": [
      "Aggregation mode: count_by_year",
      "Page size: 50, max pages: 5"
    ]
  }
}
```

### Example 2: Distribution by Phase

**Request:**
```json
{
  "query": "How are Diabetes trials distributed across phases?",
  "condition": "Diabetes"
}
```
**Response:**

```json
{
  "visualization": {
    "type": "bar_chart",
    "title": "Distribution of Diabetes Trials by Phase",
    "encoding": {
      "x": {
        "field": "phase",
        "type": "nominal"
      },
      "y": {
        "field": "trial_count",
        "type": "quantitative"
      }
    },
    "data": [
      {
        "values": {
          "phase": "NA",
          "trial_count": 117
        },
        "citations": [
          {
            "nct_id": "NCT06979635",
            "excerpt": "Assessing the Safety, Performance, and User Experience of the Tandem Mobi Automated Insulin Delivery System Among Young Competitive Athletes in Real-world Settings."
          },
          {
            "nct_id": "NCT06607497",
            "excerpt": "Better Risk Perception Via Patient Similarity to Control Hyperglycemia and Sustained by Telemonitoring"
          },
          {
            "nct_id": "NCT02388113",
            "excerpt": "Effect of Exercise Frequency on Metabolic Control and Heart Function in Type 2 Diabetes"
          },
          {
            "nct_id": "NCT00418288",
            "excerpt": "The Effect of GLP-1 on Glucose Uptake in the Brain and Heart in Healthy Men During Hypoglycemia"
          },
          {
            "nct_id": "NCT04385888",
            "excerpt": "Effects of Low-calorie Sweetened Beverage Restriction in Youth With Type 1 Diabetes"
          }
        ]
      },
      {
        "values": {
          "phase": "Not specified",
          "trial_count": 42
        },
        "citations": [
          {
            "nct_id": "NCT03437135",
            "excerpt": "Screening and Characterization of Hearing Disorders in Diabetic Persons"
          },
          {
            "nct_id": "NCT00404950",
            "excerpt": "Effects of Hyperglycemia During Cardiopulmonary Bypass on Renal Function"
          },
          {
            "nct_id": "NCT06708091",
            "excerpt": "Real-world Clinical Effectiveness and Patient Insight Associated With Adding Sodium Glucose Co-transporter 2 Inhibitor to Gliclazide Modified Release"
          },
          {
            "nct_id": "NCT05128097",
            "excerpt": "Preventive Approach for the Management of the Main Geriatric Risks"
          },
          {
            "nct_id": "NCT03172260",
            "excerpt": "Effect of E Balance Pro Therapy on Diabetes and Related Complications"
          }
        ]
      },
      {
        "values": {
          "phase": "PHASE2",
          "trial_count": 26
        },
        "citations": [
          {
            "nct_id": "NCT01157403",
            "excerpt": "Autologous Transplantation of Mesenchymal Stem Cells for Treatment of Patients With Onset of Type 1 Diabetes"
          },
          {
            "nct_id": "NCT03749642",
            "excerpt": "Trazodone/Gabapentin Fixed Dose Combination Products in Painful Diabetic Neuropathy"
          },
          {
            "nct_id": "NCT03665350",
            "excerpt": "Insulin Treatment in Diabetic Older People With Heart Failure."
          },
          {
            "nct_id": "NCT01528059",
            "excerpt": "Roux-en-Y Versus Billroth II Reconstruction After Subtotal Gastrectomy in Gastric Cancer Comorbid With Type II Diabetes"
          },
          {
            "nct_id": "NCT05638880",
            "excerpt": "Clinical Study to Evaluate the Possible Efficacy and Safety of Levocetirizine in Patients With Diabetic Kidney Disease"
          }
        ]
      },
      {
        "values": {
          "phase": "PHASE3",
          "trial_count": 24
        },
        "citations": [
          {
            "nct_id": "NCT00710424",
            "excerpt": "A Study of Sativex® for Pain Relief Due to Diabetic Neuropathy"
          },
          {
            "nct_id": "NCT01970046",
            "excerpt": "A Phase III Study of SP2086 in Combination With Metformin in Patients With Type 2 Diabetes"
          },
          {
            "nct_id": "NCT01157403",
            "excerpt": "Autologous Transplantation of Mesenchymal Stem Cells for Treatment of Patients With Onset of Type 1 Diabetes"
          },
          {
            "nct_id": "NCT01388361",
            "excerpt": "Comparison of the Efficacy and Safety of Two Intensification Strategies in Subjects With Type 2 Diabetes Inadequately Controlled on Basal Insulin and Metformin"
          },
          {
            "nct_id": "NCT01528059",
            "excerpt": "Roux-en-Y Versus Billroth II Reconstruction After Subtotal Gastrectomy in Gastric Cancer Comorbid With Type II Diabetes"
          }
        ]
      },
      {
        "values": {
          "phase": "PHASE4",
          "trial_count": 22
        },
        "citations": [
          {
            "nct_id": "NCT07117240",
            "excerpt": "Evaluation of the Efficacy and Safety of GLP-1 Receptor Agonist Therapy In Steroid-Induced Diabetes"
          },
          {
            "nct_id": "NCT01006590",
            "excerpt": "Efficacy and Tolerability of Saxagliptin add-on Compared to Uptitration of Metformin in Patients With Type 2 Diabetes"
          },
          {
            "nct_id": "NCT03253562",
            "excerpt": "Metformin Versus Vildagliptin for Diabetic Hypertensive Patients"
          },
          {
            "nct_id": "NCT00437489",
            "excerpt": "A Clinical Trial Comparing The Efficacy And Safety Of 2 Different Initial Dose Prescriptions For Exubera."
          },
          {
            "nct_id": "NCT00212290",
            "excerpt": "Insulin Resistance and Central Nervous System (CNS) Function in Type 2 Diabetes"
          }
        ]
      },
      {
        "values": {
          "phase": "PHASE1",
          "trial_count": 18
        },
        "citations": [
          {
            "nct_id": "NCT06982846",
            "excerpt": "A Study to Investigate the Response of Participants With Type 2 Diabetes Mellitus on Once-Weekly Retatrutide to Hypoglycemia"
          },
          {
            "nct_id": "NCT04768673",
            "excerpt": "A Study to Investigate the PK and Safety of CKD-393"
          },
          {
            "nct_id": "NCT04201496",
            "excerpt": "SGLT2 Inhibitor Adjunctive Therapy to Closed Loop Control in Type 1 Diabetes Mellitus"
          },
          {
            "nct_id": "NCT05227196",
            "excerpt": "A Research Study Looking at the Comparability of 2 Different Forms of Oral Semaglutide in Healthy People"
          },
          {
            "nct_id": "NCT02940418",
            "excerpt": "Use of Stem Cells in Diabetes Mellitus Type 1"
          }
        ]
      },
      {
        "values": {
          "phase": "EARLY_PHASE1",
          "trial_count": 5
        },
        "citations": [
          {
            "nct_id": "NCT04690270",
            "excerpt": "Sumatriptan and Glucose"
          },
          {
            "nct_id": "NCT03738852",
            "excerpt": "Mechanisms for Restoration of Hypoglycemia Awareness"
          },
          {
            "nct_id": "NCT05093517",
            "excerpt": "Effect of Novel Glucagon Receptor Antagonist REMD-477 on Glucose and Adipocyte Metabolism in T2DM"
          },
          {
            "nct_id": "NCT04742023",
            "excerpt": "Post-operative Complications and Graft Survival With Conventional Versus Continuous Glucose Monitoring in Patients With Diabetes Mellitus Undergoing Renal Transplantation"
          },
          {
            "nct_id": "NCT05847413",
            "excerpt": "Targeting Beta Cell Dysfunction With Verapamil in Longstanding T1D"
          }
        ]
      }
    ]
  },
  "meta": {
    "filters_applied": {
      "condition": "Diabetes"
    },
    "source": "clinicaltrials.gov",
    "total_studies_analyzed": 250,
    "query_interpretation": "This chart shows the number of clinical trials for Diabetes categorized by their development phase.",
    "assumptions": [
      "Aggregation mode: count_by_phase",
      "Page size: 50, max pages: 5"
    ]
  }
}
```

### Example 3: Geographic

**Request:**
```json
{
  "query": "Which countries have the most recruiting trials for Lung Cancer?",
  "condition": "Lung Cancer",
  "status": "RECRUITING"
}
```
**Response:**
```json
{
  "visualization": {
    "type": "bar_chart",
    "title": "Number of Recruiting Trials for Lung Cancer by Country",
    "encoding": {
      "x": {
        "field": "country",
        "type": "nominal"
      },
      "y": {
        "field": "trial_count",
        "type": "quantitative"
      }
    },
    "data": [
      {
        "values": {
          "country": "United States",
          "trial_count": 1391
        },
        "citations": [
          {
            "nct_id": "NCT06726590",
            "excerpt": "Interprofessional Pharmacogenomics (IPGx) Registry and Repository"
          },
          {
            "nct_id": "NCT01143480",
            "excerpt": "Study of the Effect of Innate on the Inflammatory Response to Endotoxin"
          },
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          }
        ]
      },
      {
        "values": {
          "country": "China",
          "trial_count": 372
        },
        "citations": [
          {
            "nct_id": "NCT06612840",
            "excerpt": "A Study of GNC-077 in Patients With Locally Advanced or Metastatic Non-small-cell Lung Cancer and Other Solid Tumors"
          },
          {
            "nct_id": "NCT06363123",
            "excerpt": "Plasma Metabolic Biomarkers for Multi-Cancer Diagnosis"
          },
          {
            "nct_id": "NCT06363123",
            "excerpt": "Plasma Metabolic Biomarkers for Multi-Cancer Diagnosis"
          },
          {
            "nct_id": "NCT06363123",
            "excerpt": "Plasma Metabolic Biomarkers for Multi-Cancer Diagnosis"
          },
          {
            "nct_id": "NCT06363123",
            "excerpt": "Plasma Metabolic Biomarkers for Multi-Cancer Diagnosis"
          }
        ]
      },
      {
        "values": {
          "country": "Spain",
          "trial_count": 189
        },
        "citations": [
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          }
        ]
      },
      {
        "values": {
          "country": "France",
          "trial_count": 127
        },
        "citations": [
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          }
        ]
      },
      {
        "values": {
          "country": "Italy",
          "trial_count": 117
        },
        "citations": [
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          }
        ]
      },
      {
        "values": {
          "country": "Germany",
          "trial_count": 113
        },
        "citations": [
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          }
        ]
      },
      {
        "values": {
          "country": "United Kingdom",
          "trial_count": 106
        },
        "citations": [
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT06923774",
            "excerpt": "European Real-World Registry for Use of the Ion Endoluminal System"
          },
          {
            "nct_id": "NCT06923774",
            "excerpt": "European Real-World Registry for Use of the Ion Endoluminal System"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          }
        ]
      },
      {
        "values": {
          "country": "Japan",
          "trial_count": 94
        },
        "citations": [
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT05498428",
            "excerpt": "A Study of Amivantamab in Participants With Advanced or Metastatic Solid Tumors Including Epidermal Growth Factor Receptor (EGFR)-Mutated Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT05498428",
            "excerpt": "A Study of Amivantamab in Participants With Advanced or Metastatic Solid Tumors Including Epidermal Growth Factor Receptor (EGFR)-Mutated Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT05498428",
            "excerpt": "A Study of Amivantamab in Participants With Advanced or Metastatic Solid Tumors Including Epidermal Growth Factor Receptor (EGFR)-Mutated Non-Small Cell Lung Cancer"
          }
        ]
      },
      {
        "values": {
          "country": "Taiwan",
          "trial_count": 85
        },
        "citations": [
          {
            "nct_id": "NCT05532696",
            "excerpt": "Phase 1b/2 Study to Evaluate ABT-101 in Solid Tumor and NSCLC Patients"
          },
          {
            "nct_id": "NCT05532696",
            "excerpt": "Phase 1b/2 Study to Evaluate ABT-101 in Solid Tumor and NSCLC Patients"
          },
          {
            "nct_id": "NCT05532696",
            "excerpt": "Phase 1b/2 Study to Evaluate ABT-101 in Solid Tumor and NSCLC Patients"
          },
          {
            "nct_id": "NCT05532696",
            "excerpt": "Phase 1b/2 Study to Evaluate ABT-101 in Solid Tumor and NSCLC Patients"
          },
          {
            "nct_id": "NCT05532696",
            "excerpt": "Phase 1b/2 Study to Evaluate ABT-101 in Solid Tumor and NSCLC Patients"
          }
        ]
      },
      {
        "values": {
          "country": "Canada",
          "trial_count": 74
        },
        "citations": [
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT06960291",
            "excerpt": "Sustainable Implementation of the EXCEL Exercise Oncology Program Across Canada"
          },
          {
            "nct_id": "NCT06960291",
            "excerpt": "Sustainable Implementation of the EXCEL Exercise Oncology Program Across Canada"
          },
          {
            "nct_id": "NCT06960291",
            "excerpt": "Sustainable Implementation of the EXCEL Exercise Oncology Program Across Canada"
          }
        ]
      },
      {
        "values": {
          "country": "South Korea",
          "trial_count": 73
        },
        "citations": [
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          }
        ]
      },
      {
        "values": {
          "country": "Australia",
          "trial_count": 70
        },
        "citations": [
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          }
        ]
      },
      {
        "values": {
          "country": "Brazil",
          "trial_count": 60
        },
        "citations": [
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          }
        ]
      },
      {
        "values": {
          "country": "Turkey (Türkiye)",
          "trial_count": 43
        },
        "citations": [
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          }
        ]
      },
      {
        "values": {
          "country": "Poland",
          "trial_count": 40
        },
        "citations": [
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          }
        ]
      },
      {
        "values": {
          "country": "Belgium",
          "trial_count": 37
        },
        "citations": [
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          },
          {
            "nct_id": "NCT06095583",
            "excerpt": "Phase 3 Study of Toripalimab Alone or in Combination With Tifcemalimab as Consolidation Therapy in Patients With Limited-stage Small Cell Lung Cancer (LS-SCLC)"
          }
        ]
      },
      {
        "values": {
          "country": "Israel",
          "trial_count": 37
        },
        "citations": [
          {
            "nct_id": "NCT05632913",
            "excerpt": "Alpha Radiation Emitters Device for the Treatment of Recurrent Lung Cancer"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          },
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          }
        ]
      },
      {
        "values": {
          "country": "Switzerland",
          "trial_count": 33
        },
        "citations": [
          {
            "nct_id": "NCT04938817",
            "excerpt": "Safety and Efficacy Study of Investigational Agents as Monotherapy or in Combination With Pembrolizumab (MK-3475) for the Treatment of Extensive-Stage Small Cell Lung Cancer (ES-SCLC) in Need of Second-Line Therapy (MK-3475-B98/KEYNOTE-B98)"
          },
          {
            "nct_id": "NCT06923774",
            "excerpt": "European Real-World Registry for Use of the Ion Endoluminal System"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          }
        ]
      },
      {
        "values": {
          "country": "Netherlands",
          "trial_count": 26
        },
        "citations": [
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          },
          {
            "nct_id": "NCT04075305",
            "excerpt": "The MOMENTUM Study: The Multiple Outcome Evaluation of Radiation Therapy Using the MR-Linac Study"
          }
        ]
      },
      {
        "values": {
          "country": "Greece",
          "trial_count": 24
        },
        "citations": [
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          },
          {
            "nct_id": "NCT06793215",
            "excerpt": "A Study Evaluating the Efficacy and Safety of Divarasib and Pembrolizumab Versus Pembrolizumab and Pemetrexed and Carboplatin or Cisplatin in Participants With Previously Untreated, KRAS G12C-Mutated, Advanced or Metastatic Non-Squamous Non-Small Cell Lung Cancer"
          }
        ]
      }
    ]
  },
  "meta": {
    "filters_applied": {
      "condition": "Lung Cancer",
      "status": "RECRUITING"
    },
    "source": "clinicaltrials.gov",
    "total_studies_analyzed": 250,
    "query_interpretation": "This query counts the number of recruiting clinical trials for Lung Cancer, grouped by country.",
    "assumptions": [
      "Aggregation mode: count_by_country",
      "Page size: 50, max pages: 5"
    ]
  }
}
```

### Example 4: Comparison

**Request:**
```json
{
  "query": "Compare phases for trials involving Aspirin vs Ibuprofen.",
}
```
**Response:** 
```json
{
  "visualization": {
    "type": "grouped_bar_chart",
    "title": "Trial Phases for Aspirin vs Ibuprofen",
    "encoding": {
      "x": {
        "field": "phase",
        "type": "nominal"
      },
      "y": {
        "field": "trial_count",
        "type": "quantitative"
      },
      "color": {
        "field": "drug",
        "type": "nominal"
      }
    },
    "data": [
      {
        "values": {
          "drug": "Aspirin",
          "phase": "PHASE3",
          "trial_count": 63
        },
        "citations": [
          {
            "nct_id": "NCT01645124",
            "excerpt": "Large-scale Trial Testing the Intensity of CYTOreductive Therapy in Polycythemia Vera (PV)"
          },
          {
            "nct_id": "NCT01398410",
            "excerpt": "Long-term Prevention of Recurrent Gastric or Duodenal Ulcers Caused by Low-dose Aspirin With Rabeprazole (E3810) Treatment (Planetarium Study)"
          },
          {
            "nct_id": "NCT04360720",
            "excerpt": "Percutaneous Coronary Intervention Followed by Antiplatelet Monotherapy in the Setting of Acute Coronary Syndromes"
          }
        ]
      },
      {
        "values": {
          "drug": "Aspirin",
          "phase": "PHASE4",
          "trial_count": 62
        },
        "citations": [
          {
            "nct_id": "NCT01069003",
            "excerpt": "EDUCATE: The MEDTRONIC Endeavor Drug Eluting Stenting: Understanding Care, Antiplatelet Agents and Thrombotic Events"
          },
          {
            "nct_id": "NCT02567461",
            "excerpt": "Edoxaban in Patients With Coronary Artery Disease on Dual Antiplatelet Therapy With Aspirin and Clopidogrel"
          },
          {
            "nct_id": "NCT02049762",
            "excerpt": "Aspirin Impact on Platelet Reactivity in Acute Coronary Syndrome Patients on Novel P2Y12 Inhibitors Therapy"
          }
        ]
      },
      {
        "values": {
          "drug": "Aspirin",
          "phase": "NA",
          "trial_count": 48
        },
        "citations": [
          {
            "nct_id": "NCT02825446",
            "excerpt": "Angioplasty of the Tibial Arteries Augmented Radio Frequency Denervation of the Popliteal Artery"
          },
          {
            "nct_id": "NCT00942617",
            "excerpt": "Measurement of Platelet Dense Granule Release in Healthy Volunteers"
          },
          {
            "nct_id": "NCT02359643",
            "excerpt": "Multi-center Prospective Randomized Control Trail of High Dose Aspirin in Acute Stage of Kawasaki Disease"
          }
        ]
      },
      {
        "values": {
          "drug": "Aspirin",
          "phase": "PHASE2",
          "trial_count": 35
        },
        "citations": [
          {
            "nct_id": "NCT04239196",
            "excerpt": "Efficacy of Tocilizumab for the Treatment of Acute AION Related to GCA"
          },
          {
            "nct_id": "NCT01398410",
            "excerpt": "Long-term Prevention of Recurrent Gastric or Duodenal Ulcers Caused by Low-dose Aspirin With Rabeprazole (E3810) Treatment (Planetarium Study)"
          },
          {
            "nct_id": "NCT00759850",
            "excerpt": "Drug Eluting Stent (DES) in Primary Angioplasty"
          }
        ]
      },
      {
        "values": {
          "drug": "Aspirin",
          "phase": "Not specified",
          "trial_count": 33
        },
        "citations": [
          {
            "nct_id": "NCT03330223",
            "excerpt": "Effect of Haemodialysis on the Efficacy of Antiplatelet Agents"
          },
          {
            "nct_id": "NCT02837003",
            "excerpt": "3-Month Discontinuation of Dual Antiplatelet Therapy After Ultimaster Sirolimus-Eluting Stent Implantation"
          },
          {
            "nct_id": "NCT00728286",
            "excerpt": "Assessment of Thrombogenicity in Acute Coronary Syndrome"
          }
        ]
      },
      {
        "values": {
          "drug": "Aspirin",
          "phase": "PHASE1",
          "trial_count": 17
        },
        "citations": [
          {
            "nct_id": "NCT07323680",
            "excerpt": "Comparative Pharmacokinetic, Pharmacodynamic, and Safety Study of 1 Dose of Aspirin for Injection and Oral Aspirin Tablets in Healthy Adult Subjects"
          },
          {
            "nct_id": "NCT00331786",
            "excerpt": "Nitric Oxide-Releasing Acetylsalicyclic Acid in Preventing Colorectal Cancer in Patients at High Risk of Colorectal Cancer"
          },
          {
            "nct_id": "NCT00872534",
            "excerpt": "Endoscopic Evaluation of Upper Gastrointestinal (GI) Mucosal Damage Induced by PL-2200 Versus Aspirin in Healthy Volunteers"
          }
        ]
      },
      {
        "values": {
          "drug": "Aspirin",
          "phase": "EARLY_PHASE1",
          "trial_count": 8
        },
        "citations": [
          {
            "nct_id": "NCT04284397",
            "excerpt": "Identification of Critical Thermal Environments for Aged Adults"
          },
          {
            "nct_id": "NCT02029118",
            "excerpt": "Acupoint Application in Patients With Stable Angina Pectoris (AASAP)"
          },
          {
            "nct_id": "NCT06906939",
            "excerpt": "A Randomized Pilot rTMS Trial for Knee Arthritis Pain and Depression"
          }
        ]
      },
      {
        "values": {
          "drug": "Ibuprofen",
          "phase": "NA",
          "trial_count": 74
        },
        "citations": [
          {
            "nct_id": "NCT05241496",
            "excerpt": "Lidocaine Spray 10% Versus Oral Ibuprofen Tablets in Pain Control During Copper Intrauterine Device Insertion"
          },
          {
            "nct_id": "NCT02902913",
            "excerpt": "Impact of Extra Virgin Olive Oil Oleocanthal Content on Platelet Reactivity"
          },
          {
            "nct_id": "NCT01606540",
            "excerpt": "Non-steroid Antiinflammatory Drugs to Heal Colles Fracture"
          }
        ]
      },
      {
        "values": {
          "drug": "Ibuprofen",
          "phase": "PHASE4",
          "trial_count": 72
        },
        "citations": [
          {
            "nct_id": "NCT01350596",
            "excerpt": "A Bioequivalence Study Of Ibuprofen 50mg/ml (laboratórios Pfizer Ltda) In The Oral Suspension Form."
          },
          {
            "nct_id": "NCT02571361",
            "excerpt": "PAracetamol and NSAID in Combination: A Randomised, Blinded, Parallel, 4-group Clinical Trial"
          },
          {
            "nct_id": "NCT01953978",
            "excerpt": "The Effect of Dexamethasone in Combination With Paracetamol and Ibuprofen on Postoperative Pain After Spine Surgery"
          }
        ]
      },
      {
        "values": {
          "drug": "Ibuprofen",
          "phase": "PHASE3",
          "trial_count": 36
        },
        "citations": [
          {
            "nct_id": "NCT04429282",
            "excerpt": "A Multicenter, Randomized, Double-Blind, Placebo-Controlled Trial of Intravenous Ibuprofen 400 and 800 mg Every 6 Hours in the Management of Postoperative Pain."
          },
          {
            "nct_id": "NCT01442428",
            "excerpt": "Paradoxical Tuberculosis Immune Reconstitution Inflammatory Syndrome (TB-IRIS) Treatment Trial"
          },
          {
            "nct_id": "NCT02668783",
            "excerpt": "Efficacy and Safety of Etonogestrel + 17β-Estradiol Vaginal Ring (MK-8342B) in Women With Primary Dysmenorrhea (With Optional Extension) (MK-8342B-059)"
          }
        ]
      },
      {
        "values": {
          "drug": "Ibuprofen",
          "phase": "PHASE2",
          "trial_count": 31
        },
        "citations": [
          {
            "nct_id": "NCT06088732",
            "excerpt": "Effects of Acute Exercise and Ibuprofen on Symptoms, Immunity, and Neural Circuits in Bipolar Depression"
          },
          {
            "nct_id": "NCT01442428",
            "excerpt": "Paradoxical Tuberculosis Immune Reconstitution Inflammatory Syndrome (TB-IRIS) Treatment Trial"
          },
          {
            "nct_id": "NCT00219700",
            "excerpt": "Ibuprofen-PC Compared With Ibuprofen in a GI Safety Trial"
          }
        ]
      },
      {
        "values": {
          "drug": "Ibuprofen",
          "phase": "PHASE1",
          "trial_count": 25
        },
        "citations": [
          {
            "nct_id": "NCT06088732",
            "excerpt": "Effects of Acute Exercise and Ibuprofen on Symptoms, Immunity, and Neural Circuits in Bipolar Depression"
          },
          {
            "nct_id": "NCT03418805",
            "excerpt": "To Evaluate the Food Effect and the Absorption Profile of Ibuprofen Controlled-Release Tablets 600 mg in Comparison to the Reference Standard Ibuprofen Tablets in Normal Healthy Volunteers"
          },
          {
            "nct_id": "NCT02963701",
            "excerpt": "Bioequivalence of a Fixed Dose Combination Tablet Containing 400 mg Ibuprofen and 60 mg Pseudoephedrine-HCl Compared to Two Film Coated Fixed Dose Combination Tablets RhinAdvil(R)(200 mg Ibuprofen and 30 mg Pseudoephedrine-HCl) Administered in Healthy Subjects"
          }
        ]
      },
      {
        "values": {
          "drug": "Ibuprofen",
          "phase": "Not specified",
          "trial_count": 15
        },
        "citations": [
          {
            "nct_id": "NCT02553174",
            "excerpt": "AKI in Thoracic and Abdominal Surgery"
          },
          {
            "nct_id": "NCT06707818",
            "excerpt": "Psychosocial Factors and Postoperative Pain in Aesthetic Breast Surgery"
          },
          {
            "nct_id": "NCT07374146",
            "excerpt": "Research on the Individualized Treatment Strategy for Extremely Preterm Infants With hsPDA Based on Biomarkers and Targeted Delivery Systems"
          }
        ]
      },
      {
        "values": {
          "drug": "Ibuprofen",
          "phase": "EARLY_PHASE1",
          "trial_count": 2
        },
        "citations": [
          {
            "nct_id": "NCT03243032",
            "excerpt": "Pre-Emptive Analgesia in Dental Implant Surgery"
          },
          {
            "nct_id": "NCT06484439",
            "excerpt": "Controlled Trial to Determine Most Effective Post-Operative Analgesia After Third Molar Extraction"
          }
        ]
      }
    ]
  },
  "meta": {
    "filters_applied": {
      "drug_name": "Aspirin, Ibuprofen"
    },
    "source": "clinicaltrials.gov",
    "total_studies_analyzed": 14,
    "query_interpretation": "Compares the distribution of trial phases for studies involving Aspirin against those involving Ibuprofen.",
    "assumptions": [
      "Aggregation mode: compare_drugs_by_phase",
      "Page size: 50, max pages: 5"
    ]
  }
}
```

### Example 5: Network Graph

**Request:**
```json
{
  "query": "Show a network of sponsors and drugs for Breast Cancer trials.",
  "condition": "Breast Cancer"
}
```
**Response:**
```json
{
  "visualization": {
    "type": "network_graph",
    "title": "Sponsor-Drug Network for Breast Cancer Trials",
    "encoding": {
      "source": {
        "field": "sponsor",
        "type": "nominal"
      },
      "target": {
        "field": "drug",
        "type": "nominal"
      },
      "weight": {
        "field": "weight",
        "type": "quantitative"
      }
    },
    "data": [
      {
        "values": {
          "sponsor": "Monte Rosa Therapeutics, Inc",
          "drug": "Oral MRT-2359",
          "weight": 6
        },
        "citations": [
          {
            "nct_id": "NCT05546268",
            "excerpt": "Study of Oral MRT-2359 in Selected Cancer Patients"
          },
          {
            "nct_id": "NCT05546268",
            "excerpt": "Study of Oral MRT-2359 in Selected Cancer Patients"
          },
          {
            "nct_id": "NCT05546268",
            "excerpt": "Study of Oral MRT-2359 in Selected Cancer Patients"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Koning Corporation",
          "drug": "Computed Tomography",
          "weight": 3
        },
        "citations": [
          {
            "nct_id": "NCT00972413",
            "excerpt": "Cone Beam Computed Tomography for Breast Imaging"
          },
          {
            "nct_id": "NCT00972413",
            "excerpt": "Cone Beam Computed Tomography for Breast Imaging"
          },
          {
            "nct_id": "NCT00972413",
            "excerpt": "Cone Beam Computed Tomography for Breast Imaging"
          }
        ]
      },
      {
        "values": {
          "sponsor": "EMD Serono",
          "drug": "MSC1936369B (pimasertib)",
          "weight": 2
        },
        "citations": [
          {
            "nct_id": "NCT01390818",
            "excerpt": "Trial of MEK Inhibitor and PI3K/mTOR Inhibitor in Subjects With Locally Advanced or Metastatic Solid Tumors"
          },
          {
            "nct_id": "NCT01390818",
            "excerpt": "Trial of MEK Inhibitor and PI3K/mTOR Inhibitor in Subjects With Locally Advanced or Metastatic Solid Tumors"
          }
        ]
      },
      {
        "values": {
          "sponsor": "EMD Serono",
          "drug": "SAR245409 (PI3K and mTOR inhibitor)",
          "weight": 2
        },
        "citations": [
          {
            "nct_id": "NCT01390818",
            "excerpt": "Trial of MEK Inhibitor and PI3K/mTOR Inhibitor in Subjects With Locally Advanced or Metastatic Solid Tumors"
          },
          {
            "nct_id": "NCT01390818",
            "excerpt": "Trial of MEK Inhibitor and PI3K/mTOR Inhibitor in Subjects With Locally Advanced or Metastatic Solid Tumors"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Novartis Pharmaceuticals",
          "drug": "Letrozole",
          "weight": 2
        },
        "citations": [
          {
            "nct_id": "NCT00237224",
            "excerpt": "Open Label Study of Postmenopausal Women With ER and /or PgR Positive Breast Cancer Treated With Letrozole"
          },
          {
            "nct_id": "NCT02154776",
            "excerpt": "Dose Escalation Study of LEE011 in Combination With Buparlisib and Letrozole in HR+, HER2-negative Post-menopausal Women With Advanced Breast Cancer."
          }
        ]
      },
      {
        "values": {
          "sponsor": "Jules Bordet Institute",
          "drug": "Sampling of tumor tissue after breast cancer surgery",
          "weight": 2
        },
        "citations": [
          {
            "nct_id": "NCT01916837",
            "excerpt": "Genomic Grade Index (GGI): Feasibility in Routine Practice and Impact on Treatment Decisions in Early Breast Cancer"
          },
          {
            "nct_id": "NCT01916837",
            "excerpt": "Genomic Grade Index (GGI): Feasibility in Routine Practice and Impact on Treatment Decisions in Early Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Sanofi",
          "drug": "Docetaxel",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00688740",
            "excerpt": "Docetaxel in Node Positive Adjuvant Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Sanofi",
          "drug": "5-fluorouracil",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00688740",
            "excerpt": "Docetaxel in Node Positive Adjuvant Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Sanofi",
          "drug": "Doxorubicin",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00688740",
            "excerpt": "Docetaxel in Node Positive Adjuvant Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Sanofi",
          "drug": "Cyclophosphamide",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00688740",
            "excerpt": "Docetaxel in Node Positive Adjuvant Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Beijing Friendship Hospital",
          "drug": "The breast reconstruction method after single-port insufflation endoscopic nipple-sparing mastectomy",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT05833659",
            "excerpt": "Comparison Between Prepectoral and Subpectoral Breast Reconstruction"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Cynthia Aristei",
          "drug": "Hepilor",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT03997188",
            "excerpt": "Zinc-L-Carnosine Prevents Dysphagia in Breast Cancer Patients Undergoing Adjuvant Radiotherapy"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Milton S. Hershey Medical Center",
          "drug": "Placebo",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT01784042",
            "excerpt": "Dietary Energy Restriction and Omega-3 Fatty Acids on Mammary Tissue"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Milton S. Hershey Medical Center",
          "drug": "Lovaza",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT01784042",
            "excerpt": "Dietary Energy Restriction and Omega-3 Fatty Acids on Mammary Tissue"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Milton S. Hershey Medical Center",
          "drug": "Dietary energy restriction",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT01784042",
            "excerpt": "Dietary Energy Restriction and Omega-3 Fatty Acids on Mammary Tissue"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Sheng Liu",
          "drug": "Traditional Chinese medicine",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT03332368",
            "excerpt": "Clinical Study on Triple Negative Breast Cancer With Chinese Medicine"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Washington University School of Medicine",
          "drug": "Sentinel Lymph Node Biopsy",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT01821768",
            "excerpt": "Axillary Ultrasound With or Without Sentinel Lymph Node Biopsy in Detecting the Spread of Breast Cancer in Patients Receiving Breast Conservation Therapy"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Rogers Sciences Inc.",
          "drug": "Verteporfin",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT02939274",
            "excerpt": "An Open Label, Phase II Trial of Continuous Low-Irradiance Photodynamic Therapy (CLIPT) Using Verteporfin (Visudyne®) for the Treatment of Cutaneous Metastases of Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Rogers Sciences Inc.",
          "drug": "Continuous Low-Irradiance Photodynamic Therapy (CLIPT)",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT02939274",
            "excerpt": "An Open Label, Phase II Trial of Continuous Low-Irradiance Photodynamic Therapy (CLIPT) Using Verteporfin (Visudyne®) for the Treatment of Cutaneous Metastases of Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Mater Misericordiae University Hospital",
          "drug": "Pectoral Plane Block",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT03024697",
            "excerpt": "Single-shot Pectoral Plane(PECs) Block Versus Continuous Local Anaesthetic Infusion Analgesia or Both PECS Block and Local Anaesthetic Infusion After Breast Surgery: A Prospective Randomised, Double-blind Trial"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Mater Misericordiae University Hospital",
          "drug": "Local Anaesthetic Wound Infusion Catheter",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT03024697",
            "excerpt": "Single-shot Pectoral Plane(PECs) Block Versus Continuous Local Anaesthetic Infusion Analgesia or Both PECS Block and Local Anaesthetic Infusion After Breast Surgery: A Prospective Randomised, Double-blind Trial"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Novartis Pharmaceuticals",
          "drug": "ribociclib + AI ± LHRH",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT06830720",
            "excerpt": "A Non-interventional Study for Kisqali (Ribociclib) in Combination With an Aromatase Inhibitor for Adjuvant Treatment in Patients With HR+/HER2- Early Breast Cancer at High Risk of Recurrence"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Novartis Pharmaceuticals",
          "drug": "abemaciclib + ET ± LHRH",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT06830720",
            "excerpt": "A Non-interventional Study for Kisqali (Ribociclib) in Combination With an Aromatase Inhibitor for Adjuvant Treatment in Patients With HR+/HER2- Early Breast Cancer at High Risk of Recurrence"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Novartis Pharmaceuticals",
          "drug": "ET mono ± LHRH",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT06830720",
            "excerpt": "A Non-interventional Study for Kisqali (Ribociclib) in Combination With an Aromatase Inhibitor for Adjuvant Treatment in Patients With HR+/HER2- Early Breast Cancer at High Risk of Recurrence"
          }
        ]
      },
      {
        "values": {
          "sponsor": "National University Hospital, Singapore",
          "drug": "doxorubicin, docetaxel",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00212082",
            "excerpt": "Gene Expression Profiles in Predicting Chemotherapy Response in Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Instituto Nacional de Cancer, Brazil",
          "drug": "Megestrol Acetate 160Mg Tablet",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT03024580",
            "excerpt": "A Study Evaluating Megestrol Acetate Modulation in Hormone Receptor Positive Advanced Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Instituto Nacional de Cancer, Brazil",
          "drug": "Anastrozole 1Mg Tablet",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT03024580",
            "excerpt": "A Study Evaluating Megestrol Acetate Modulation in Hormone Receptor Positive Advanced Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Instituto Nacional de Cancer, Brazil",
          "drug": "Letrozole 2.5Mg Tablet",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT03024580",
            "excerpt": "A Study Evaluating Megestrol Acetate Modulation in Hormone Receptor Positive Advanced Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Instituto Nacional de Cancer, Brazil",
          "drug": "Exemestane 25 MG",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT03024580",
            "excerpt": "A Study Evaluating Megestrol Acetate Modulation in Hormone Receptor Positive Advanced Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Instituto Nacional de Cancer, Brazil",
          "drug": "Tamoxifen 20Mg Tablet",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT03024580",
            "excerpt": "A Study Evaluating Megestrol Acetate Modulation in Hormone Receptor Positive Advanced Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "Instituto Nacional de Cancer, Brazil",
          "drug": "Fulvestrant 50Mg Solution for Injection",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT03024580",
            "excerpt": "A Study Evaluating Megestrol Acetate Modulation in Hormone Receptor Positive Advanced Breast Cancer"
          }
        ]
      },
      {
        "values": {
          "sponsor": "OHSU Knight Cancer Institute",
          "drug": "Clinic Intervention",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT01773980",
            "excerpt": "CROSSROAD II: Activating Rural Clinics and Women With Disabilities to Improve Cancer Screening"
          }
        ]
      },
      {
        "values": {
          "sponsor": "OHSU Knight Cancer Institute",
          "drug": "Patient Intervention",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT01773980",
            "excerpt": "CROSSROAD II: Activating Rural Clinics and Women With Disabilities to Improve Cancer Screening"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "doxorubicin hydrochloride",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "cyclophosphamide",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "paclitaxel",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "filgrastim",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "capecitabine",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "methotrexate",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "vinorelbine tartrate",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "needle biopsy",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "therapeutic conventional surgery",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "immunohistochemistry staining method",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "trastuzumab",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "tamoxifen citrate",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "letrozole",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "University of Washington",
          "drug": "laboratory biomarker analysis",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT00194779",
            "excerpt": "Combination Chemotherapy and Filgrastim Before Surgery in Treating Patients With HER2-Positive Breast Cancer That Can Be Removed By Surgery"
          }
        ]
      },
      {
        "values": {
          "sponsor": "The First Affiliated Hospital of the Fourth Military Medical University",
          "drug": "Conventional-reading",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT04527510",
            "excerpt": "Remote Breast Cancer Screening Study"
          }
        ]
      },
      {
        "values": {
          "sponsor": "The First Affiliated Hospital of the Fourth Military Medical University",
          "drug": "Second-reading",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT04527510",
            "excerpt": "Remote Breast Cancer Screening Study"
          }
        ]
      },
      {
        "values": {
          "sponsor": "The First Affiliated Hospital of the Fourth Military Medical University",
          "drug": "Concurrent-reading",
          "weight": 1
        },
        "citations": [
          {
            "nct_id": "NCT04527510",
            "excerpt": "Remote Breast Cancer Screening Study"
          }
        ]
      }
    ]
  },
  "meta": {
    "filters_applied": {
      "condition": "Breast Cancer"
    },
    "source": "clinicaltrials.gov",
    "total_studies_analyzed": 250,
    "query_interpretation": "Display a network graph showing the relationships between sponsors and drugs in clinical trials related to Breast Cancer.",
    "assumptions": [
      "Aggregation mode: sponsor_drug_network",
      "Page size: 50, max pages: 5"
    ]
  }
}
```

---

## Limitations & Future Improvements

- **Caching**: Repeated identical queries re-fetch from ClinicalTrials.gov. Adding a TTL cache (Redis or in-memory) would reduce latency.
- **Single-level aggregation**: Each query produces only one visualization. A multi-panel dashboard mode would support exploratory analysis better.
- **LLM dependency**: The planner requires a Google AI Studio API key. Could add a rule-based fallback for common query patterns.
- **Pagination cap**: Currently fetches up to 250 studies (5 pages). Could implement streaming or background jobs for larger datasets.
- **More visualization types**: Heatmaps, Sankey diagrams, and geographic maps would enrich the output.

---

## Integrity Note

- **AI tools used**: Cursor (Claude Opus 4.6 Max) for test code (unit test+integration test), frontend (UI - html) generation and iteration. GPT-5.4 for README structure refinement, and prompt refinement. 
- **What I designed/decided deliberately**:
  - Simplistic agent architecture (Plan + Execute + Visualize)
  - Schema Design
  - Technology choices: Google Gemini over OpenAI, SonarCloud for code quality, Docker Hub for distribution.
  - CI/CD pipeline structure: separate jobs for code quality, unit tests, integration tests, SonarCloud analysis, and Docker build/push.
  - Security practices: all secrets via GitHub Secrets, nothing hardcoded.
  - Drove iterative testing against the live API, which uncovered real integration issues.
- **What was adapted from AI-generated code**:
  - Anti-hallucination strategy (Prompts refinement)
  - Aggregation functions, and encoding mappings
  - Tests structure (unit and integration tests)
  - Frontend single-page app (Chart.js + vis-network)
- **Discovered and fixed through manual testing** (initial errors: first attempt):
  - Gemini wraps JSON in extra keys → built an unwrapping layer with validation
  - Gemini omits optional fields → added resilient defaults on QueryPlan
  - ClinicalTrials.gov rejects free-text status values like "active" → built a normalization layer mapping common terms to valid API enums
  - `httpx` library gets 403'd by ClinicalTrials.gov (TLS fingerprinting) → switched to `requests`
- **Validation**: 86 unit tests + 3 integration tests (97% code coverage). SonarCloud dashboard monitors code smells, duplication, and maintainability. Manual end-to-end testing with diverse queries across all visualization types. Deployed as a Docker image, pulled on a different system and performed integration tests.
