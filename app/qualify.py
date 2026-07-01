"""Stage 3 — qualify each enriched lead for an acquisition / origination platform.

Target profile: privately held, owner/family-operated SMBs with an identifiable
decision-maker. Public companies, franchises, and PE-backed firms are red flags.
The model returns a status + scores + reasons + missing data + evidence — and is
told to choose 'Needs Review' (not guess) when key data is missing or ambiguous,
because accuracy and evidence matter more than volume."""

from __future__ import annotations

import json
import os

from openai import OpenAI

from app.enrich import client
from app.schema import CleanLead, Enrichment, Qualification

MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

_SYS = (
    "You are a lead qualification analyst for an acquisition/origination platform that buys "
    "privately held, owner-operated small-to-mid businesses (roughly $1M–$100M revenue).\n"
    "Classify each company as exactly one of: Pass, Needs Review, Reject. Decision rules:\n"
    "- REJECT if the 'red_flags' field contains any confirmed flag (publicly traded, franchise, or PE-backed).\n"
    "- REJECT on size ONLY if it is clearly an enterprise far outside SMB range (e.g. > $500M revenue "
    "or > 1500 employees) even when private.\n"
    "- PASS if it is privately / owner / family-owned, has an identifiable owner or decision-maker, and "
    "fits the SMB range. A few hundred employees and tens of millions in revenue is a normal target — do NOT reject for that.\n"
    "- NEEDS REVIEW if key data is missing (no owner or no contact), ownership is ambiguous "
    "(e.g. employee-owned / ESOP with no single owner), or it's a borderline very-large private firm.\n"
    "Trust the 'red_flags' field — do not invent new ones. Prefer 'Needs Review' over guessing. "
    "Evidence and accuracy matter more than volume. Output strict JSON only."
)


def qualify(lead: CleanLead, enr: Enrichment) -> Qualification:
    payload = {
        "company": lead.company_name,
        "location": f"{lead.city}, {lead.state}",
        "industry": lead.industry,
        "employees": lead.employees,
        "revenue": lead.revenue,
        "data_axle_flags": {"public_private": lead.public_private_flag, "franchise": lead.franchise_flag},
        "enrichment": enr.model_dump(),
    }
    instr = (
        "Qualify this lead. Return JSON with keys: "
        "status ('Pass'|'Needs Review'|'Reject'), fit_score (0-100), confidence (0-100), "
        "reasons (1-3 sentences), missing_data (array of field names that are missing/uncertain).\n\n"
        f"Lead:\n{json.dumps(payload, indent=2)}"
    )
    resp = client().chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": _SYS}, {"role": "user", "content": instr}],
    )
    data = json.loads(resp.choices[0].message.content)
    data["evidence_urls"] = enr.evidence_urls
    allowed = set(Qualification.model_fields.keys())
    out = {k: v for k, v in data.items() if k in allowed}
    # guard required fields
    out.setdefault("status", "Needs Review")
    out.setdefault("fit_score", 0)
    out.setdefault("confidence", 0)
    out.setdefault("reasons", "")
    return Qualification(**out)
