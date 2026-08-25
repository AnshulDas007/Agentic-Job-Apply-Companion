# Build Progress Tracker
# ============================================================
# This file tracks build progress for token continuity.
# If the conversation is interrupted, start a new conversation
# and say "continue building" — the agent will read this file
# and pick up exactly where it left off.
# ============================================================

## Current Phase: 7
## Current Step: Cover Letter Generation Module
## Status: NOT_STARTED
## Last Completed: Phase 6 (Matching/Relevance Scoring Layer)
## Next Action: Build backend/cover_letter/generator.py, templates, tests
## Blockers: None

## Completed Phases:
- Phase 1: Docs, scaffolding, git push, env setup, Groq API key added
- Phase 2: CandidateProfile schema, profile store, manage_profile CLI, tests
- Phase 3: Model router (config-driven, fallback chains, rate limiting), cost tracker, tests + live Groq integration verified
- Phase 4: Scraping layer (Apify, Greenhouse/Lever/Ashby ATS, YC Jobs), job schema, scraper registry, tests
- Phase 5: Fraud filter (hard blockers + soft-signal scoring), signal checkers, tests
- Phase 6: Matching layer (embeddings via sentence-transformers, ChromaDB vector store, multi-signal relevance scorer with skill/experience/location/embedding scoring), tests

## Files Created:
- .gitignore
- .env.example
- pyproject.toml
- requirements.txt
- requirements-dev.txt
- Makefile
- docker-compose.yml
- Dockerfile
- backend/__init__.py
- backend/model_router.py
- backend/cost_tracker.py
- backend/parsing/__init__.py
- backend/parsing/profile_schema.py
- backend/parsing/profile_store.py
- backend/scrapers/__init__.py
- backend/scrapers/job_schema.py
- backend/scrapers/base_scraper.py
- backend/scrapers/apify_scraper.py
- backend/scrapers/ats_scraper.py
- backend/scrapers/yc_scraper.py
- backend/scrapers/scraper_registry.py
- backend/fraud_filter/__init__.py
- backend/fraud_filter/filter.py
- backend/fraud_filter/signals.py
- backend/matching/__init__.py
- backend/matching/embeddings.py
- backend/matching/vector_store.py
- backend/matching/scorer.py
- backend/form_filler/__init__.py
- backend/form_filler/ats_handlers/__init__.py
- backend/cover_letter/__init__.py
- backend/legal_review/__init__.py
- config/model_config.yaml
- config/app_config.yaml
- config/matching_config.yaml
- manage_profile.py
- tests/__init__.py
- tests/test_profile_schema.py
- tests/test_model_router.py
- tests/test_scrapers.py
- tests/test_fraud_filter.py
- tests/test_matching.py
- PROGRESS_TRACKER.md

## Commit History:
- chore: project scaffolding, environment config, and dependency pinning
- docs: README, architecture doc, and product requirements document
- feat: candidate profile schema, store, and CLI manager
- test: profile schema validation tests
- feat: config-driven model router with fallback chains and cost tracking
- test: model router unit tests and live Groq integration test
- feat: scraping layer with Apify, ATS, and YC scrapers
- test: scraping layer unit tests
- feat: fraud filter with hard-blocker and scored legitimacy checks
- test: fraud filter hard-blocker detection and soft-signal scoring
- feat: matching/relevance scoring layer with embeddings, vector store, and multi-signal scorer

## Test Results: 134/134 passing

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

## Model Config Notes:
- Groq models updated to current availability: qwen/qwen3.6-27b (small/mid), openai/gpt-oss-120b (best)
- llama-3.3-70b-versatile is no longer available on Groq
- Live Groq integration test confirmed working

## Phase 6 Architecture Notes:
- EmbeddingManager: lazy-loads sentence-transformers all-MiniLM-L6-v2 (~80MB)
- VectorStore: ChromaDB PersistentClient with cosine distance, deduplication via URL hash
- RelevanceScorer: 4-signal weighted scoring (embedding_similarity=0.40, skill_match=0.30, experience_relevance=0.20, location_fit=0.10)
- Two-stage pipeline: fast embedding pre-filter (threshold=0.35) then full scoring
- ChromaDB 1.0+ compatibility: metadata always non-empty dict
- Skill normalization with 20+ aliases (JS→javascript, k8s→kubernetes, etc.)
