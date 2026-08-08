-- ============================================================
-- SCHEMA: Google Maps Lead-Gen SaaS
-- Target: PostgreSQL 14+
-- ============================================================

CREATE TYPE lead_status AS ENUM (
    'new',          -- just scraped, not yet reviewed
    'qualified',     -- AI/human marked as a good prospect
    'contacted',     -- outreach message sent
    'replied',       -- business responded
    'won',           -- became a client
    'lost',          -- not interested / dead end
    'ignored'        -- manually excluded
);

CREATE TYPE outreach_channel AS ENUM ('email', 'whatsapp');
CREATE TYPE outreach_status AS ENUM ('draft', 'sent', 'failed');
CREATE TYPE search_job_status AS ENUM ('pending', 'running', 'completed', 'failed');

-- ------------------------------------------------------------
-- search_jobs: one row per scrape run (e.g. "dentists in Karachi")
-- ------------------------------------------------------------
CREATE TABLE search_jobs (
    id              BIGSERIAL PRIMARY KEY,
    query           TEXT NOT NULL,
    result_limit    INTEGER NOT NULL DEFAULT 20,
    status          search_job_status NOT NULL DEFAULT 'pending',
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_by      BIGINT  -- plug in a FK to your users/auth table once that exists
);

-- ------------------------------------------------------------
-- businesses: the actual leads. One row per scraped business.
-- De-duplicated on (name, address) so re-running the same search
-- area doesn't create duplicate leads.
-- ------------------------------------------------------------
CREATE TABLE businesses (
    id                  BIGSERIAL PRIMARY KEY,
    search_job_id       BIGINT REFERENCES search_jobs(id) ON DELETE SET NULL,

    name                TEXT NOT NULL,
    category            TEXT,
    rating              NUMERIC(2,1),          -- e.g. 4.3
    review_count        INTEGER,
    address             TEXT,
    phone               TEXT,
    website             TEXT,
    email               TEXT,
    google_maps_url     TEXT,

    -- AI lead-scoring layer writes here (built in the next step)
    lead_score          SMALLINT,              -- 0-100
    lead_score_reason   TEXT,                  -- short AI explanation
    scored_at           TIMESTAMPTZ,

    status              lead_status NOT NULL DEFAULT 'new',
    notes               TEXT,                  -- freeform user notes

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (name, address)
);

CREATE INDEX idx_businesses_search_job ON businesses(search_job_id);
CREATE INDEX idx_businesses_status ON businesses(status);
CREATE INDEX idx_businesses_lead_score ON businesses(lead_score DESC);
CREATE INDEX idx_businesses_rating ON businesses(rating);

-- ------------------------------------------------------------
-- outreach_messages: AI-generated (or edited) email/WhatsApp drafts,
-- one row per message per business. Kept even after sending, as a log.
-- ------------------------------------------------------------
CREATE TABLE outreach_messages (
    id              BIGSERIAL PRIMARY KEY,
    business_id     BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,

    channel         outreach_channel NOT NULL,
    subject         TEXT,                       -- email only; null for whatsapp
    body            TEXT NOT NULL,
    status          outreach_status NOT NULL DEFAULT 'draft',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at         TIMESTAMPTZ
);

CREATE INDEX idx_outreach_business ON outreach_messages(business_id);

-- ------------------------------------------------------------
-- chat_messages: conversational history for the "ask the AI about
-- your leads" chatbot layer. One row per turn.
-- ------------------------------------------------------------
CREATE TABLE chat_sessions (
    id              BIGSERIAL PRIMARY KEY,
    title           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
    id              BIGSERIAL PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_messages_session ON chat_messages(session_id);

-- ------------------------------------------------------------
-- Keep updated_at fresh on businesses
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_businesses_updated_at
BEFORE UPDATE ON businesses
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
