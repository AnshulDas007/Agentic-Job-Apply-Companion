# Build Progress Tracker
# ============================================================
# This file tracks build progress for token continuity.
# If the conversation is interrupted, start a new conversation
# and say "continue building" — the agent will read this file
# and pick up exactly where it left off.
# ============================================================

## Current Phase: DONE
## Current Step: All Phases Complete (Phases 1–17)
## Status: COMPLETED
## Last Completed: Phase 17 (GitHub Actions + Issues Architecture — committed and pushed)
## Next Action: Project is fully built! Add your repo secrets and trigger the workflows.
## Blockers: None

## Completed Phases:
- Phase 1: Docs, scaffolding, git push, env setup, Groq API key added
- Phase 2: CandidateProfile schema, profile store, manage_profile CLI, tests
- Phase 3: Model router (config-driven, fallback chains, rate limiting), cost tracker, tests + live Groq integration verified
- Phase 4: Scraping layer (Apify, Greenhouse/Lever/Ashby ATS, YC Jobs), job schema, scraper registry, tests
- Phase 5: Fraud filter (hard blockers + soft-signal scoring), signal checkers, tests
- Phase 6: Matching layer (embeddings via sentence-transformers, ChromaDB vector store, multi-signal relevance scorer with skill/experience/location/embedding scoring), tests
- Phase 7: Cover letter generation (mandatory-only, banned-phrase enforcement, real profile data), tests
- Phase 8: Legal review module (rule-based and LLM-based clause detection, consent element classification, e-signature exceptions), tests
- Phase 9: Form filling layer (strict separation of experience/projects, field classification, value mapping, duration buckets), tests
- Phase 10: Scheduling & Automation (Application Orchestrator, tier 1/2 platform routing, burn-in mode, daily digest generation), tests
- Phase 11: Resume parser (PDF/DOCX extraction via pdfplumber/python-docx, LLM-structured extraction, gap-check), tests
- Phase 12: SQLite database (jobs, applications, audit_trail, usage_log tables, CRUD operations, statistics), tests
- Phase 13: Form filler enhancements (verification diff-check, dropdown/year-bucket handler, ATS handlers for Greenhouse/Lever/Workday/Ashby/Generic), tests
- Phase 14: Cover letter ban list and legal review clause patterns extracted to standalone modules, tests
- Phase 15: CLI entry point (main.py with intake/run/status/review/profile subcommands) and scheduling module (cron + GitHub Actions), tests
- Phase 16: Git finalization — all phases committed with conventional prefixes and pushed
- Phase 17 (in progress): GitHub Actions + Issues Architecture
  - DONE: Deleted Dockerfile, docker-compose.yml, demo.py, Makefile, schedule.py, requirements-dev.txt
  - DONE: Deduplicated deps — pyproject.toml uses dynamic=[dependencies], requirements.txt is source of truth
  - DONE: Added PyGithub>=2.5.0 to requirements.txt
  - DONE: Updated .gitignore — selective data/ tracking (jobs_seen.json, candidate_profile.json), removed Docker ignores
  - DONE: Created backend/issues_review/ module (GitHubIssuesManager: open/read/label/close Issues)
  - DONE: Refactored orchestrator to two-phase model (run_scrape_and_score + run_apply_tier1 + dedupe via jobs_seen.json)
  - DONE: Created run_pipeline.py entry point (scrape-and-score + apply-tier1 subcommands)
  - DONE: Created .github/workflows/scrape-and-score.yml (daily cron 9 AM UTC + manual)
  - DONE: Created .github/workflows/apply-tier1.yml (daily cron 11 AM UTC + manual, burn-in default)
  - DONE: Updated main.py — removed run/review commands, kept intake/status/profile
  - DONE: Updated .env.example — added GITHUB_TOKEN/GITHUB_REPOSITORY refs, removed SMTP
  - DONE: Created data/jobs_seen.json (empty initial state file)
  - DONE: Updated README.md — full rewrite for Actions+Issues flow, required secrets, new structure
  - DONE: Updated Project_Architecture.md — new data flow, orchestration table, execution model, cost tracking
  - DONE: Created tests/test_issues_review.py (25 tests)
  - DONE: Created tests/test_run_pipeline.py (20 tests)
  - DONE: Updated tests/test_main_cli.py and tests/test_orchestrator.py for new API
  - DONE: All 350 tests passing
  - TODO: Git commit and push

## Phase 17 New/Modified Files:
- [NEW] .github/workflows/scrape-and-score.yml
- [NEW] .github/workflows/apply-tier1.yml
- [NEW] backend/issues_review/__init__.py
- [NEW] backend/issues_review/github_issues.py
- [NEW] run_pipeline.py
- [NEW] data/jobs_seen.json
- [NEW] tests/test_issues_review.py
- [NEW] tests/test_run_pipeline.py
- [MODIFIED] .gitignore, .env.example, pyproject.toml, requirements.txt
- [MODIFIED] backend/orchestrator.py, main.py
- [MODIFIED] README.md, Project_Architecture.md
- [MODIFIED] tests/test_main_cli.py, tests/test_orchestrator.py
- [DELETED] Dockerfile, docker-compose.yml, demo.py, Makefile, schedule.py, requirements-dev.txt

## Test Results: 350 passing

## User Details Collected:
- Name: Anshul Das
- Email: anshuldas42@gmail.com
- GitHub: https://github.com/AnshulDas007/Agentic-Job-Apply-Companion.git
- GitHub Username: AnshulDas007
- SSH key: configured and verified
- Git: configured (user.name + user.email)
- Resume: PDF ready (path not yet provided)
- LLM keys: Groq API key configured in .env
- Apify token: User has it (needed for Apify scrapers, not yet in .env)

## Phase 17 Architecture Notes:
- Execution runs entirely on GitHub Actions (no local machine, no server, no custom web app)
- Review interface is GitHub Issues — users approve/reject by labeling from web/mobile
- State persists via bot commits of data/jobs_seen.json back to the repo
- Secrets (API keys) go in Repo → Settings → Secrets, not .env, for CI
- Burn-in: apply-tier1 starts with --burn-in flag (dry-run) for first 2 weeks
- Tier 2 (LinkedIn/Indeed/Naukri) stays manual permanently — Issues opened with details for self-apply
