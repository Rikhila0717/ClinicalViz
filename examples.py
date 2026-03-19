"""
Generate example query/response pairs for documentation.

Usage:
    python examples.py              # prints to stdout
    python examples.py --save       # writes examples/ directory
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from app.agent import process_query
from app.schemas import QueryRequest

EXAMPLE_QUERIES = [
    {
        "label": "Time trend — Pembrolizumab trials over time",
        "request": QueryRequest(
            query="How has the number of trials for Pembrolizumab changed per year since 2015?",
            drug_name="Pembrolizumab",
            start_year=2015,
        ),
    },
    {
        "label": "Distribution — Diabetes trials by phase",
        "request": QueryRequest(
            query="How are Diabetes trials distributed across phases?",
            condition="Diabetes",
        ),
    },
    {
        "label": "Geographic — Recruiting Lung Cancer trials by country",
        "request": QueryRequest(
            query="Which countries have the most recruiting trials for Lung Cancer?",
            condition="Lung Cancer",
            status="RECRUITING",
        ),
    },
    {
        "label": "Comparison — Aspirin vs Ibuprofen by phase",
        "request": QueryRequest(
            query="Compare phases for trials involving Aspirin vs Ibuprofen.",
        ),
    },
    {
        "label": "Network — Sponsor-drug relationships for Breast Cancer",
        "request": QueryRequest(
            query="Show a network of sponsors and drugs for Breast Cancer trials.",
            condition="Breast Cancer",
        ),
    },
]


async def run_examples(save: bool = False):
    out_dir = Path("examples")
    if save:
        out_dir.mkdir(exist_ok=True)

    for i, ex in enumerate(EXAMPLE_QUERIES, 1):
        print(f"\n{'='*72}")
        print(f"Example {i}: {ex['label']}")
        print(f"{'='*72}")

        req: QueryRequest = ex["request"]
        print(f"Request:\n{req.model_dump_json(indent=2, exclude_none=True)}\n")

        try:
            resp = await process_query(req)
            resp_json = resp.model_dump_json(indent=2)
            print(f"Response:\n{resp_json}\n")

            if save:
                fname = f"example_{i}.json"
                payload = {
                    "label": ex["label"],
                    "request": json.loads(req.model_dump_json(exclude_none=True)),
                    "response": json.loads(resp_json),
                }
                (out_dir / fname).write_text(json.dumps(payload, indent=2))
                print(f"  → saved to {out_dir / fname}")
        except Exception as exc:
            print(f"  ERROR: {exc}")


if __name__ == "__main__":
    save = "--save" in sys.argv
    asyncio.run(run_examples(save))
