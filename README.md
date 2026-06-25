# JobRadar

Self-hosted job monitoring pipeline that scrapes multiple job boards, uses RAG-powered semantic matching against your resume, and sends a Gmail digest for jobs scoring ≥80% relevancy. Runs indefinitely in a Docker container.

## How It Works

**Two-stage AI pipeline:**

1. **Stage 1 — Semantic Filter**: Embeds each job description and queries your resume chunks in ChromaDB via cosine similarity. Fast, cheap, no LLM cost. Jobs below the threshold are skipped.
2. **Stage 2 — LLM Scoring**: Retrieves the top-3 most relevant resume chunks and sends them to Gemini Flash with the job description. Returns a structured score (0–100) plus matching skills, missing skills, seniority classification, location check, and salary check.

Jobs scoring ≥80 that pass all hard gates (seniority, location, salary, visa) get emailed in a digest.

## Sources

| Source | Type | Notes |
|---|---|---|
| WeWorkRemotely | RSS | Remote tech jobs |
| RemoteOK | JSON API | Remote-only board |
| Remote.co | RSS | Remote jobs |
| Remotive | REST API | Remote jobs with category filter |
| WorkAtAStartup | Web scrape | YC startup jobs |
| Indeed (via JobSpy) | Scraper | On-site + remote in your city |

## Tech Stack

| Library | Purpose |
|---|---|
| `google-genai` | Gemini 2.5 Flash (scoring) + gemini-embedding-001 (embeddings) |
| `groq` | Optional Groq fallback (llama-3.3-70b-versatile) when Gemini rate-limits |
| `chromadb` | Local vector DB for resume chunks |
| `python-jobspy` | Scrapes Indeed without an API key |
| `feedparser` | WeWorkRemotely + Remote.co RSS feeds |
| `pydantic` | Structured AI output schemas |
| `apscheduler` | Blocking scheduler (keeps Docker container alive) |
| `sqlite3` | Job deduplication and score persistence |
| `smtplib` | Gmail SMTP digest |

## Setup

### 1. Prerequisites

- Docker + Docker Compose
- [Gemini API key](https://aistudio.google.com/apikey) (free tier: 15 RPM, 1M tokens/day — sufficient)
- Gmail App Password (Google Account → Security → 2-Step Verification → App passwords)
- *(Optional)* [Groq API key](https://console.groq.com) for rate-limit fallback

### 2. Clone and configure

```bash
git clone https://github.com/abdulah-x/JobRadar.git
cd JobRadar

# Create your config from the example template
cp config.example.yaml config.yaml
```

Edit `config.yaml`:
- Set your `gemini_api_key`
- Set your `groq_api_key` (optional but recommended)
- Set `email.sender`, `email.app_password`, `email.recipient`
- Adjust `filters.keywords`, `filters.locations`, `filters.seniority_allowed` for your situation
- Set `github.username` to index your public repos (optional)

### 3. Add your resume

```bash
# Add your resume as plain text — the AI uses this to score jobs
cp /path/to/your/resume.txt resume.txt
```

The resume is chunked by section (SKILLS, EXPERIENCE, EDUCATION, etc.) and embedded into ChromaDB on first run. If you update `resume.txt`, the index rebuilds automatically on the next run.

### 4. Run

```bash
docker compose up           # foreground — watch logs
docker compose up -d        # background — runs forever
docker logs -f job-radar    # follow logs when running in background
```

On first run you'll see the resume indexing complete, then the pipeline fires immediately. Subsequent runs follow the schedule in `config.yaml` (default: remote boards every 30 min, Indeed every 3 hrs).

## Configuration Reference

```yaml
schedule:
  remote_minutes: 30    # how often to scrape remote boards
  jobspy_hours: 3       # how often to scrape Indeed

filters:
  keywords: [...]          # any of these must appear in the job title
  exclude_keywords: [...]  # any of these in the title → skip
  seniority_allowed:       # only notify these levels
    - entry
    - associate
    - intern
  salary:
    min_pkr: 75000         # skip if stated salary is below this (PKR)
    min_usd: 600           # skip if stated salary is below this (USD)

scoring:
  semantic_threshold: 0.60  # cosine similarity cutoff (Stage 1)
  llm_threshold: 80         # LLM score cutoff (Stage 2) — only jobs above this are emailed
  daily_job_limit: 20       # max emails per day to avoid inbox flooding
```

## Data Persistence

All data lives in the `data/` directory (Docker volume-mounted):

| File | Contents |
|---|---|
| `data/jobs.db` | SQLite — every seen job with scores. Never re-notifies the same job. |
| `data/chroma/` | ChromaDB vector store of resume chunks. Auto-rebuilt if `resume.txt` changes. |
| `data/profile.json` | AI-extracted profile (name, skills, domains, seniority, experience). |

## Utility Scripts

```bash
# Preview the email template with sample data
python test_email.py

# Re-send the last 15 scored qualifying jobs (useful for testing)
docker exec -it job-radar python resend_qualified.py
```

## Verify Email is Working

Set `llm_threshold: 0` in `config.yaml` temporarily — this forces every semantically-passing job to qualify for email, letting you confirm delivery without waiting for real high-scoring matches. Remember to set it back to `80` after.

## Hard Gates

Even if a job scores ≥80, it is silently skipped if any of these are true:

- **Seniority**: role level is not in `seniority_allowed` (e.g., senior/lead roles are dropped)
- **Location**: on-site outside your configured cities, or remote but requiring work authorization in another country
- **Salary**: stated salary is explicitly below the configured minimums
- **Visa**: job requires work authorization / visa sponsorship not provided

These are evaluated by the LLM alongside the relevancy score — no separate API calls needed.

## Notes

- `python-jobspy` scrapes without API keys but may occasionally get rate-limited — handled gracefully (logs a warning, continues).
- Remote.co sometimes times out — also handled gracefully.
- The Gemini free tier (15 RPM) is respected via a threading lock that serializes all Gemini calls with a 15s sleep between them. Add a Groq key for a free fallback.
- Jobs are deduplicated by URL hash — a job seen once is never re-notified even if it reappears on a board.
