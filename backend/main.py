"""
FastAPI backend for the lead-gen SaaS.

Endpoints
---------
POST   /search-jobs              kick off a new Maps scrape (runs scraper.py as a subprocess)
GET    /search-jobs/{id}         check job status
GET    /leads                    list/filter/sort leads
GET    /leads/{id}               single lead
PATCH  /leads/{id}                update status/notes
POST   /leads/{id}/outreach       save a (usually AI-drafted) outreach message  [stub -- generation built in next step]
GET    /leads/{id}/outreach       list outreach messages for a lead
POST   /chat                      chat turn against the leads dataset          [stub -- AI wiring built in next step]

Run:
    uvicorn main:app --reload
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

import models
import schemas
from database import SessionLocal, engine, get_db
from ai import scoring, chat as ai_chat, outreach as ai_outreach

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Lead-Gen SaaS API")

# Allow the dashboard to be served from any origin (e.g. opening index.html
# directly, or behind a different host/port), while keeping it simple to run.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Paths to the scraper / enrichment scripts built in earlier steps.
# Playwright (and thus Chromium driver code) is installed in the scraper's own
# virtualenv, NOT in this backend venv, so we must run those subprocesses with
# the scraper venv's Python interpreter. Fall back to this process's interpreter
# if that venv isn't found (e.g. running a different layout).
SCRAPER_DIR = Path(__file__).parent.parent / "scraper"
SCRAPER_SCRIPT = SCRAPER_DIR / "scraper.py"
SCRAPER_ENRICH_SCRIPT = SCRAPER_DIR / "enrich.py"
_scraper_venv_py = SCRAPER_DIR / "venv" / "Scripts" / "python.exe"
SCRAPER_PYTHON = str(_scraper_venv_py) if _scraper_venv_py.exists() else sys.executable

SCRAPE_OUTPUT_DIR = Path(__file__).parent / "scrape_output"
SCRAPE_OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------
# Search jobs -- triggers the scraper and loads results into the DB
# ---------------------------------------------------------------

def _run_scrape_job(job_id: int, query: str, limit: int):
    """Background task: run scraper.py, then upsert results into `businesses`."""
    db: Session = SessionLocal()
    job = db.get(models.SearchJob, job_id)
    job.status = models.SearchJobStatus.running
    job.started_at = datetime.now(timezone.utc)
    db.commit()

    out_prefix = str(SCRAPE_OUTPUT_DIR / f"job_{job_id}")
    try:
        result = subprocess.run(
            [SCRAPER_PYTHON, str(SCRAPER_SCRIPT), query, "--limit", str(limit), "--out", out_prefix],
            capture_output=True, text=True, timeout=1800,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-2000:])

        records = json.loads(Path(f"{out_prefix}.json").read_text(encoding="utf-8"))

        # ---- Email auto-enrichment ---------------------------------------
        # enrich.py visits each business's own website and pulls a contact
        # email (Google Maps itself doesn't expose emails). Best-effort: if
        # enrichment fails/stalls, we keep the raw scraped records (emails
        # simply stay blank) rather than failing the whole scrape.
        try:
            enriched_prefix = f"{out_prefix}_enriched"
            enrich_res = subprocess.run(
                [SCRAPER_PYTHON, str(SCRAPER_ENRICH_SCRIPT), f"{out_prefix}.json", "--out", enriched_prefix],
                capture_output=True, text=True, timeout=1800,
            )
            if enrich_res.returncode == 0:
                enriched_path = Path(f"{enriched_prefix}.json")
                if enriched_path.exists():
                    enriched = json.loads(enriched_path.read_text(encoding="utf-8"))
                    if enriched:
                        records = enriched
        except Exception:
            pass  # keep raw records; emails will be blank

        # ---- Upsert into `businesses` ------------------------------------
        job_businesses: list[models.Business] = []
        for rec in records:
            existing = (
                db.query(models.Business)
                .filter_by(name=rec.get("name", ""), address=rec.get("address", ""))
                .first()
            )
            rating = rec.get("rating") or None
            review_count = rec.get("review_count") or None
            if existing:
                existing.search_job_id = job_id
                existing.category = rec.get("category") or existing.category
                existing.rating = rating or existing.rating
                existing.review_count = int(review_count) if review_count else existing.review_count
                existing.phone = rec.get("phone") or existing.phone
                existing.website = rec.get("website") or existing.website
                existing.email = rec.get("email") or existing.email
                existing.google_maps_url = rec.get("google_maps_url") or existing.google_maps_url
                job_businesses.append(existing)
            else:
                biz = models.Business(
                    search_job_id=job_id,
                    name=rec.get("name", "Unknown"),
                    category=rec.get("category"),
                    rating=rating,
                    review_count=int(review_count) if review_count else None,
                    address=rec.get("address"),
                    phone=rec.get("phone"),
                    website=rec.get("website"),
                    email=rec.get("email"),
                    google_maps_url=rec.get("google_maps_url"),
                )
                db.add(biz)
                job_businesses.append(biz)
        db.commit()

        # ---- Auto lead-scoring -------------------------------------------
        # Score every business this job added/updated that isn't scored yet,
        # so new leads are ranked and ready as soon as the job finishes. The
        # scorer never fails the job -- it falls back to rule-based signals
        # if Ollama (the local LLM) isn't reachable.
        for biz in job_businesses:
            db.refresh(biz)
            if biz.lead_score is None:
                score_result = scoring.score_business(_business_to_dict(biz))
                biz.lead_score = score_result["score"]
                biz.lead_score_reason = score_result["reason"]
                biz.scored_at = datetime.now(timezone.utc)
        db.commit()
        job.status = models.SearchJobStatus.completed
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        job.status = models.SearchJobStatus.failed
        job.error_message = str(e)[:2000]
        db.commit()
    finally:
        db.close()


@app.post("/search-jobs", response_model=schemas.SearchJobOut)
def create_search_job(payload: schemas.SearchJobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = models.SearchJob(query=payload.query, result_limit=payload.limit)
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_scrape_job, job.id, payload.query, payload.limit)
    return job


@app.get("/search-jobs/{job_id}", response_model=schemas.SearchJobOut)
def get_search_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(models.SearchJob, job_id)
    if not job:
        raise HTTPException(404, "Search job not found")
    return job


# ---------------------------------------------------------------
# Leads
# ---------------------------------------------------------------

SORTABLE_FIELDS = {
    "lead_score": models.Business.lead_score,
    "rating": models.Business.rating,
    "review_count": models.Business.review_count,
    "created_at": models.Business.created_at,
}


@app.get("/leads", response_model=list[schemas.BusinessOut])
def list_leads(
    search_job_id: int | None = None,
    status: models.LeadStatus | None = None,
    min_rating: float | None = None,
    max_rating: float | None = None,
    min_score: int | None = None,
    sort_by: str = Query("lead_score", pattern="^(lead_score|rating|review_count|created_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
):
    q = db.query(models.Business)
    if search_job_id is not None:
        q = q.filter(models.Business.search_job_id == search_job_id)
    if status is not None:
        q = q.filter(models.Business.status == status)
    if min_rating is not None:
        q = q.filter(models.Business.rating >= min_rating)
    if max_rating is not None:
        q = q.filter(models.Business.rating <= max_rating)
    if min_score is not None:
        q = q.filter(models.Business.lead_score >= min_score)

    order_col = SORTABLE_FIELDS[sort_by]
    q = q.order_by(desc(order_col) if sort_dir == "desc" else asc(order_col))

    q = q.offset((page - 1) * page_size).limit(page_size)
    return q.all()


@app.get("/leads/{lead_id}", response_model=schemas.BusinessOut)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    biz = db.get(models.Business, lead_id)
    if not biz:
        raise HTTPException(404, "Lead not found")
    return biz


@app.patch("/leads/{lead_id}", response_model=schemas.BusinessOut)
def update_lead(lead_id: int, payload: schemas.BusinessUpdate, db: Session = Depends(get_db)):
    biz = db.get(models.Business, lead_id)
    if not biz:
        raise HTTPException(404, "Lead not found")
    if payload.status is not None:
        biz.status = payload.status
    if payload.notes is not None:
        biz.notes = payload.notes
    db.commit()
    db.refresh(biz)
    return biz


# ---------------------------------------------------------------
# AI lead scoring -- rule-based signals + LLM reasoning (ai/scoring.py).
# Falls back to rule-only scoring automatically if Ollama isn't running.
# ---------------------------------------------------------------

def _business_to_dict(biz: models.Business) -> dict:
    return {
        "name": biz.name,
        "category": biz.category,
        "rating": float(biz.rating) if biz.rating is not None else None,
        "review_count": biz.review_count,
        "address": biz.address,
        "website": biz.website,
        "lead_score_reason": biz.lead_score_reason,
    }


@app.post("/leads/{lead_id}/score", response_model=schemas.BusinessOut)
def score_lead(lead_id: int, db: Session = Depends(get_db)):
    biz = db.get(models.Business, lead_id)
    if not biz:
        raise HTTPException(404, "Lead not found")

    result = scoring.score_business(_business_to_dict(biz))
    biz.lead_score = result["score"]
    biz.lead_score_reason = result["reason"]
    biz.scored_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(biz)
    return biz


def _score_all_unscored():
    db: Session = SessionLocal()
    try:
        unscored = db.query(models.Business).filter(models.Business.lead_score.is_(None)).all()
        for biz in unscored:
            result = scoring.score_business(_business_to_dict(biz))
            biz.lead_score = result["score"]
            biz.lead_score_reason = result["reason"]
            biz.scored_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


@app.post("/leads/score-all")
def score_all_leads(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Scores every not-yet-scored lead in the background (can be slow -- one LLM call per lead)."""
    count = db.query(models.Business).filter(models.Business.lead_score.is_(None)).count()
    background_tasks.add_task(_score_all_unscored)
    return {"queued": count}


