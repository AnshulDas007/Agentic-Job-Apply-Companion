"""
Tests for the SQLite database module.

Tests table creation, CRUD operations, audit logging, and usage tracking.
Uses a temporary in-memory database for isolation.
"""

import pytest
from pathlib import Path

from backend.database import Database


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    yield database
    database.close()


# ---------------------------------------------------------------------------
# Tests: Database initialization
# ---------------------------------------------------------------------------

class TestDatabaseInit:
    def test_creates_database_file(self, tmp_path):
        db_path = tmp_path / "subdir" / "test.db"
        database = Database(db_path)
        assert db_path.exists()
        database.close()

    def test_tables_exist(self, db):
        conn = db._get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t["name"] for t in tables}
        assert "jobs" in table_names
        assert "applications" in table_names
        assert "audit_trail" in table_names
        assert "usage_log" in table_names


# ---------------------------------------------------------------------------
# Tests: Jobs CRUD
# ---------------------------------------------------------------------------

class TestJobsCRUD:
    def test_insert_and_get_job(self, db):
        job_id = db.insert_job({
            "id": "job-001",
            "title": "Backend Engineer",
            "company": "Stripe",
            "url": "https://stripe.com/jobs/001",
            "source": "greenhouse",
        })
        assert job_id == "job-001"

        job = db.get_job("job-001")
        assert job is not None
        assert job["title"] == "Backend Engineer"
        assert job["company"] == "Stripe"
        assert job["status"] == "scraped"

    def test_get_nonexistent_job(self, db):
        assert db.get_job("nonexistent") is None

    def test_update_job_status(self, db):
        db.insert_job({
            "id": "job-002",
            "title": "SDE",
            "company": "Google",
            "url": "https://google.com/jobs/002",
        })
        db.update_job_status("job-002", "applied", relevance_score=0.85)

        job = db.get_job("job-002")
        assert job["status"] == "applied"
        assert job["relevance_score"] == 0.85

    def test_get_jobs_by_status(self, db):
        db.insert_job({"id": "j1", "title": "A", "company": "C1", "url": "u1", "status": "scraped"})
        db.insert_job({"id": "j2", "title": "B", "company": "C2", "url": "u2", "status": "applied"})
        db.insert_job({"id": "j3", "title": "C", "company": "C3", "url": "u3", "status": "scraped"})

        scraped = db.get_jobs(status="scraped")
        assert len(scraped) == 2
        applied = db.get_jobs(status="applied")
        assert len(applied) == 1

    def test_get_all_jobs(self, db):
        db.insert_job({"id": "j1", "title": "A", "company": "C1", "url": "u1"})
        db.insert_job({"id": "j2", "title": "B", "company": "C2", "url": "u2"})

        all_jobs = db.get_jobs()
        assert len(all_jobs) == 2

    def test_upsert_job(self, db):
        """INSERT OR REPLACE should update existing records."""
        db.insert_job({
            "id": "j1", "title": "Engineer", "company": "Old", "url": "u1"
        })
        db.insert_job({
            "id": "j1", "title": "Engineer", "company": "New", "url": "u1"
        })
        job = db.get_job("j1")
        assert job["company"] == "New"


# ---------------------------------------------------------------------------
# Tests: Applications CRUD
# ---------------------------------------------------------------------------

class TestApplicationsCRUD:
    def test_insert_and_get_application(self, db):
        db.insert_job({"id": "j1", "title": "SDE", "company": "C", "url": "u"})
        app_id = db.insert_application({
            "id": "app-001",
            "job_id": "j1",
            "tier": "tier_1",
            "status": "submitted",
        })
        assert app_id == "app-001"

        apps = db.get_applications()
        assert len(apps) == 1
        assert apps[0]["tier"] == "tier_1"
        assert apps[0]["status"] == "submitted"

    def test_update_application_status(self, db):
        db.insert_job({"id": "j1", "title": "SDE", "company": "C", "url": "u"})
        db.insert_application({
            "id": "app-001",
            "job_id": "j1",
            "status": "pending",
        })

        db.update_application_status(
            "app-001", "submitted",
            notes="Auto-submitted via Tier 1"
        )

        apps = db.get_applications(status="submitted")
        assert len(apps) == 1
        assert apps[0]["notes"] == "Auto-submitted via Tier 1"

    def test_filter_applications_by_status(self, db):
        db.insert_job({"id": "j1", "title": "A", "company": "C", "url": "u"})
        db.insert_application({"id": "a1", "job_id": "j1", "status": "pending"})
        db.insert_application({"id": "a2", "job_id": "j1", "status": "submitted"})
        db.insert_application({"id": "a3", "job_id": "j1", "status": "pending"})

        pending = db.get_applications(status="pending")
        assert len(pending) == 2


# ---------------------------------------------------------------------------
# Tests: Audit Trail
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_log_and_retrieve(self, db):
        entry_id = db.log_audit(
            action="scrape",
            target="linkedin",
            details="Scraped 50 jobs",
            result="success",
        )
        assert entry_id is not None
        assert entry_id > 0

        trail = db.get_audit_trail()
        assert len(trail) == 1
        assert trail[0]["action"] == "scrape"
        assert trail[0]["target"] == "linkedin"
        assert trail[0]["result"] == "success"

    def test_multiple_entries_ordered(self, db):
        db.log_audit(action="first", target="t1")
        db.log_audit(action="second", target="t2")
        db.log_audit(action="third", target="t3")

        trail = db.get_audit_trail()
        assert len(trail) == 3
        # Most recent first (ORDER BY id DESC)
        assert trail[0]["action"] == "third"
        assert trail[2]["action"] == "first"


# ---------------------------------------------------------------------------
# Tests: Usage Logging
# ---------------------------------------------------------------------------

class TestUsageLogging:
    def test_log_and_summarize(self, db):
        db.log_usage(service="groq", model="llama3", tokens_in=100, tokens_out=50)
        db.log_usage(service="groq", model="llama3", tokens_in=200, tokens_out=100)

        summary = db.get_usage_summary()
        assert summary["total_calls"] == 2
        assert summary["total_tokens_in"] == 300
        assert summary["total_tokens_out"] == 150

    def test_usage_by_service(self, db):
        db.log_usage(service="groq", model="llama3", tokens_in=100, tokens_out=50)
        db.log_usage(service="apify", model="", tokens_in=0, tokens_out=0, cost_estimate=0.01)
        db.log_usage(service="groq", model="llama3", tokens_in=200, tokens_out=100)

        by_service = db.get_usage_by_service()
        assert len(by_service) == 2

        groq_entry = next(s for s in by_service if s["service"] == "groq")
        assert groq_entry["call_count"] == 2
        assert groq_entry["total_tokens_in"] == 300


# ---------------------------------------------------------------------------
# Tests: Statistics
# ---------------------------------------------------------------------------

class TestStatistics:
    def test_get_stats(self, db):
        db.insert_job({"id": "j1", "title": "A", "company": "C1", "url": "u1", "status": "scraped"})
        db.insert_job({"id": "j2", "title": "B", "company": "C2", "url": "u2", "status": "applied"})
        db.insert_application({"id": "a1", "job_id": "j1", "status": "submitted"})
        db.log_usage(service="groq", tokens_in=100, tokens_out=50)

        stats = db.get_stats()
        assert stats["jobs"]["scraped"] == 1
        assert stats["jobs"]["applied"] == 1
        assert stats["applications"]["submitted"] == 1
        assert stats["usage"]["total_calls"] == 1
