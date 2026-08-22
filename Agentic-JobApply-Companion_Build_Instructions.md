# Agentic-JobApply-Companion — Build Instructions

**Project name:** Agentic-JobApply-Companion
**Tagline:** An agentic job-application copilot that only applies to verified companies, never fabricates experience, and never auto-signs anything legally binding.

This document is the full specification. Hand it to the coding agent as-is. It covers architecture, data schema, guardrails, safety practices, and GitHub delivery requirements.

---

## 1. Project Overview

Build a semi-autonomous AI agent that:
1. Parses the user's resume(s) into a structured, typed profile (never raw text re-parsed per application)
2. Scrapes/ingests job listings from LinkedIn, Indeed, Naukri, Wellfound, ZipRecruiter, Y Combinator's job board, and individual company career pages (Greenhouse, Lever, Workday, Ashby, custom ATS)
3. Scores each listing for relevance against the user's profile
4. Runs every listing through a **fraud/legitimacy filter** before it is eligible for application
5. Fills out application forms accurately, with strict separation between work experience, internships, and personal projects
6. Generates a cover letter **only when the form marks it mandatory**, in natural human tone, from the user's real project/experience details — never generic filler
7. Extracts and surfaces any legally binding clause (arbitration, IP assignment, e-signature, background check authorization) for human review before submission — never auto-accepts these
8. Applies automatically **only** on company/ATS sites that passed the fraud filter and clear a match-score threshold; requires a human click for LinkedIn, Indeed, Naukri (platform ToS/ban-risk reasons — see Section 6)
9. Logs every action for audit and cost tracking

---

## 2. Tech Stack (all free/open-source)

