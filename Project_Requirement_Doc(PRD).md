# Product Requirements Document (PRD) — Agentic-JobApply-Companion

**Version:** 1.0.0  
**Author:** Anshul Das  
**Date:** August 2026  
**Status:** Approved  

---

## 1. Executive Summary

Agentic-JobApply-Companion is a semi-autonomous AI agent that automates the repetitive, error-prone parts of job applications while maintaining strict guardrails around data accuracy, legal compliance, and fraud prevention. The agent parses resumes, scrapes job listings, filters fraudulent postings, scores relevance, fills application forms with structurally enforced data separation, generates cover letters only when mandatory, and surfaces legal clauses for human review — all at $0 recurring cost using free-tier tools.

---

## 2. Problem Statement

### Current Pain Points

1. **Manual application fatigue**: Applying to 50+ jobs requires filling the same information repeatedly across different ATS platforms
2. **Data cross-contamination**: Existing autofill tools (LinkedIn, browser extensions) frequently put projects into experience fields, GitHub URLs into address fields, and round up experience durations
3. **Fraud exposure**: Job boards contain fraudulent listings that waste time or harvest personal data
4. **Legal risk**: Applications often contain binding clauses (arbitration, IP assignment, non-compete) buried in fine print that applicants accept without reading
5. **Generic cover letters**: AI-generated cover letters are immediately detectable due to generic, low-specificity language

### Solution

An agent that automates mechanical tasks while keeping humans in control of consequential decisions — with data accuracy enforced structurally (via typed schemas), not just by prompting.

---

## 3. Target Users

- **Primary**: Individual job seekers, particularly fresh graduates and early-career professionals
- **Scale**: Personal use (single user, single machine)
- **Technical level**: Comfortable running Python CLI commands; not required to write code

---

## 4. Functional Requirements

### 4.1 Resume Parsing & Profile Management

| ID | Requirement | Priority |
|---|---|---|
| FR-1.1 | Parse PDF and DOCX resumes into a structured `CandidateProfile` schema | Must |
| FR-1.2 | Separate experience, projects, education, contact info, and skills into strictly typed fields | Must |
| FR-1.3 | Run gap-check after parsing; ask user for missing fields exactly once | Must |
| FR-1.4 | Store profile in `data/candidate_profile.json` (gitignored) | Must |
| FR-1.5 | Provide CLI tool for viewing, editing, and exporting the profile | Must |
| FR-1.6 | Never re-ask for previously captured information | Must |
| FR-1.7 | Support YAML export for human-friendly editing | Should |

### 4.2 Job Scraping

| ID | Requirement | Priority |
|---|---|---|
| FR-2.1 | Scrape LinkedIn, Indeed, Naukri, Wellfound, ZipRecruiter via Apify | Must |
| FR-2.2 | Scrape Greenhouse, Lever, Ashby career pages directly | Must |
| FR-2.3 | Scrape Workday career pages via Playwright (JS-heavy) | Must |
| FR-2.4 | Scrape Y Combinator Work at a Startup board | Must |
| FR-2.5 | Deduplicate listings by URL hash | Must |
| FR-2.6 | Track Apify compute-unit cost per run | Must |
| FR-2.7 | Graceful degradation: one scraper failure doesn't block others | Should |

### 4.3 Fraud/Legitimacy Filter

| ID | Requirement | Priority |
|---|---|---|
| FR-3.1 | Hard-block listings with registration fees, payment requests, or sensitive data requests | Must |
| FR-3.2 | Hard-block listings with no verifiable company domain (generic email only) | Must |
| FR-3.3 | Hard-block listings with WhatsApp/Telegram-only hiring process | Must |
| FR-3.4 | Score soft signals: LinkedIn company presence, Glassdoor/AmbitionBox, salary reasonableness, urgency language | Must |
| FR-3.5 | Only pass listings that clear hard-blockers AND minimum legitimacy score | Must |
| FR-3.6 | Log rejection reason for every filtered listing | Must |

### 4.4 Job Relevance Scoring

| ID | Requirement | Priority |
|---|---|---|
| FR-4.1 | Compute embedding similarity between candidate profile and job description | Must |
| FR-4.2 | LLM-augmented scoring for skill match, experience relevance, location fit | Must |
| FR-4.3 | Configurable minimum score threshold | Must |
| FR-4.4 | Store embeddings in ChromaDB for deduplication and fast retrieval | Must |

### 4.5 Form Filling

| ID | Requirement | Priority |
|---|---|---|
| FR-5.1 | Classify each form field via LLM before filling | Must |
| FR-5.2 | Separate fill functions per data type: `fill_experience_field()`, `fill_project_field()`, `fill_contact_field()`, etc. | Must |
| FR-5.3 | No generic "fill from resume text" function — structural separation is mandatory | Must |
| FR-5.4 | Handle dropdowns: exact month granularity when available, lowest valid bucket otherwise | Must |
| FR-5.5 | "Years of experience" always resolves from `is_fresher_relevant` internship data only | Must |
| FR-5.6 | Pre-submission verification: diff-check populated form against profile data | Must |
| FR-5.7 | Halt submission on any mismatch (e.g., project in experience block) | Must |
| FR-5.8 | ATS-specific adapters for Greenhouse, Lever, Workday, Ashby | Must |

### 4.6 Cover Letter Generation

| ID | Requirement | Priority |
|---|---|---|
| FR-6.1 | Only generate when form marks cover letter as mandatory | Must |
| FR-6.2 | Draw exclusively from real `profile.experience` and `profile.projects` details | Must |
| FR-6.3 | Ban stock AI phrases: "passionate about", "leverage my skills", "fast-paced world", etc. | Must |
| FR-6.4 | Vary sentence length and structure naturally | Must |
| FR-6.5 | Write every letter to review queue for human pass | Must |

