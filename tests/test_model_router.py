"""
Tests for the model router and cost tracker.
"""

import os
import csv
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.model_router import ModelRouter, load_model_config, RateLimiter, PROVIDER_CALLERS
from backend.cost_tracker import CostTracker


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestConfigLoading:
    def test_load_model_config(self):
        config = load_model_config()
        assert "tiers" in config
        assert "providers" in config
        assert "retry" in config

    def test_tiers_present(self):
        config = load_model_config()
        expected_tiers = ["parsing", "classification", "scoring", "fraud_analysis", "cover_letter", "legal_review"]
        for tier in expected_tiers:
            assert tier in config["tiers"], f"Missing tier: {tier}"

    def test_each_tier_has_primary(self):
        config = load_model_config()
        for tier_name, tier_config in config["tiers"].items():
            assert "primary" in tier_config, f"Tier '{tier_name}' missing primary"
            assert "provider" in tier_config["primary"]
            assert "model" in tier_config["primary"]

    def test_providers_have_required_fields(self):
        config = load_model_config()
        for name, pconfig in config["providers"].items():
            if name != "ollama":
                assert "env_key" in pconfig, f"Provider '{name}' missing env_key"


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_no_wait_under_limit(self):
        rl = RateLimiter()
        # Should not block with 1 call at 30 RPM
        rl.wait_if_needed("groq", 30)

    def test_tracks_calls(self):
        rl = RateLimiter()
        rl.wait_if_needed("groq", 1000)
        rl.wait_if_needed("groq", 1000)
        assert len(rl._call_timestamps["groq"]) == 2


# ---------------------------------------------------------------------------
# Cost tracker
# ---------------------------------------------------------------------------

class TestCostTracker:
    def test_creates_csv(self, tmp_path):
        log_path = tmp_path / "test_usage.csv"
        tracker = CostTracker(log_path=log_path)
        assert log_path.exists()

        # Verify headers
        with open(log_path, "r") as f:
            reader = csv.reader(f)
            headers = next(reader)
            assert "timestamp" in headers
            assert "provider" in headers

    def test_log_llm_call(self, tmp_path):
        log_path = tmp_path / "test_usage.csv"
        tracker = CostTracker(log_path=log_path)
        tracker.log_llm_call(
            provider="groq",
            model="qwen/qwen3.6-27b",
            tokens_in=100,
            tokens_out=50,
            latency_ms=250.5,
        )

        with open(log_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["service"] == "llm"
            assert rows[0]["provider"] == "groq"
            assert int(rows[0]["tokens_in"]) == 100

    def test_log_apify_run(self, tmp_path):
        log_path = tmp_path / "test_usage.csv"
        tracker = CostTracker(log_path=log_path)
        tracker.log_apify_run(actor_name="linkedin-scraper", compute_units=0.05)

        with open(log_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["service"] == "apify"

    def test_get_summary(self, tmp_path):
        log_path = tmp_path / "test_usage.csv"
        tracker = CostTracker(log_path=log_path)

        tracker.log_llm_call(provider="groq", model="test", tokens_in=100, tokens_out=50)
        tracker.log_llm_call(provider="groq", model="test", tokens_in=200, tokens_out=100)
        tracker.log_apify_run(actor_name="test-actor", compute_units=0.1)

        summary = tracker.get_summary()
        assert summary["total_llm_calls"] == 2
        assert summary["total_apify_runs"] == 1
        assert summary["total_tokens_in"] == 300
        assert summary["total_tokens_out"] == 150
        assert "groq" in summary["by_provider"]


# ---------------------------------------------------------------------------
# Model router (mocked providers)
# ---------------------------------------------------------------------------

class TestModelRouter:
    def test_list_tiers(self):
        router = ModelRouter()
        tiers = router.list_tiers()
        assert "parsing" in tiers
        assert "cover_letter" in tiers

    def test_unknown_tier_raises(self):
        router = ModelRouter()
        with pytest.raises(ValueError, match="Unknown tier"):
            router.complete("nonexistent_tier", "test prompt")

    def test_build_call_chain(self):
        router = ModelRouter()
        chain = router._build_call_chain("parsing")
        assert len(chain) >= 1
        assert chain[0]["provider"] == "groq"  # Primary for parsing

    def test_complete_calls_primary(self, tmp_path):
        """Test that complete() calls the primary provider via PROVIDER_CALLERS dict."""
        mock_caller = MagicMock(return_value={
            "content": "test response",
            "tokens_in": 10,
            "tokens_out": 5,
            "model": "qwen/qwen3.6-27b",
            "provider": "groq",
        })

        router = ModelRouter()
        router.cost_tracker = CostTracker(log_path=tmp_path / "test_cost.csv")

        # Patch the PROVIDER_CALLERS dict entry directly
        original = PROVIDER_CALLERS["groq"]
        PROVIDER_CALLERS["groq"] = mock_caller
        try:
            result = router.complete("parsing", "Extract fields from this text")
            assert result["content"] == "test response"
            assert result["provider"] == "groq"
            mock_caller.assert_called_once()
        finally:
            PROVIDER_CALLERS["groq"] = original

    def test_fallback_on_primary_failure(self, tmp_path):
        """Test that when primary fails, the fallback is tried."""
        mock_primary = MagicMock(side_effect=Exception("API error"))
        mock_fallback = MagicMock(return_value={
            "content": "fallback response",
            "tokens_in": 10,
            "tokens_out": 5,
            "model": "openai/gpt-oss-20b",
            "provider": "groq",
        })

        router = ModelRouter()
        router.cost_tracker = CostTracker(log_path=tmp_path / "test_cost.csv")

        # The parsing tier has groq as both primary and fallback (different models)
        # We need to make it fail on first model, succeed on second
        call_count = 0
        def smart_mock(**kwargs):
            nonlocal call_count
            call_count += 1
            model = kwargs.get("model", "")
            if model == "qwen/qwen3.6-27b":
                raise Exception("API error")
            return {
                "content": "fallback response",
                "tokens_in": 10,
                "tokens_out": 5,
                "model": model,
                "provider": "groq",
            }

        original = PROVIDER_CALLERS["groq"]
        PROVIDER_CALLERS["groq"] = smart_mock
        try:
            result = router.complete("parsing", "test prompt")
            assert result["content"] == "fallback response"
        finally:
            PROVIDER_CALLERS["groq"] = original


# ---------------------------------------------------------------------------
# Live integration test (only runs if GROQ_API_KEY is set)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.getenv("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live integration test"
)
class TestModelRouterLive:
    def test_live_groq_call(self, tmp_path):
        router = ModelRouter()
        router.cost_tracker = CostTracker(log_path=tmp_path / "live_test_usage.csv")

        result = router.complete(
            "parsing",
            "Respond with exactly the word 'PONG' and nothing else.",
            system_prompt="You are a simple echo bot.",
        )

        assert result["content"] is not None
        assert len(result["content"]) > 0
        assert result["provider"] == "groq"
        assert result["tokens_in"] > 0
        assert result["latency_ms"] > 0
