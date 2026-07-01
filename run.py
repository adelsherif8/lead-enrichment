"""CLI: run the full pipeline over a Data Axle export.

    python run.py [path/to/export.csv]

Cleans → enriches (live web search) → qualifies → syncs to Airtable (or local
mock) and writes data/results.json for the UI. Errors on one company never
abort the batch."""

from __future__ import annotations

import json
import pathlib
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from app.clean import load_clean_leads  # noqa: E402
from app.pipeline import process_lead  # noqa: E402
from app.airtable import sync  # noqa: E402

DATA = pathlib.Path(__file__).parent / "data"


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else str(DATA / "sample_leads.csv")
    leads = load_clean_leads(src)
    print(f"Loaded {len(leads)} leads from {src}\n")

    results = []
    for i, lead in enumerate(leads, 1):
        print(f"[{i}/{len(leads)}] {lead.company_name} … ", end="", flush=True)
        t = time.time()
        try:
            res = process_lead(lead)
            q = res.qualification
            print(f"{q.status}  fit={q.fit_score} conf={q.confidence}  ({time.time()-t:.1f}s)")
            results.append(res)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: {e}")

    (DATA / "results.json").write_text(
        json.dumps([r.model_dump() for r in results], indent=2)
    )
    summary = sync(results)
    counts = {}
    for r in results:
        counts[r.qualification.status] = counts.get(r.qualification.status, 0) + 1
    print(f"\nDone. {counts}  | Airtable sync: {summary}")
    print(f"Results → {DATA/'results.json'}")


if __name__ == "__main__":
    main()
