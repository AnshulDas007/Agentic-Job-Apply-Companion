# Agentic-JobApply-Companion

> An agentic job-application copilot that only applies to verified companies, never fabricates experience, and never auto-signs anything legally binding.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

---

## What It Does

A semi-autonomous AI agent that handles the repetitive, error-prone parts of job applications while keeping humans in control of every decision that matters:

1. **Parses your resume** into a structured, typed profile — once, not per application
2. **Scrapes job listings** from LinkedIn, Indeed, Naukri, Wellfound, ZipRecruiter, Y Combinator, and company career pages (Greenhouse, Lever, Workday, Ashby)
3. **Filters out fraud** — registration fees, fake companies, WhatsApp-only hiring, and other red flags are automatically blocked
4. **Scores relevance** — embedding similarity + LLM-augmented matching against your actual skills and experience
5. **Fills application forms** with strict data separation — experience stays in experience fields, projects stay in project fields, contact info stays in contact fields. No cross-contamination.
6. **Generates cover letters** only when required, built from your real project details — never generic AI filler
7. **Surfaces legal clauses** — arbitration, non-compete, IP assignment, background checks are flagged for your review before any submission
8. **Auto-applies on safe-tier sites** (Greenhouse, Lever, etc.) after a burn-in period; LinkedIn/Indeed/Naukri always require your click

---

## Non-Negotiable Guardrails

| # | Guardrail |
|---|---|
| 1 | Never fabricate or inflate work experience — exact duration, no rounding up |
| 2 | Never mix experience, projects, and contact fields — enforced structurally via typed schema |
| 3 | Never submit legally binding clauses without explicit human review |
| 4 | Typed-name "e-signature" auto-filled only when standalone (not bundled with consent) |
| 5 | Never generate a cover letter unless the form requires one |
| 6 | Never auto-apply on LinkedIn/Indeed/Naukri without a human click |
| 7 | Never apply to a listing that failed the fraud filter |
| 8 | Never commit secrets — `.env` stays local and gitignored |
| 9 | Never re-ask for information already captured — profile store is single source of truth |
| 10 | Always log what was submitted and why, for audit |

---

## Tech Stack

| Component | Technology | Cost |
|---|---|---|
| Language | Python 3.11+ | Free |
| Browser Automation | Playwright | Free |
| LLM Access | Groq, OpenRouter, Gemini (config-driven router) | Free tier |
| Vector Store | ChromaDB | Free |
| Database | SQLite | Free |
| Scraping | Apify (LinkedIn/Naukri) + direct scraping (ATS/YC) | $5/mo free tier |
| Scheduling | cron / GitHub Actions | Free |

**Total recurring cost: $0** at personal scale.

---

## Quick Start

### Prerequisites

- Python 3.11 or higher
- At least one LLM API key ([Groq](https://console.groq.com) recommended — free, 14,400 req/day)

### Setup

```bash
# Clone the repository
git clone https://github.com/AnshulDas007/Agentic-Job-Apply-Companion.git
cd Agentic-Job-Apply-Companion

# Full setup (venv + dependencies + Playwright browsers)
make setup

# Activate the virtual environment
source venv/bin/activate

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your API keys (at minimum: GROQ_API_KEY)
```

### First Run — Profile Intake

```bash
# Parse your resume and build your candidate profile
make intake
# or: python main.py intake --resume path/to/your/resume.pdf

# View your profile
python manage_profile.py view

# Edit a field if needed
python manage_profile.py edit
```

### Running the Agent

```bash
# Run a scrape + match + apply cycle
make run
# or: python main.py run

# Check recent activity
make status
# or: python main.py status

# Review pending applications (Tier 2 / burn-in holds)
make review
# or: python main.py review
```

---

## Project Structure

```
Agentic-Job-Apply-Companion/
├── backend/
│   ├── scrapers/              # Apify + direct scraping modules
│   ├── parsing/               # Resume → CandidateProfile schema
│   ├── matching/              # Relevance scoring + vector similarity
│   ├── fraud_filter/          # Legitimacy checks (hard blockers + soft signals)
│   ├── form_filler/           # Playwright automation + field classification
│   │   └── ats_handlers/      # Platform-specific adapters
│   ├── cover_letter/          # Conditional generation module
│   ├── legal_review/          # Clause extraction + summarization
│   ├── model_router.py        # Config-driven LLM routing
│   ├── database.py            # SQLite wrapper + audit logging
│   ├── cost_tracker.py        # LLM token + Apify cost tracking
│   ├── pipeline.py            # Main orchestration pipeline
│   └── digest.py              # Daily activity digest
├── config/                    # YAML configuration files
├── data/                      # (gitignored) Profile, logs, scraped data
├── logs/                      # (gitignored) Application logs
├── tests/                     # Comprehensive test suite
├── .github/workflows/         # CI/CD + scheduled auto-apply
├── .env.example               # Environment template
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── main.py                    # CLI entry point
├── manage_profile.py          # Profile management CLI
├── schedule.py                # Cron scheduling helper
├── Project_Architecture.md
├── Project_Requirement_Doc(PRD).md
└── README.md
```

---

## Model Routing Strategy

Tasks are routed to different model tiers based on stakes, not one model for everything:

| Task | Model Tier | Default Provider |
|---|---|---|
| Resume parsing | Small | Groq (Llama) |
| Field classification | Small/Mid | Groq (Llama) |
| Job relevance scoring | Small/Mid + Embeddings | Groq + sentence-transformers |
| Cover letter generation | Best available | Gemini / Claude |
| Legal clause review | Best available | Gemini / Claude |

Configure in [`config/model_config.yaml`](config/model_config.yaml) — swap providers without touching code.

---

## Automation Tiers

| Tier | Platforms | Behavior |
|---|---|---|
| **Tier 1** | Greenhouse, Lever, Workday, Ashby, direct career pages | Auto-submit after burn-in period |
| **Tier 2** | LinkedIn, Indeed, Naukri | Always requires human click (permanent — ToS/ban risk) |

**Burn-in period (first 2 weeks):** All applications held for review. Switch to unattended only when verification failures reach zero.

---

## Development

```bash
# Run tests
make test

# Run tests with coverage
make test-cov

# Lint + type check
make lint

# Auto-format code
make format

# Clean build artifacts
make clean
```

---

## Documentation

- [**Project Architecture**](Project_Architecture.md) — System design, data flow, component interactions
- [**Product Requirements Document**](Project_Requirement_Doc(PRD).md) — Full specification and requirements

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## Author

**Anshul Das** — [GitHub](https://github.com/AnshulDas007)
