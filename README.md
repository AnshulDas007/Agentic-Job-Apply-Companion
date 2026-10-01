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
5. **Opens GitHub Issues** for every qualifying job — with match scores, fraud results, cover letter drafts, and legal flags — so you review and approve from your phone or browser
6. **Auto-applies on safe-tier sites** (Greenhouse, Lever, etc.) after you label an Issue `approve`; LinkedIn/Indeed/Naukri always flag as "manual apply required"
7. **Generates cover letters** only when required, built from your real project details — never generic AI filler
8. **Surfaces legal clauses** — arbitration, non-compete, IP assignment, background checks are flagged for your review before any submission

---

## How It Works — GitHub Actions + Issues

This project runs **entirely on GitHub Actions** — no local machine needs to stay on, no dedicated server, no custom web app. **GitHub Issues is the review interface.**

```
Daily Schedule (GitHub Actions)
┌──────────────────────┐     ┌───────────────────────┐
│ scrape-and-score.yml │────▶│   GitHub Issues        │
│ (9:00 AM UTC daily)  │     │   (your review inbox)  │
│                      │     │                        │
│ • Scrape listings    │     │ You label:             │
│ • Fraud filter       │     │   approve → auto-apply │
│ • Score relevance    │     │   reject  → skip       │
│ • Open Issues        │     └───────────┬────────────┘
└──────────────────────┘                 │
                                         ▼
                            ┌───────────────────────┐
                            │ apply-tier1.yml        │
                            │ (11:00 AM UTC daily)   │
                            │                        │
                            │ • Read approved Issues  │
                            │ • Apply via Playwright  │
                            │ • Close with outcome   │
                            └───────────────────────┘
```

**Tier 2 (LinkedIn/Indeed/Naukri)** stays manual — Issues are opened with all the details (scores, cover letter, legal flags) so you can apply yourself using the pre-filled drafts.

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
| 8 | Never commit secrets — API keys live in Repo → Settings → Secrets |
| 9 | Never re-ask for information already captured — profile store is single source of truth |
| 10 | Always log what was submitted and why, for audit |

---

## Tech Stack

| Component | Technology | Cost |
|---|---|---|
| Language | Python 3.11+ | Free |
| Browser Automation | Playwright | Free |
| LLM Access | Groq, Gemini (config-driven router) | Free tier |
| Vector Store | ChromaDB | Free |
| Database | SQLite | Free |
| Scraping | Apify (LinkedIn/Naukri) + direct scraping (ATS/YC) | $5/mo free tier |
| Execution | GitHub Actions | Free (2,000 min/mo private, unlimited public) |
| Review Interface | GitHub Issues | Free |

**Total recurring cost: $0** at personal scale.

---

## Getting Started

### 1. Fork / Clone

```bash
git clone https://github.com/AnshulDas007/Agentic-Job-Apply-Companion.git
cd Agentic-Job-Apply-Companion
```

### 2. Add Secrets

Go to **Repo → Settings → Secrets and variables → Actions** and add:

| Secret Name | Description | Required |
|---|---|---|
| `GROQ_API_KEY` | [Groq](https://console.groq.com) API key (free, 14,400 req/day) | ✅ |
| `GOOGLE_AI_API_KEY` | [Google AI Studio](https://aistudio.google.com) API key (free, 60 req/min) | ✅ |
| `APIFY_TOKEN` | [Apify](https://apify.com) API token (free $5/mo credit) | ✅ |

> `GITHUB_TOKEN` is automatically provided by GitHub Actions — you don't need to set it.

### 3. Create Your Profile

```bash
# Local setup (one-time)
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Parse your resume
python main.py intake --resume path/to/resume.pdf

# Verify your profile
python main.py profile
```

Commit `data/candidate_profile.json` to the repo — the Actions workflows read it from there.

### 4. Push → Workflows Run Automatically

The `scrape-and-score` workflow runs daily at 9:00 AM UTC. You can also trigger it manually from **Actions → Daily Job Scrape and Score → Run workflow**.

### 5. Review Issues, Label, Done

- Open Issues appear with job details, scores, cover letter drafts, and legal flags
- Label `approve` on Tier 1 jobs to auto-apply
- Tier 2 jobs (LinkedIn/Indeed) are flagged "manual apply required" — use the details to apply yourself

---

## Required Secrets

| Secret | Where to Get It | What It's For |
|---|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | Resume parsing, field classification, scoring |
| `GOOGLE_AI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) | Cover letters, legal clause review |
| `APIFY_TOKEN` | [apify.com](https://apify.com) | Scraping LinkedIn, Indeed, Naukri listings |

---

## Project Structure

```
Agentic-Job-Apply-Companion/
├── .github/workflows/
│   ├── scrape-and-score.yml     # Daily scrape → filter → score → open Issues
│   └── apply-tier1.yml          # Apply to approved company-site listings
├── backend/
│   ├── scrapers/                # Apify + direct scraping modules
│   ├── parsing/                 # Resume → CandidateProfile schema
│   ├── matching/                # Relevance scoring + vector similarity
│   ├── fraud_filter/            # Legitimacy checks (hard blockers + soft signals)
│   ├── form_filler/             # Playwright automation + field classification
│   │   └── ats_handlers/        # Platform-specific adapters
│   ├── cover_letter/            # Conditional generation module
│   ├── legal_review/            # Clause extraction + summarization
│   ├── issues_review/           # GitHub Issues API — open/read/label/close
│   ├── model_router.py          # Config-driven LLM routing
│   ├── orchestrator.py          # Two-phase pipeline (scrape+score / apply)
│   ├── database.py              # SQLite wrapper + audit logging
│   └── cost_tracker.py          # LLM token + Apify cost tracking
├── config/                      # YAML configuration files
├── data/
│   ├── jobs_seen.json           # Dedupe log (committed by Actions bot)
│   └── candidate_profile.json   # Your profile (committed once)
├── tests/                       # Comprehensive test suite
├── run_pipeline.py              # GitHub Actions entry point
├── main.py                      # Local CLI (intake, status, profile)
├── manage_profile.py            # Profile management CLI
├── pyproject.toml               # Project metadata + tool config
├── requirements.txt             # Pinned dependencies
├── .env.example                 # Environment template
├── Project_Architecture.md
├── Project_Requirement_Doc(PRD).md
└── README.md
```

---

## Automation Tiers

| Tier | Platforms | Behavior |
|---|---|---|
| **Tier 1** | Greenhouse, Lever, Workday, Ashby, direct career pages | Auto-apply after `approve` label |
| **Tier 2** | LinkedIn, Indeed, Naukri | Always manual — Issue provides pre-filled details |

**Burn-in period (first 2 weeks):** The `apply-tier1` workflow runs with `--burn-in` flag, logging what it *would* apply to without actually submitting. Verify the fraud filter, scoring, and cover letters are correct before removing the flag.

---

## Cost Tracking

| Service | Free Tier | Monitor At |
|---|---|---|
| GitHub Actions | 2,000 min/mo (private), unlimited (public) | Repo → Settings → Actions → Usage |
| Groq | 14,400 req/day | [console.groq.com](https://console.groq.com) |
| Apify | $5/mo platform credit | [apify.com/account](https://apify.com) |
| Google AI Studio | 60 req/min | [aistudio.google.com](https://aistudio.google.com) |

---

## Development

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e '.[dev]'

# Run tests
python -m pytest tests/ -v

# Lint
ruff check .

# Type check
mypy backend/
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
