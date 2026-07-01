"""Orchestrates one lead through enrich → qualify. Cleaning is done in batch
(app.clean) since it reads the whole file at once."""

from __future__ import annotations

from app.enrich import enrich
from app.qualify import qualify
from app.schema import CleanLead, LeadResult


def process_lead(lead: CleanLead) -> LeadResult:
    enrichment = enrich(lead)
    qualification = qualify(lead, enrichment)
    return LeadResult(clean=lead, enrichment=enrichment, qualification=qualification)
