"""Pydantic schemas -- request/response shapes for the API."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

from models import LeadStatus, OutreachChannel, OutreachStatus, SearchJobStatus


# ---------- Search jobs ----------

class SearchJobCreate(BaseModel):
    query: str
    limit: int = 20


class SearchJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    result_limit: int
    status: SearchJobStatus
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ---------- Businesses / leads ----------

class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    search_job_id: Optional[int] = None
    name: str
    category: Optional[str] = None
    rating: Optional[Decimal] = None
    review_count: Optional[int] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    google_maps_url: Optional[str] = None
    lead_score: Optional[int] = None
    lead_score_reason: Optional[str] = None
    status: LeadStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BusinessUpdate(BaseModel):
    status: Optional[LeadStatus] = None
    notes: Optional[str] = None


class BusinessListParams(BaseModel):
    """Query params for GET /leads -- documented here, parsed as query params in main.py."""
    search_job_id: Optional[int] = None
    status: Optional[LeadStatus] = None
    min_rating: Optional[float] = None
    max_rating: Optional[float] = None
    min_score: Optional[int] = None
    sort_by: str = "lead_score"   # lead_score | rating | review_count | created_at
    sort_dir: str = "desc"        # asc | desc
    page: int = 1
    page_size: int = 25


# ---------- Outreach ----------

class OutreachMessageCreate(BaseModel):
    channel: OutreachChannel
    subject: Optional[str] = None
    body: str


class OutreachMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    channel: OutreachChannel
    subject: Optional[str] = None
    body: str
    status: OutreachStatus
    created_at: datetime
    sent_at: Optional[datetime] = None


# ---------- Chat ----------

class ChatMessageCreate(BaseModel):
    session_id: Optional[int] = None  # omit to start a new session
    content: str


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: str
    content: str
    created_at: datetime
