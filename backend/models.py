"""SQLAlchemy ORM models -- mirrors schema.sql."""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, Column, DateTime, Enum, ForeignKey, Integer,
    Numeric, SmallInteger, String, Text, UniqueConstraint, func
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# SQLite's rowid-based autoincrement only kicks in for a plain INTEGER
# primary key -- a BigInteger PK is NOT treated as an alias for rowid,
# so inserts fail with "NOT NULL constraint failed" unless we tell
# SQLAlchemy to use plain Integer specifically on the sqlite dialect.
# On Postgres this still generates a real bigint/bigserial column.
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class LeadStatus(str, enum.Enum):
    new = "new"
    qualified = "qualified"
    contacted = "contacted"
    replied = "replied"
    won = "won"
    lost = "lost"
    ignored = "ignored"


class OutreachChannel(str, enum.Enum):
    email = "email"
    whatsapp = "whatsapp"


class OutreachStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    failed = "failed"


class SearchJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class SearchJob(Base):
    __tablename__ = "search_jobs"

    id = Column(BigIntPK, primary_key=True)
    query = Column(Text, nullable=False)
    result_limit = Column(Integer, nullable=False, default=20)
    status = Column(Enum(SearchJobStatus), nullable=False, default=SearchJobStatus.pending)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_by = Column(BigInteger)

    businesses = relationship("Business", back_populates="search_job")


class Business(Base):
    __tablename__ = "businesses"
    __table_args__ = (UniqueConstraint("name", "address", name="uq_business_name_address"),)

    id = Column(BigIntPK, primary_key=True)
    search_job_id = Column(BigInteger, ForeignKey("search_jobs.id", ondelete="SET NULL"))

    name = Column(Text, nullable=False)
    category = Column(Text)
    rating = Column(Numeric(2, 1))
    review_count = Column(Integer)
    address = Column(Text)
    phone = Column(Text)
    website = Column(Text)
    email = Column(Text)
    google_maps_url = Column(Text)

    lead_score = Column(SmallInteger)
    lead_score_reason = Column(Text)
    scored_at = Column(DateTime(timezone=True))

    status = Column(Enum(LeadStatus), nullable=False, default=LeadStatus.new)
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    search_job = relationship("SearchJob", back_populates="businesses")
    outreach_messages = relationship("OutreachMessage", back_populates="business", cascade="all, delete-orphan")


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"

    id = Column(BigIntPK, primary_key=True)
    business_id = Column(BigInteger, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)

    channel = Column(Enum(OutreachChannel), nullable=False)
    subject = Column(Text)
    body = Column(Text, nullable=False)
    status = Column(Enum(OutreachStatus), nullable=False, default=OutreachStatus.draft)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True))

    business = relationship("Business", back_populates="outreach_messages")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(BigIntPK, primary_key=True)
    title = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(BigIntPK, primary_key=True)
    session_id = Column(BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")