### 4.7 Legal Clause Handling

| ID | Requirement | Priority |
|---|---|---|
| FR-7.1 | Never auto-accept arbitration, non-compete, IP assignment, or background check clauses | Must |
| FR-7.2 | Extract and summarize unusual clauses in plain language | Must |
| FR-7.3 | Hard stop on any checkbox/toggle/consent agreement | Must |
| FR-7.4 | Auto-fill typed-name "e-signature" fields ONLY when standalone | Must |
| FR-7.5 | If typed-name field is adjacent to consent checkbox, treat entire block as legal action | Must |

### 4.8 Automation Tiers

| ID | Requirement | Priority |
|---|---|---|
| FR-8.1 | Tier 1 (ATS sites): eligible for auto-submit after burn-in period | Must |
| FR-8.2 | Tier 2 (LinkedIn, Indeed, Naukri): always require human click — permanent policy | Must |
| FR-8.3 | Burn-in period (first 2 weeks): all Tier 1 held for review | Must |
| FR-8.4 | Daily digest of submissions (file log, optional email) | Must |
| FR-8.5 | Cron or GitHub Actions scheduling for Tier 1 runs | Should |

### 4.9 Cost Tracking

| ID | Requirement | Priority |
|---|---|---|
| FR-9.1 | Log every LLM call's token count and estimated cost | Must |
| FR-9.2 | Log every Apify run's compute-unit cost | Must |
| FR-9.3 | Export to `usage_log.csv` for at-a-glance visibility | Must |
| FR-9.4 | Default to free-tier providers for all tasks | Must |

---

## 5. Non-Functional Requirements

| ID | Requirement | Category |
|---|---|---|
| NFR-1 | All API keys in `.env`, never hardcoded, never committed | Security |
| NFR-2 | No PII, resume data, or scraped personal data committed to repo | Security |
| NFR-3 | Python venv isolation — nothing installed globally | Environment |
| NFR-4 | `requirements.txt` with pinned versions for reproducibility | Environment |
| NFR-5 | Structured logging with timestamps for audit trail | Observability |
| NFR-6 | Comprehensive error handling with retry and exponential backoff | Reliability |
| NFR-7 | Type hints on all functions, enforced via mypy | Code Quality |
| NFR-8 | Unit + integration test coverage ≥ 80% | Testing |
| NFR-9 | CI pipeline: lint + type-check + test on every push | CI/CD |
| NFR-10 | Conventional commit messages (`feat:`, `chore:`, `docs:`, `fix:`) | Git |

---

## 6. Model Routing Strategy

| Task | Model Tier | Why |
|---|---|---|
| Resume parsing → structured schema | Small (Groq free tier) | Structured, narrow, low-risk task |
| Field-label classification | Small/Mid | Narrow classification, doesn't need frontier reasoning |
| Job relevance scoring | Small/Mid + embeddings | High volume, needs to be cheap |
| Cover letter generation | Best available | Quality directly affects natural-tone requirement |
| Legal clause extraction | Best available | High-stakes, must not miss binding clauses |

Implemented as a config-driven router (`model_router.py`) — swapping providers requires editing `config/model_config.yaml`, not business logic.

---

## 7. Data Schema

### CandidateProfile (Pydantic)

```
CandidateProfile
├── name: str
├── contact: ContactInfo
│   ├── address: str
│   ├── github_url: str
│   ├── linkedin_url: str
│   ├── email: str
│   └── phone: str
├── experience: List[Experience]         # ONLY real work/internship history
│   ├── type: "internship" | "full_time" | "part_time" | "contract"
│   ├── title: str
│   ├── company: str
│   ├── duration_months: int             # Exact, never rounded
│   ├── start_date: str
│   ├── end_date: str
│   ├── description: str
│   └── is_fresher_relevant: bool
├── projects: List[Project]              # ONLY personal/academic projects
│   ├── name: str
│   ├── description: str
│   ├── github_url: Optional[str]
│   └── tech_stack: List[str]
├── skills: List[str]
└── education: List[Education]
```

**Critical rule**: `fill_experience_field()` reads ONLY from `profile.experience`. `fill_project_field()` reads ONLY from `profile.projects`. No shared generic fill function exists.

---

## 8. Success Metrics

| Metric | Target |
|---|---|
| Field cross-contamination rate | 0% (enforced structurally) |
| Fraudulent listing pass-through rate | 0% for hard-blocker categories |
| Legal clause miss rate | 0% for checkboxes/toggles |
| Monthly cost | $0 (free tier only) |
| Profile re-ask rate | 0% (once captured, never re-asked) |
| Cover letter ban-phrase rate | 0% (re-generated on detection) |

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ATS layout changes break form filling | High | ATS-specific handlers with fallback to generic; verification pass catches errors |
| Apify free tier exhausted | Medium | Direct scraping fallback for most platforms; monitor usage in `usage_log.csv` |
| LLM rate limits hit | Medium | Fallback chain in model router (Groq → OpenRouter → Gemini) |
| LinkedIn/Indeed account ban from automation | High | Permanent Tier 2 policy: never auto-submit on these platforms |
| LLM hallucinates experience details | Critical | Fill functions structurally limited to profile data; verification diff-check before submit |

---

## 10. Delivery Requirements

- **Repository**: `Agentic-Job-Apply-Companion` on GitHub (public, `main` branch)
- **Documentation**: `README.md`, `Project_Architecture.md`, this PRD
- **Commit convention**: `feat:`, `chore:`, `docs:`, `fix:` — one module per commit
- **Config files**: `.gitignore`, `.env.example`, `requirements.txt`, `pyproject.toml`
- **Optional**: `docker-compose.yml`, `Dockerfile` for containerized runs
