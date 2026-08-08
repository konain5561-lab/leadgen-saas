# Google Maps Lead-Gen SaaS -- Full Project

A complete pipeline: scrape businesses from Google Maps → store in a
database → AI scores which ones need marketing help → chat with an AI
about your leads → AI drafts personalized email/WhatsApp outreach.

Uses **Ollama** (free, open-source, runs locally) as the LLM -- no API
key, no per-request cost, no signup.

```
leadgen-saas/
├── scraper/
│   ├── scraper.py          # scrapes Google Maps -> leads.json/leads.csv
│   ├── enrich.py           # finds contact emails from each business's website
│   └── requirements.txt
└── backend/
    ├── main.py              # FastAPI app -- all endpoints
    ├── models.py             # SQLAlchemy ORM models
    ├── schemas.py             # Pydantic request/response schemas
    ├── database.py            # DB engine/session (SQLite dev / Postgres prod)
    ├── schema.sql              # reference Postgres DDL
    ├── requirements.txt
    └── ai/
        ├── llm_client.py       # Ollama wrapper (free local LLM)
        ├── scoring.py           # lead scoring: rules + LLM reasoning
        ├── chat.py               # chatbot grounded in your leads data
        └── outreach.py            # email/WhatsApp draft generator
```

## 1. Install Ollama (the free AI engine)

```bash
# https://ollama.com/download -- available for Mac/Windows/Linux
ollama pull llama3.1        # ~4.7GB, one-time download
ollama serve                 # usually auto-starts as a background service
```

That's the entire AI setup. No API key, no billing.

## 2. Set up the scraper

```bash
cd scraper
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 3. Set up the backend

```bash
cd ../backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Runs on `http://localhost:8000`. Interactive docs at `/docs`.

By default it uses a local SQLite file. For production, set
`DATABASE_URL` to a Postgres connection string (see `database.py`).

## One-click start / stop (no typing required)

PowerShell scripts are provided so you can start and stop the backend by
**double-clicking** instead of running `uvicorn` by hand. They live in the
project root alongside this file:

| Double-click | What it does |
|---|---|
| **`start-server.cmd`** | Starts the backend on `http://localhost:8000` in the background (`--reload`), saves its PID to `backend\.server.pid`, waits until it's live, then opens the dashboard in your browser. If it's already running, it just opens the browser (no duplicate server). |
| **`stop-server.cmd`** | Stops the running backend (kills the whole reloader + worker process tree) and confirms port 8000 is free. |

The `.cmd` files are **double-click launchers** — they call the underlying
`.ps1` scripts (`start-server.ps1` / `stop-server.ps1`) with
`-ExecutionPolicy Bypass`, so they work even when PowerShell's script
execution policy is restricted. (If you double-click a `.ps1` directly it
opens in Notepad; use the `.cmd` versions.)

Notes:
- Startup/shutdown messages show in a small console window that stays open.
- Logs are written to `backend\uvicorn.log` and `backend\uvicorn.err.log`.
- You can also run the scripts from a terminal: `.\start-server.ps1` /
  `.\stop-server.ps1`.


## Full workflow

```bash
# 1. Kick off a scrape (runs scraper.py as a background job, loads results into the DB)
curl -X POST http://localhost:8000/search-jobs \
  -H "Content-Type: application/json" \
  -d '{"query": "dentists in Karachi", "limit": 30}'
# -> {"id": 1, "status": "pending", ...}

# 2. Check job status until it's "completed"
curl http://localhost:8000/search-jobs/1

# 3. Score all the new leads (AI decides who needs marketing help)
curl -X POST http://localhost:8000/leads/score-all

# 4. List leads sorted by lead score, best prospects first
curl "http://localhost:8000/leads?sort_by=lead_score&sort_dir=desc"

# 5. Ask the chatbot about your leads
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"content": "Which 3 leads need the most help and why?"}'

# 6. Generate an outreach draft for a specific lead
curl -X POST "http://localhost:8000/leads/5/generate-outreach?channel=email"
```

## Endpoint reference

| Method | Path | Description |
|---|---|---|
| POST | `/search-jobs` | Start a Maps scrape |
| GET | `/search-jobs/{id}` | Check scrape job status |
| GET | `/leads` | List/filter/sort leads |
| GET | `/leads/{id}` | Single lead |
| PATCH | `/leads/{id}` | Update status/notes |
| POST | `/leads/{id}/score` | AI-score a single lead |
| POST | `/leads/score-all` | AI-score every unscored lead (background) |
| POST | `/leads/{id}/generate-outreach?channel=email\|whatsapp` | AI drafts a message, saves it |
| POST | `/leads/{id}/outreach` | Manually save an outreach draft |
| GET | `/leads/{id}/outreach` | List a lead's outreach history |
| POST | `/chat` | Ask the AI about your leads (multi-turn, grounded in DB) |

## Design notes

- **Every AI feature has a deterministic fallback.** If Ollama isn't
  running, scoring falls back to rule-based signals (low rating, few
  reviews, no website), outreach falls back to a fill-in-the-blank
  template, and chat returns a clear "AI unavailable" message instead
  of crashing. This was verified by testing with Ollama offline as
  well as with mocked Ollama responses.
- **Lead scoring** combines cheap rule-based signals with an LLM's
  judgment call, and always returns a `reason` string so you can see
  *why* a lead scored the way it did -- not just a number.
- **Chat is grounded, not hallucinated.** Each chat turn passes the
  current top leads (name, rating, reviews, score) into the prompt, so
  the model answers from your actual scraped data.
- **Outreach compliance is on you.** The generator drafts pitch
  content; you still need sender identification and opt-out handling
  to comply with CAN-SPAM/GDPR-style rules before sending at scale.

## Known limitations (be aware before relying on this in production)

- Google Maps scraping breaks Google's ToS and its selectors drift
  over time -- see `scraper/README.md` (in the scraper output from
  the earlier step) for details and maintenance tips.
- Sending outreach (actually dispatching email/WhatsApp) isn't wired
  up yet -- this project generates and stores drafts; hooking up SMTP
  or the WhatsApp Business API is a separate step.
- The chat context strategy (dumping up to 100 leads into the prompt)
  works fine at small-to-medium scale; past a few hundred leads you'd
  want real vector search (e.g. Chroma/Qdrant) instead.
