"""
Cost tracker for LLM and scraping usage.

Logs every LLM call and Apify run to a CSV file for spend visibility.
Thread-safe via file locking.
"""

import csv
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

USAGE_LOG_PATH = Path("data/usage_log.csv")

CSV_HEADERS = [
    "timestamp",
    "service",      # "llm" or "apify"
    "provider",
    "model",
    "tokens_in",
    "tokens_out",
    "latency_ms",
    "cost_estimate",
    "notes",
]

# Approximate cost per 1M tokens for free-tier providers (all $0 for free tiers)
COST_PER_1M_TOKENS = {
    "groq": {"input": 0.0, "output": 0.0},        # Free tier
    "openrouter": {"input": 0.0, "output": 0.0},   # Free models
    "google": {"input": 0.0, "output": 0.0},        # Free tier
    "ollama": {"input": 0.0, "output": 0.0},        # Local
}


class CostTracker:
    """
    Thread-safe CSV logger for LLM and scraping usage.

    All costs should be $0 on free tiers, but we track token counts
    and latency for visibility and capacity planning.
    """

    _lock = threading.Lock()

    def __init__(self, log_path: Path = USAGE_LOG_PATH):
        self.log_path = log_path
        self._ensure_csv()

    def _ensure_csv(self) -> None:
        """Create the CSV file with headers if it doesn't exist."""
        os.makedirs(self.log_path.parent, exist_ok=True)
        if not self.log_path.exists():
            with open(self.log_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADERS)

    def _append_row(self, row: list) -> None:
        """Thread-safe append of a single row to the CSV."""
        with self._lock:
            with open(self.log_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row)

    def log_llm_call(
        self,
        provider: str,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: float = 0.0,
        notes: str = "",
    ) -> None:
        """Log a single LLM API call."""
        cost = self._estimate_cost(provider, tokens_in, tokens_out)
        self._append_row([
            datetime.now(timezone.utc).isoformat(),
            "llm",
            provider,
            model,
            tokens_in,
            tokens_out,
            f"{latency_ms:.1f}",
            f"{cost:.6f}",
            notes,
        ])

    def log_apify_run(
        self,
        actor_name: str,
        compute_units: float = 0.0,
        cost_usd: float = 0.0,
        notes: str = "",
    ) -> None:
        """Log a single Apify actor run."""
        self._append_row([
            datetime.now(timezone.utc).isoformat(),
            "apify",
            "apify",
            actor_name,
            0,  # tokens_in (N/A)
            0,  # tokens_out (N/A)
            0,  # latency_ms (N/A)
            f"{cost_usd:.6f}",
            f"CU={compute_units:.4f}; {notes}" if notes else f"CU={compute_units:.4f}",
        ])

    def _estimate_cost(self, provider: str, tokens_in: int, tokens_out: int) -> float:
        """Estimate cost in USD based on provider pricing."""
        pricing = COST_PER_1M_TOKENS.get(provider, {"input": 0.0, "output": 0.0})
        cost_in = (tokens_in / 1_000_000) * pricing["input"]
        cost_out = (tokens_out / 1_000_000) * pricing["output"]
        return cost_in + cost_out

    def get_summary(self) -> dict:
        """
        Read the usage log and return a summary.

        Returns dict with:
            total_llm_calls, total_apify_runs, total_tokens_in,
            total_tokens_out, total_cost_estimate, by_provider
        """
        summary = {
            "total_llm_calls": 0,
            "total_apify_runs": 0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_cost_estimate": 0.0,
            "by_provider": {},
        }

        if not self.log_path.exists():
            return summary

        with open(self.log_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                service = row.get("service", "")
                provider = row.get("provider", "")

                if service == "llm":
                    summary["total_llm_calls"] += 1
                    tokens_in = int(row.get("tokens_in", 0))
                    tokens_out = int(row.get("tokens_out", 0))
                    summary["total_tokens_in"] += tokens_in
                    summary["total_tokens_out"] += tokens_out

                    if provider not in summary["by_provider"]:
                        summary["by_provider"][provider] = {"calls": 0, "tokens_in": 0, "tokens_out": 0}
                    summary["by_provider"][provider]["calls"] += 1
                    summary["by_provider"][provider]["tokens_in"] += tokens_in
                    summary["by_provider"][provider]["tokens_out"] += tokens_out

                elif service == "apify":
                    summary["total_apify_runs"] += 1

                cost = float(row.get("cost_estimate", 0.0))
                summary["total_cost_estimate"] += cost

        return summary
