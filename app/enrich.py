"""Stage 2 — enrich each company with real web research.

Two steps, on purpose: (1) a live web search gathers facts + the source URLs it
cited, then (2) a separate structuring pass maps those notes into our schema.
Keeping research and structuring apart means evidence URLs are real citations,
not model-invented, and we never fabricate an email/LinkedIn that wasn't found."""

from __future__ import annotations

import json
import os
from typing import List, Tuple

from openai import OpenAI

from app.schema import CleanLead, Enrichment

_client = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


SEARCH_MODEL = os.getenv("OPENAI_SEARCH_MODEL", "gpt-4o")
STRUCT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")


def _research(lead: CleanLead) -> Tuple[str, List[str]]:
    where = ", ".join(filter(None, [lead.city, lead.state]))
    prompt = (
        f"Research the company \"{lead.company_name}\" ({where}). Find and report, with sources:\n"
        f"- official company website\n- owner / founder / president / CEO name and title\n"
        f"- a decision-maker email only if it is publicly listed\n"
        f"- the company LinkedIn page URL\n- the owner/executive LinkedIn profile URL if available\n"
        f"- services offered\n- whether the address/location checks out\n"
        f"- ownership: is it private / family-owned?\n"
        f"- RED FLAGS: is it publicly traded, a franchise, or private-equity (PE) backed?\n"
        f"Be precise and cite your sources."
    )
    r = client().responses.create(
        model=SEARCH_MODEL,
        tools=[{"type": "web_search_preview"}],
        input=prompt,
    )
    urls: List[str] = []
    for item in getattr(r, "output", []) or []:
        for block in getattr(item, "content", []) or []:
            for ann in getattr(block, "annotations", []) or []:
                u = getattr(ann, "url", None)
                if u and u not in urls:
                    urls.append(u)
    return (r.output_text or ""), urls


_STRUCT_SYS = (
    "You convert research notes into a strict JSON object. Never invent facts. "
    "If a field is not clearly supported by the notes, use null (or [] for arrays). "
    "Do NOT fabricate emails or LinkedIn URLs — include them only if present in the notes."
)


def _structure(lead: CleanLead, notes: str, urls: List[str]) -> Enrichment:
    instr = (
        f"Company: {lead.company_name} ({lead.city}, {lead.state}). "
        f"Data Axle flags — public/private: {lead.public_private_flag}, franchise: {lead.franchise_flag}.\n\n"
        f"Research notes:\n{notes}\n\n"
        "Return JSON with keys: website, owner_name, owner_title, decision_maker_email, "
        "company_linkedin, owner_linkedin, services, location_verified (true/false/null), "
        "ownership_signal (short phrase e.g. 'private / family-owned', 'publicly traded', 'franchise'), "
        "is_public (bool), is_franchise (bool), is_pe_backed (bool).\n"
        "For the three booleans: default to FALSE. Set true ONLY if the notes explicitly support it "
        "(is_public = listed on a stock exchange / has a ticker; is_franchise = it is a franchise; "
        "is_pe_backed = a named private-equity firm owns or backs it). Most small private businesses are "
        "NOT public and NOT PE-backed — do not guess."
    )
    resp = client().chat.completions.create(
        model=STRUCT_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": _STRUCT_SYS}, {"role": "user", "content": instr}],
    )
    data = json.loads(resp.choices[0].message.content)
    data["evidence_urls"] = urls[:8]  # real citations from the search step

    # Red flags must be reliable, not echoed enum options. Seed from the Data Axle
    # structured flags (ground truth for public/franchise) and only accept a
    # PE-backed flag from the model when its notes actually support it.
    flags = set()
    axle_public = (lead.public_private_flag or "").strip().lower().startswith("public")
    axle_franchise = (lead.franchise_flag or "").strip().lower() in ("yes", "y", "true")
    if axle_public or data.get("is_public") is True:
        flags.add("publicly traded")
    if axle_franchise or data.get("is_franchise") is True:
        flags.add("franchise")
    if data.get("is_pe_backed") is True:
        flags.add("PE-backed")
    data["red_flags"] = sorted(flags)

    allowed = set(Enrichment.model_fields.keys())
    return Enrichment(**{k: v for k, v in data.items() if k in allowed})


def enrich(lead: CleanLead) -> Enrichment:
    notes, urls = _research(lead)
    return _structure(lead, notes, urls)