- **Language:** Python 3.11+
- **Browser automation:** Playwright (handles JS-heavy ATS forms better than Selenium)
- **LLM access:** Provider-agnostic client (see Section 3) — no hardcoded single provider
- **Vector store:** ChromaDB or a local FAISS index (free, no hosted service needed) for resume/job embedding
- **Database:** SQLite (single-file, zero setup, sufficient at personal scale)
- **Scraping:** Apify (existing pipeline) for LinkedIn/Naukri/Wellfound; direct `requests`/Playwright scraping for company ATS pages and YC job board (no need to spend Apify credits on structurally simple sites)
- **Scheduling:** `cron` (Linux) or GitHub Actions scheduled workflow (free tier) for the "safe tier" auto-apply run
- **Environment isolation:** `venv` (Python's built-in virtual environment) — nothing installed globally

---

## 3. Model Routing Strategy

Route tasks by stakes, not by using one model for everything:

| Task | Model tier | Why |
|---|---|---|
| Resume parsing → structured schema | Small open model (local via Ollama, or Groq free tier) | Structured, narrow, low-risk task |
| Field-label classification (is this field "experience," "project," "address," "GitHub URL"?) | Small/mid open model | Narrow classification task, doesn't need frontier reasoning |
| Job relevance scoring | Small/mid open model + embedding similarity | High volume, needs to be cheap |
| Cover letter generation | Best available model (Claude/GPT free-tier credits, or best open model available) | Quality directly affects "not AI-detectable, natural tone" requirement |
| Legal clause extraction & summarization | Best available model | High-stakes, must not miss a binding clause |

Implement this as a config-driven router (`model_router.py`) so swapping providers doesn't require touching business logic.

---

## 4. Environment & Security Setup (mandatory, do this first)

- Create a `venv` before installing anything: `python -m venv venv` → activate → install into the venv only
- All API keys (LLM providers, Apify token) go in a `.env` file — **never hardcoded, never committed**
- `.env` must be listed in `.gitignore` from the very first commit
- Provide a `.env.example` file with placeholder keys (e.g. `GROQ_API_KEY=your_key_here`) so the repo is self-documenting without exposing real secrets
- Use `python-dotenv` to load environment variables at runtime
- `requirements.txt` pinned with exact versions for reproducibility
- No credentials, resume PII, or scraped personal data ever committed to the repo — add `/data/`, `/logs/`, and any personal-profile JSON to `.gitignore`

---

## 5. One-Time Profile Intake & Editing

The agent must never re-ask for the same information across sessions or applications. Any field it cannot determine from the resume or already-stored profile is asked **once**, then written permanently to the profile store.

- **Intake flow:** on first run, the agent parses the resume into the `CandidateProfile` schema (Section 6), then runs a gap-check — any schema field it couldn't confidently fill (e.g., phone number not on resume, work-authorization status, notice period, preferred locations, salary expectation) is asked via a single interactive prompt/CLI session, not scattered across later runs
- Once answered, the value is written to the local profile store (`data/candidate_profile.json`, gitignored) and never asked again
- Later runs load the stored profile directly — no re-parsing, no re-asking, unless a gap check finds a genuinely new field (e.g., a new application asks for something not previously captured)
- **Manual editing:** provide a simple, human-readable way to review and edit stored values without touching code:
  - A single editable file (`data/candidate_profile.json` or a friendlier `data/candidate_profile.yaml`) that's easy to open and hand-edit
  - Optionally, a minimal CLI command (e.g., `python manage_profile.py edit`) that lists current fields with their values and lets the user update one by selecting its number/name — lower-friction than hunting through raw JSON
  - Any manual edit takes effect on the next run with no other changes needed — the profile store is the single source of truth the rest of the pipeline always reads from

---

## 6. Data Schema (strict typing — this is the core fix for field-mixing issues)

```python
# profile_schema.py

class Experience(BaseModel):
    type: Literal["internship", "full_time", "part_time", "contract"]
    title: str
    company: str
    duration_months: int          # exact, e.g. 6 — never rounded
    start_date: str
    end_date: str
    description: str
    is_fresher_relevant: bool     # True for the internship, used when forms ask "years of experience"

class Project(BaseModel):
    name: str
    description: str
    github_url: Optional[str]
    tech_stack: List[str]
    # Projects NEVER populate an "experience" field, under any circumstance

class ContactInfo(BaseModel):
    address: str
    github_url: str
    linkedin_url: str
    email: str
    phone: str
    # Kept as fully separate typed fields — github_url can never be
    # written into address, and vice versa

class CandidateProfile(BaseModel):
    name: str
    contact: ContactInfo
    experience: List[Experience]   # ONLY real work/internship history
    projects: List[Project]        # ONLY personal/academic projects
    skills: List[str]
    education: List[dict]
```

**Rule enforced in code, not just prompting:** the form-filling module has separate functions `fill_experience_field()` and `fill_project_field()` that only ever read from `profile.experience` and `profile.projects` respectively. There is no shared/generic "fill field with resume text" function — this structural separation is what prevents the cross-contamination you've seen company autofill tools do.

---

## 7. Field Classification Logic (before filling anything)

For every form field encountered:

1. Extract the field's label, nearby heading/section text, and input type (text, dropdown, textarea)
2. Classify via LLM call: *"Given this label and surrounding context, is this field asking for: (a) work experience, (b) a project, (c) a URL/portfolio link, (d) a personal address, (e) years of experience, (f) something else?"*
3. Route to the matching typed field from the schema in Section 6 — never a fuzzy/generic match
4. **Duration/dropdown handling:**
   - If the field allows month-level granularity → fill the internship's exact `duration_months` (6)
   - If the field only offers coarse year buckets (e.g., "0-1 yrs", "1-3 yrs") → select the lowest bucket that includes 6 months; never round up
   - If the field is a plain "Years of experience" number input → this always resolves from `is_fresher_relevant` internship data only, never invented
5. **Verification pass before submission:** diff-check what's populated in the form's Experience section against `profile.experience`, and Projects section against `profile.projects`. Any mismatch (e.g., a project ended up in the experience block) halts submission and flags for review — this catches both the agent's own mistakes and the ATS's native autofill doing it wrong.

---

## 8. Fraud / Legitimacy Filter (runs before a listing is eligible for application)

Hard blockers (any one of these disqualifies a listing automatically):
- Any mention of a registration fee, training deposit, "buy equipment first," or payment of any kind at application stage
- No verifiable company domain (generic Gmail/Yahoo contact instead of a company email)
- Entire hiring process conducted via WhatsApp/Telegram with no email trail
- Request for bank details, SSN-equivalent (Aadhaar/PAN), or payment card info at the *application* stage

Scored/soft signals (weighted, contribute to a legitimacy score):
- Company has a real LinkedIn page with plausible employee count and posting history
- Presence (or absence) on AmbitionBox/Glassdoor
- Salary offered is realistic for role/experience level (wildly inflated pay for entry-level fresher roles is a red flag)
- Urgency-pressure language ("apply within 2 hours", "immediate joining, no interview")

Only listings that clear both the hard-blocker check and a minimum legitimacy score proceed to relevance scoring.

---

## 9. Cover Letter Generation Rules

- **Only generate when the form explicitly marks it mandatory** — skip otherwise
- Draw exclusively from real details in `profile.experience` and `profile.projects` (e.g., specific decisions made building the Deep-Research Copilot, actual outcomes) — never generic "I am a passionate professional" filler
- Vary sentence length and structure naturally; no uniform LLM cadence
- Ban list of stock AI phrases the generator must never use: "In today's fast-paced world," "I am excited to leverage my skills," "passionate about," "dynamic environment," and similar generic filler
- No jargon — plain, natural language
- Every generated letter is written to a review queue; the user does a quick pass before it's sent, at least during the initial calibration period
- **Note on "AI-detectability":** there is no removable watermark in text-based AI detectors — they flag generic, low-specificity writing. The actual fix is specificity, not evasion. A letter built from real, concrete details reads as human because it substantively is.

---

## 10. Legal Clause Handling

- Never auto-accept or auto-check: arbitration clauses, non-compete/non-solicit terms, broad IP-assignment clauses, background-check authorizations
- Extract and summarize any unusual clause in plain language, surfaced to the user before submission
- Hard stop (no submission without explicit user action) on any legally binding *checkbox or agreement toggle*

**Narrow e-signature exception:** where the "e-signature" requirement is simply typing your full legal name into a text field (the common "type your name to sign" pattern), the agent may fill this automatically from `profile.contact.name` — this is a data-entry action, not a consent decision. This exception does **not** extend to:
- Checkboxes or toggles agreeing to terms, arbitration, or policies (still requires explicit human action, per above)
- Drawn/uploaded signature images
- Any field bundled with a consent statement requiring a separate acknowledgment click

If a typed-name field is directly adjacent to or bundled with a consent checkbox, treat the whole block as a legal-acceptance action and hold for human review rather than auto-filling either part.

---

## 11. Automation Tiers & Scheduling

- **Tier 1 — Company/ATS sites (Greenhouse, Lever, Workday, Ashby, direct career pages):** eligible for scheduled, unattended auto-apply *after* a burn-in period (see below)
- **Tier 2 — LinkedIn, Indeed, Naukri:** always require a human click before submission. These platforms actively detect and ban automated application patterns — this is a permanent policy, not a temporary trust threshold
- **Burn-in period:** for the first 1–2 weeks, run Tier 1 in "generate + hold for review" mode. Spot-check a sample of filled forms and cover letters. Only switch to fully unattended scheduling once verification-pass failures are at zero across enough real cases
- Scheduled runs (cron or GitHub Actions) send a daily digest (email or file log) of what was submitted, to whom, and why it was scored as a match — unattended does not mean invisible

---

## 12. Cost Tracking (staying at $0)

- **Apify:** free tier = $5 platform credit/month, non-rolling, hard-capped (cannot overspend — it blocks new runs instead of billing). Run small test batches first, check actual compute-unit cost per platform in the Apify Console before scaling scrape frequency
- **LLM calls:** default to free-tier hosted open models (Groq, OpenRouter free tiers) or local Ollama inference for parsing/classification/scoring; reserve any paid-tier credits only for cover letters and legal-clause review
- **Everything else** (Playwright, SQLite, ChromaDB/FAISS, cron/GitHub Actions at low volume) is free with no usage ceiling relevant at personal scale
- Log every LLM call's token count and every Apify run's compute-unit cost to a local `usage_log.csv` so spend is visible at a glance, even though it should stay at $0

---

## 13. Repository Structure

```
Agentic-JobApply-Companion/
├── backend/
│   ├── scrapers/          # Apify + direct scraping modules
│   ├── parsing/           # resume → CandidateProfile schema
│   ├── matching/          # relevance scoring
│   ├── fraud_filter/      # legitimacy checks
│   ├── form_filler/       # Playwright automation + field classification
│   ├── cover_letter/      # generation module
│   ├── legal_review/      # clause extraction/summarization
│   └── model_router.py
├── data/                  # gitignored — profile, logs, scraped jobs
├── .env.example
├── .gitignore
├── requirements.txt
├── docker-compose.yml     # optional, for consistent local runs
├── README.md
├── Project_Architecture.md
└── Project_Requirement_Doc(PRD).md
```

---

## 14. GitHub Delivery Requirements

- Repository name: `Agentic-JobApply-Companion`
- Public repo, `main` branch
- Include: `README.md`, `Project_Architecture.md`, `Project_Requirement_Doc(PRD).md`, `.gitignore`, `requirements.txt`
- **Commit messages must use conventional prefixes matching each file's role**, consistent with the existing `Agentic-Deep-Research-Copilot` repo convention:
  - `feat:` for new functional modules (e.g., `feat: fraud filter with hard-blocker and scored legitimacy checks`)
  - `chore:` for config/dependency/setup files (`.gitignore`, `requirements.txt`, `docker-compose.yml`)
  - `docs:` for README, PRD, and architecture doc commits
  - `fix:` for bug fixes
- Each module should land in its own commit with a message describing what that specific file/module does — not a single bulk "initial commit"

---

## 15. Summary of Non-Negotiable Guardrails

1. Never fabricate or inflate work experience — internship data only, exact duration
2. Never mix experience, projects, and contact fields — enforced structurally via schema, not just prompting
3. Never submit a legally binding clause (checkbox, agreement toggle, consent-bundled signature) without explicit human review
4. Typed-name "e-signature" fields may be auto-filled *only* when standalone and not bundled with a consent checkbox
5. Never generate a cover letter unless the form requires one
6. Never auto-apply on LinkedIn/Indeed/Naukri without a human click
7. Never apply to a listing that failed the fraud filter
8. Never commit secrets — `.env` stays local and gitignored
9. Never re-ask the user for information already captured — profile store is the single source of truth, with an easy manual-edit path
10. Always log what was submitted and why, for audit
