from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

_STR_FIELDS = (
    "website", "owner_name", "owner_title", "decision_maker_email",
    "company_linkedin", "owner_linkedin", "services", "ownership_signal",
)


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    return v


def _as_str(v):
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) or None
    return v


class CleanLead(BaseModel):
    """Standardized fields extracted from the raw Data Axle export."""

    record_id: str
    company_name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    employees: Optional[int] = None
    revenue: Optional[int] = None
    year_established: Optional[int] = None
    public_private_flag: Optional[str] = None
    franchise_flag: Optional[str] = None


class Enrichment(BaseModel):
    website: Optional[str] = None
    owner_name: Optional[str] = None
    owner_title: Optional[str] = None
    decision_maker_email: Optional[str] = None
    company_linkedin: Optional[str] = None
    owner_linkedin: Optional[str] = None
    services: Optional[str] = None
    location_verified: Optional[bool] = None
    ownership_signal: Optional[str] = None  # e.g. "private / family-owned"
    red_flags: List[str] = Field(default_factory=list)  # public, franchise, PE-backed
    evidence_urls: List[str] = Field(default_factory=list)

    _v_red = field_validator("red_flags", mode="before")(_as_list)
    _v_ev = field_validator("evidence_urls", mode="before")(_as_list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_str_fields(cls, data):
        if isinstance(data, dict):
            for k in _STR_FIELDS:
                data[k] = _as_str(data.get(k))
        return data


class Qualification(BaseModel):
    status: str  # "Pass" | "Needs Review" | "Reject"
    fit_score: int  # 0-100
    confidence: int  # 0-100
    reasons: str
    missing_data: List[str] = Field(default_factory=list)
    evidence_urls: List[str] = Field(default_factory=list)

    _v_md = field_validator("missing_data", mode="before")(_as_list)
    _v_ev = field_validator("evidence_urls", mode="before")(_as_list)


class LeadResult(BaseModel):
    clean: CleanLead
    enrichment: Enrichment
    qualification: Qualification
