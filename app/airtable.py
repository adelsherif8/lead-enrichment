"""Stage 4 — push qualified leads to Airtable, deduped.

- Pass / Needs Review  → main "Leads" table
- Reject               → separate "Rejected" log
Dedupe key is the source record_id (upsert: update if present, else create).

If AIRTABLE_TOKEN + AIRTABLE_BASE_ID are set it writes to real Airtable; otherwise
it writes the exact same records to local JSON files so the pipeline runs end-to-end
with zero setup. The record shape is identical either way."""

from __future__ import annotations

import json
import os
import pathlib
from typing import Dict, List

from app.schema import LeadResult

_DATA = pathlib.Path(__file__).parent.parent / "data"
MAIN_TABLE = os.getenv("AIRTABLE_MAIN_TABLE", "Leads")
REJECTED_TABLE = os.getenv("AIRTABLE_REJECTED_TABLE", "Rejected")


def to_record(r: LeadResult) -> Dict:
    c, e, q = r.clean, r.enrichment, r.qualification
    return {
        "record_id": c.record_id,
        "company": c.company_name,
        "city": c.city,
        "state": c.state,
        "industry": c.industry,
        "status": q.status,
        "fit_score": q.fit_score,
        "confidence": q.confidence,
        "website": e.website,
        "owner": e.owner_name,
        "owner_title": e.owner_title,
        "email": e.decision_maker_email,
        "company_linkedin": e.company_linkedin,
        "owner_linkedin": e.owner_linkedin,
        "services": e.services,
        "ownership_signal": e.ownership_signal,
        "red_flags": ", ".join(e.red_flags) if e.red_flags else None,
        "reasons": q.reasons,
        "missing_data": ", ".join(q.missing_data) if q.missing_data else None,
        "evidence_urls": "\n".join(q.evidence_urls) if q.evidence_urls else None,
    }


def _split(results: List[LeadResult]):
    main, rejected = [], []
    for r in results:
        (rejected if r.qualification.status == "Reject" else main).append(to_record(r))
    return main, rejected


def _sync_local(main, rejected) -> Dict:
    def upsert_file(path: pathlib.Path, rows):
        existing = {}
        if path.exists():
            for rec in json.loads(path.read_text()):
                existing[rec["record_id"]] = rec
        for rec in rows:  # dedupe by record_id
            existing[rec["record_id"]] = rec
        path.write_text(json.dumps(list(existing.values()), indent=2))

    upsert_file(_DATA / "airtable_main.json", main)
    upsert_file(_DATA / "airtable_rejected.json", rejected)
    return {"mode": "local-mock", "main": len(main), "rejected": len(rejected)}


def _sync_airtable(main, rejected) -> Dict:
    from pyairtable import Api

    api = Api(os.environ["AIRTABLE_TOKEN"])
    base = os.environ["AIRTABLE_BASE_ID"]
    for table_name, rows in ((MAIN_TABLE, main), (REJECTED_TABLE, rejected)):
        if not rows:
            continue
        table = api.table(base, table_name)
        table.batch_upsert(
            [{"fields": r} for r in rows],
            key_fields=["record_id"],
        )
    return {"mode": "airtable", "main": len(main), "rejected": len(rejected)}


def sync(results: List[LeadResult]) -> Dict:
    main, rejected = _split(results)
    if os.getenv("AIRTABLE_TOKEN") and os.getenv("AIRTABLE_BASE_ID"):
        try:
            return _sync_airtable(main, rejected)
        except Exception as e:  # noqa: BLE001 — never lose results to an Airtable hiccup
            print(f"[airtable] live sync failed ({e}); writing local mock instead")
    return _sync_local(main, rejected)
