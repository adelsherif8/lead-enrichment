from __future__ import annotations

import asyncio
import glob
import json
import os
import pathlib
import tempfile
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

load_dotenv()

from app.clean import load_clean_leads  # noqa: E402
from app.pipeline import process_lead  # noqa: E402

app = FastAPI(title="Lead Enrichment & Qualification")
_TEMPLATES = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES))
DATA = pathlib.Path(__file__).parent.parent / "data"

# In-memory job → uploaded-file path (fine for a single-process demo).
JOBS: dict[str, str] = {}
# Cap batch size when set (used on the hosted demo to stay within timeouts).
MAX_COMPANIES = int(os.getenv("MAX_COMPANIES", "0")) or None


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/sample-data")
def sample_data():
    """Pre-computed results of a real run — used to replay the sample instantly
    (reliable everywhere, incl. the hosted demo)."""
    path = DATA / "results.json"
    return JSONResponse(json.loads(path.read_text()) if path.exists() else [])


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower() or ".csv"
    job = uuid.uuid4().hex
    path = os.path.join(tempfile.gettempdir(), f"lead_{job}{ext}")
    with open(path, "wb") as f:
        f.write(await file.read())
    try:
        leads = load_clean_leads(path)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Could not read file: {e}"}, status_code=400)
    JOBS[job] = path
    return {"job": job, "count": len(leads), "companies": [l.company_name for l in leads]}


def _resolve(job: str):
    path = JOBS.get(job)
    if not path or not os.path.exists(path):
        hits = glob.glob(os.path.join(tempfile.gettempdir(), f"lead_{job}*"))
        path = hits[0] if hits else None
    return path


@app.get("/stream/{job}")
async def stream(job: str):
    path = _resolve(job)

    async def gen():
        if not path:
            yield f"event: error\ndata: {json.dumps({'error': 'upload expired — please re-upload'})}\n\n"
            return
        leads = load_clean_leads(path)
        if MAX_COMPANIES:
            leads = leads[:MAX_COMPANIES]
        total = len(leads)
        yield f"event: start\ndata: {json.dumps({'total': total, 'companies': [l.company_name for l in leads]})}\n\n"

        results = []
        for i, lead in enumerate(leads, 1):
            try:
                res = await asyncio.to_thread(process_lead, lead)
                results.append(res)
                payload = {"i": i, "total": total, "result": res.model_dump()}
            except Exception as e:  # noqa: BLE001
                payload = {"i": i, "total": total, "error": str(e), "company": lead.company_name}
            yield f"data: {json.dumps(payload)}\n\n"

        summary = {}
        try:
            from app.airtable import sync

            summary = sync(results)
        except Exception:  # noqa: BLE001
            pass
        yield f"event: done\ndata: {json.dumps({'summary': summary})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