# ---------------------------------------------------------------
# Outreach -- storage only for now. AI generation gets wired in
# as its own step; this endpoint just persists whatever draft is
# passed in (human-written or, later, model-generated).
# ---------------------------------------------------------------

# ---------------------------------------------------------------
# Outreach -- AI-generated drafts (ai/outreach.py), stored as
# OutreachMessage rows. Falls back to a template if Ollama is offline.
# ---------------------------------------------------------------

@app.post("/leads/{lead_id}/generate-outreach", response_model=schemas.OutreachMessageOut)
def generate_outreach_message(lead_id: int, channel: models.OutreachChannel, db: Session = Depends(get_db)):
    biz = db.get(models.Business, lead_id)
    if not biz:
        raise HTTPException(404, "Lead not found")

    result = ai_outreach.generate_outreach(_business_to_dict(biz), channel.value)
    msg = models.OutreachMessage(
        business_id=lead_id, channel=channel,
        subject=result["subject"], body=result["body"],
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


@app.post("/leads/{lead_id}/outreach", response_model=schemas.OutreachMessageOut)
def create_outreach_message(lead_id: int, payload: schemas.OutreachMessageCreate, db: Session = Depends(get_db)):
    biz = db.get(models.Business, lead_id)
    if not biz:
        raise HTTPException(404, "Lead not found")
    msg = models.OutreachMessage(
        business_id=lead_id, channel=payload.channel,
        subject=payload.subject, body=payload.body,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


@app.get("/leads/{lead_id}/outreach", response_model=list[schemas.OutreachMessageOut])
def list_outreach_messages(lead_id: int, db: Session = Depends(get_db)):
    return db.query(models.OutreachMessage).filter_by(business_id=lead_id).order_by(models.OutreachMessage.created_at.desc()).all()


# ---------------------------------------------------------------
# Chat -- stub. Wiring this to an actual LLM (Ollama/local model)
# over the leads table is the next build step.
# ---------------------------------------------------------------

@app.post("/chat", response_model=schemas.ChatMessageOut)
def chat_turn(payload: schemas.ChatMessageCreate, db: Session = Depends(get_db)):
    if payload.session_id:
        session = db.get(models.ChatSession, payload.session_id)
        if not session:
            raise HTTPException(404, "Chat session not found")
    else:
        session = models.ChatSession(title=payload.content[:60])
        db.add(session)
        db.commit()
        db.refresh(session)

    user_msg = models.ChatMessage(session_id=session.id, role="user", content=payload.content)
    db.add(user_msg)
    db.commit()

    # Build conversation history for this session (excluding the message we just added)
    prior_turns = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session.id, models.ChatMessage.id != user_msg.id)
        .order_by(models.ChatMessage.created_at)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in prior_turns]

    # Ground the answer in the current leads, best-scored first
    leads = (
        db.query(models.Business)
        .order_by(desc(models.Business.lead_score))
        .limit(100)
        .all()
    )
    leads_dicts = [
        {
            "name": b.name, "category": b.category,
            "rating": float(b.rating) if b.rating is not None else None,
            "review_count": b.review_count, "website": b.website,
            "lead_score": b.lead_score, "status": b.status.value if b.status else None,
        }
        for b in leads
    ]

    reply_text = ai_chat.answer(payload.content, history, leads_dicts)

    assistant_msg = models.ChatMessage(session_id=session.id, role="assistant", content=reply_text)
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return assistant_msg


# ---------------------------------------------------------------
# Frontend dashboard -- serve static files at the site root.
# Mounted LAST so the API/docs routes registered above take priority
# and this only picks up requests that match no other route.
# ---------------------------------------------------------------
FRONTEND_DIR = Path(__file__).parent / "frontend"
FRONTEND_DIR.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

