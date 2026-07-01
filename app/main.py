from __future__ import annotations

import json
import pathlib

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

load_dotenv()

app = FastAPI(title="Lead Enrichment & Qualification")
_TEMPLATES = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES))
DATA = pathlib.Path(__file__).parent.parent / "data"


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    path = DATA / "results.json"
    results = json.loads(path.read_text()) if path.exists() else []
    counts = {"Pass": 0, "Needs Review": 0, "Reject": 0}
    for r in results:
        s = r["qualification"]["status"]
        counts[s] = counts.get(s, 0) + 1
    return templates.TemplateResponse(
        request,
        "index.html",
        {"results": results, "counts": counts, "total": len(results)},
    )
