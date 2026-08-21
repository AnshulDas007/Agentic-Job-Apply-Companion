# Project Architecture — Agentic-JobApply-Companion

## System Architecture Overview

```mermaid
flowchart TB
    subgraph Input["Input Layer"]
        A["Resume PDF/DOCX"] --> B["Resume Parser<br/>(pdfplumber + LLM)"]
        B --> C["CandidateProfile Store<br/>(data/candidate_profile.json)"]
        D["CLI Profile Editor<br/>(manage_profile.py)"] --> C
    end

    subgraph ModelRouter["Model Router (Config-Driven)"]
        MR["model_router.py"]
        MR --> SM["Small Tier<br/>Groq Free (Llama 3)"]
        MR --> BM["Best Tier<br/>Gemini / OpenRouter"]
        CT["Cost Tracker<br/>(usage_log.csv)"] -.-> MR
    end

    subgraph Scraping["Scraping Layer"]
        E["Apify Client<br/>LinkedIn, Indeed, Naukri,<br/>Wellfound, ZipRecruiter"]
        F["Direct Scraper<br/>Greenhouse, Lever,<br/>Workday, Ashby"]
        G["YC Scraper<br/>Work at a Startup"]
    end

    subgraph Processing["Processing Layer"]
        E & F & G --> H["Fraud/Legitimacy Filter"]
        H -->|"Pass"| I["Relevance Scorer<br/>(Embeddings + LLM)"]
        H -->|"Fail"| X["Rejected — Logged"]
        I --> J{"Score >= Threshold?"}
        J -->|"Yes"| K["Field Classifier"]
        J -->|"No"| X
    end

    subgraph FormFilling["Form Filling Layer — Strict Separation"]
        K --> L["fill_experience_field()<br/>reads ONLY profile.experience"]
        K --> M["fill_project_field()<br/>reads ONLY profile.projects"]
        K --> N["fill_contact_field()<br/>reads ONLY profile.contact"]
        K --> O["fill_education_field()<br/>reads ONLY profile.education"]
        C --> L & M & N & O
    end

    subgraph Review["Review Layer"]
        L & M & N & O --> P["Verification Pass<br/>Diff-Check Form vs Profile"]
        P --> Q["Legal Clause Review"]
        Q --> R{"Cover Letter<br/>Required?"}
        R -->|"Yes"| S["Cover Letter Generator"]
        R -->|"No"| T["Submission Decision"]
        S --> T
    end

    subgraph Submission["Submission Layer"]
        T --> U{"Tier?"}
        U -->|"Tier 1 — ATS Sites"| V["Auto-Submit<br/>(or Hold if Burn-in)"]
        U -->|"Tier 2 — LinkedIn/Indeed/Naukri"| W["Hold for Human Click"]
    end

    subgraph Logging["Audit Layer"]
        V & W --> Y["SQLite Database<br/>(Audit Trail)"]
        Y --> Z["Daily Digest<br/>(File Log / Email)"]
    end

    B & K & I -.->|"Uses"| MR
    S & Q -.->|"Uses"| MR
```

---

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI as main.py
    participant Parser as Resume Parser
    participant Store as Profile Store
    participant Scrapers as Job Scrapers
    participant Fraud as Fraud Filter
    participant Scorer as Relevance Scorer
    participant Filler as Form Filler
    participant Legal as Legal Review
    participant CoverLetter as Cover Letter
    participant DB as SQLite DB

    Note over User,CLI: First Run (Intake)
    User->>CLI: python main.py intake --resume resume.pdf
    CLI->>Parser: Parse resume
    Parser->>Store: Save CandidateProfile
    Store-->>CLI: Gap check results
    CLI->>User: Ask missing fields (once)
    User->>CLI: Provide answers
    CLI->>Store: Update profile (never ask again)

    Note over User,CLI: Regular Run (Apply Cycle)
    User->>CLI: python main.py run
    CLI->>Store: Load CandidateProfile
    CLI->>Scrapers: Scrape job listings
    Scrapers-->>CLI: Raw listings
    
    loop For each listing
        CLI->>Fraud: Check legitimacy
        Fraud-->>CLI: Pass/Fail + score
        alt Passed fraud filter
            CLI->>Scorer: Score relevance
            Scorer-->>CLI: Match score + breakdown
            alt Score >= threshold
                CLI->>Filler: Classify fields + fill form
                Filler->>Filler: Verification diff-check
                CLI->>Legal: Scan for legal clauses
                Legal-->>CLI: Clauses found?
                alt Has mandatory cover letter
                    CLI->>CoverLetter: Generate from real details
                    CoverLetter-->>CLI: Draft for review
                end
                alt Tier 1 (ATS) + burn-in cleared
                    CLI->>DB: Submit + log
                else Tier 2 or burn-in active
                    CLI->>DB: Hold for review + log
                    CLI->>User: Notification
                end
            end
        end
    end
    
    CLI->>DB: Generate daily digest
