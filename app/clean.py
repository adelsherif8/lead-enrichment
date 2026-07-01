"""Stage 1 — turn a raw Data Axle Excel/CSV export into clean, standardized leads.

Real exports carry 25+ columns (census tract, lat/long, carrier route, credit
codes…) that are noise for outreach. We keep only the useful fields and coerce
types, dropping the rest."""

from __future__ import annotations

import math
from typing import List

import pandas as pd

from app.schema import CleanLead

# Map messy source columns → our standardized field. Add aliases as needed.
COLUMN_MAP = {
    "record_id": "record_id",
    "company_name": "company_name",
    "address": "address",
    "city": "city",
    "state": "state",
    "zip": "zip",
    "phone": "phone",
    "website": "website",
    "sic_description": "industry",
    "employee_size": "employees",
    "sales_volume": "revenue",
    "year_established": "year_established",
    "public_private_flag": "public_private_flag",
    "franchise_flag": "franchise_flag",
}


def _clean_val(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    return s or None


def _to_int(v):
    s = _clean_val(v)
    if s is None:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def load_clean_leads(path: str) -> List[CleanLead]:
    df = pd.read_excel(path) if path.lower().endswith((".xlsx", ".xls")) else pd.read_csv(path)

    leads: List[CleanLead] = []
    for _, row in df.iterrows():
        data = {}
        for src, dst in COLUMN_MAP.items():
            if src not in row:
                continue
            if dst in ("employees", "revenue", "year_established"):
                data[dst] = _to_int(row[src])
            else:
                data[dst] = _clean_val(row[src])
        # Normalize a phone to digits for consistency.
        if data.get("phone"):
            digits = "".join(ch for ch in data["phone"] if ch.isdigit())
            data["phone"] = digits or None
        leads.append(CleanLead(**data))
    return leads