```

---

## Component Responsibilities

### Input Layer

| Component | File | Responsibility |
|---|---|---|
| Resume Parser | `backend/parsing/resume_parser.py` | Extract text from PDF/DOCX, LLM-structured extraction to `CandidateProfile`, one-time gap check |
| Profile Schema | `backend/parsing/profile_schema.py` | Pydantic models with strict typing — `Experience`, `Project`, `ContactInfo` are structurally separate |
| Profile Store | `backend/parsing/profile_store.py` | Load/save profile JSON, gap detection, merge without overwrite, version backup |
| Profile Manager | `manage_profile.py` | CLI for viewing, editing, exporting, and validating the stored profile |

### Model Router

| Component | File | Responsibility |
|---|---|---|
| Model Router | `backend/model_router.py` | Config-driven LLM routing: task tier → provider + model, fallback chains, retry with backoff |
| Model Config | `config/model_config.yaml` | Editable tier-to-model mapping — swap providers without code changes |
| Cost Tracker | `backend/cost_tracker.py` | Log every LLM call (model, tokens, latency, cost) and Apify run (compute units) |

### Scraping Layer

| Component | File | Responsibility |
|---|---|---|
| Base Scraper | `backend/scrapers/base_scraper.py` | Abstract base with retry, rate-limiting, error handling |
| Apify Scraper | `backend/scrapers/apify_scraper.py` | LinkedIn, Indeed, Naukri, Wellfound, ZipRecruiter via Apify marketplace actors |
| ATS Scraper | `backend/scrapers/ats_scraper.py` | Direct scraping for Greenhouse, Lever, Ashby; Playwright for Workday |
| YC Scraper | `backend/scrapers/yc_scraper.py` | Y Combinator Work at a Startup board |
| Job Schema | `backend/scrapers/job_schema.py` | `RawJobListing`, `ProcessedJobListing` Pydantic models |
| Scraper Registry | `backend/scrapers/scraper_registry.py` | Register and run scrapers by platform |

### Processing Layer

| Component | File | Responsibility |
|---|---|---|
| Fraud Filter | `backend/fraud_filter/filter.py` | Hard-blocker checks (deterministic) + soft-signal scoring (weighted) |
| Signal Checkers | `backend/fraud_filter/signals.py` | Individual checkers: company LinkedIn, Glassdoor, salary reasonableness, urgency language |
| Relevance Scorer | `backend/matching/scorer.py` | Embedding similarity + LLM-augmented scoring, configurable thresholds |
| Vector Store | `backend/matching/vector_store.py` | ChromaDB wrapper for job embeddings, deduplication |
| Embeddings | `backend/matching/embeddings.py` | sentence-transformers embedding generation |

### Form Filling Layer

| Component | File | Responsibility |
|---|---|---|
| Field Classifier | `backend/form_filler/field_classifier.py` | Extract label + context → LLM classify → route to typed filler |
| Filler | `backend/form_filler/filler.py` | Structurally separate fill functions per data type — zero cross-contamination |
| Verification | `backend/form_filler/verification.py` | Pre-submission diff-check: form contents vs profile data |
| Dropdown Handler | `backend/form_filler/dropdown_handler.py` | Duration/year-bucket selection logic |
| ATS Handlers | `backend/form_filler/ats_handlers/` | Greenhouse, Lever, Workday, Ashby, Generic adapters |

### Review Layer

| Component | File | Responsibility |
|---|---|---|
| Cover Letter | `backend/cover_letter/generator.py` | Mandatory-only trigger, real-detail specificity, ban-list enforcement |
| Ban List | `backend/cover_letter/ban_list.py` | Stock AI phrase detection + rejection |
| Legal Reviewer | `backend/legal_review/reviewer.py` | Clause extraction, plain-language summary, consent detection |
| Clause Patterns | `backend/legal_review/clause_patterns.py` | Regex + keyword patterns for legal terms |

### Orchestration Layer

| Component | File | Responsibility |
|---|---|---|
| Pipeline | `backend/pipeline.py` | Full orchestration: scrape → filter → score → fill → review → submit/hold |
| Database | `backend/database.py` | SQLite wrapper: applications, jobs, usage, audit tables with migrations |
| Digest | `backend/digest.py` | Daily activity summary generation |
| Main CLI | `main.py` | Entry point: `intake`, `run`, `status`, `review` subcommands |
| Scheduler | `schedule.py` | Cron-based scheduling for Tier 1 auto-apply |

---

## Database Schema

```mermaid
erDiagram
    JOBS {
        text id PK
        text title
        text company
        text url
        text source
        text description
        real legitimacy_score
        real relevance_score
        text status
        text scraped_at
        text processed_at
    }
    
    APPLICATIONS {
        text id PK
        text job_id FK
        text tier
        text status
        text cover_letter_path
        text legal_review_summary
        text submitted_at
        text reviewed_by
        text notes
    }
    
    AUDIT_TRAIL {
        integer id PK
        text timestamp
        text action
        text target
        text details
        text result
    }
    
    USAGE_LOG {
        integer id PK
        text timestamp
        text service
        text model
        integer tokens_in
        integer tokens_out
        real cost_estimate
        real latency_ms
    }

    JOBS ||--o{ APPLICATIONS : "has"
    APPLICATIONS ||--o{ AUDIT_TRAIL : "logs"
```

---

## Security Model

- **Secrets**: All API keys in `.env`, never committed, loaded via `python-dotenv`
- **PII**: Candidate profile and scraped data in `data/` (gitignored), never committed
- **Legal**: All consent/legal checkboxes require explicit human action — no auto-acceptance
- **Audit**: Every action logged with timestamp, target, and result for traceability
- **Platform Safety**: LinkedIn/Indeed/Naukri always require human click to avoid account bans
