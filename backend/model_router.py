"""
Config-driven LLM model router.

Routes tasks to the appropriate provider/model based on tier configuration.
Supports fallback chains, exponential-backoff retries, and per-provider rate limiting.
"""

import os
import time
import logging
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

from backend.cost_tracker import CostTracker

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------

CONFIG_PATH = Path("config/model_config.yaml")


def load_model_config(path: Path = CONFIG_PATH) -> dict:
    """Load model routing configuration from YAML."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Rate limiter (simple token-bucket per provider)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Per-provider rate limiter using a sliding-window approach."""

    def __init__(self):
        self._call_timestamps: dict[str, list[float]] = {}

    def wait_if_needed(self, provider: str, rpm_limit: int) -> None:
        """Block until we're under the rate limit for this provider."""
        now = time.time()
        window = 60.0  # 1-minute window

        if provider not in self._call_timestamps:
            self._call_timestamps[provider] = []

        # Prune old timestamps outside the window
        self._call_timestamps[provider] = [
            ts for ts in self._call_timestamps[provider] if now - ts < window
        ]

        if len(self._call_timestamps[provider]) >= rpm_limit:
            oldest = self._call_timestamps[provider][0]
            sleep_time = window - (now - oldest) + 0.1
            if sleep_time > 0:
                logger.info("Rate limit reached for %s, sleeping %.1fs", provider, sleep_time)
                time.sleep(sleep_time)

        self._call_timestamps[provider].append(time.time())


# ---------------------------------------------------------------------------
# Provider adapters
# ---------------------------------------------------------------------------

def _call_groq(model: str, prompt: str, system_prompt: Optional[str],
               temperature: float, max_tokens: int, base_url: str, api_key: str) -> dict:
    """Call Groq API (OpenAI-compatible)."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    choice = response.choices[0]
    usage = response.usage
    return {
        "content": choice.message.content,
        "tokens_in": usage.prompt_tokens if usage else 0,
        "tokens_out": usage.completion_tokens if usage else 0,
        "model": model,
        "provider": "groq",
    }


def _call_openrouter(model: str, prompt: str, system_prompt: Optional[str],
                     temperature: float, max_tokens: int, base_url: str, api_key: str) -> dict:
    """Call OpenRouter API (OpenAI-compatible)."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    choice = response.choices[0]
    usage = response.usage
    return {
        "content": choice.message.content,
        "tokens_in": usage.prompt_tokens if usage else 0,
        "tokens_out": usage.completion_tokens if usage else 0,
        "model": model,
        "provider": "openrouter",
    }


def _call_google(model: str, prompt: str, system_prompt: Optional[str],
                 temperature: float, max_tokens: int, api_key: str, **kwargs) -> dict:
    """Call Google Generative AI API."""
    from google import genai

    client = genai.Client(api_key=api_key)

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
        config={
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        },
    )

    # Estimate tokens (Google API may not always return exact counts)
    tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) if response.usage_metadata else 0
    tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) if response.usage_metadata else 0

    return {
        "content": response.text,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "model": model,
        "provider": "google",
    }


def _call_ollama(model: str, prompt: str, system_prompt: Optional[str],
                 temperature: float, max_tokens: int, base_url: str, **kwargs) -> dict:
    """Call local Ollama instance (OpenAI-compatible API)."""
    from openai import OpenAI

    client = OpenAI(api_key="ollama", base_url=f"{base_url}/v1")
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    choice = response.choices[0]
    usage = response.usage
    return {
        "content": choice.message.content,
        "tokens_in": usage.prompt_tokens if usage else 0,
        "tokens_out": usage.completion_tokens if usage else 0,
        "model": model,
        "provider": "ollama",
    }


PROVIDER_CALLERS = {
    "groq": _call_groq,
    "openrouter": _call_openrouter,
    "google": _call_google,
    "ollama": _call_ollama,
}


# ---------------------------------------------------------------------------
# Model Router
# ---------------------------------------------------------------------------

class ModelRouter:
    """
    Routes LLM calls to the appropriate provider based on task tier.

    Usage:
        router = ModelRouter()
        result = router.complete("parsing", "Extract fields from this resume...",
                                 system_prompt="You are a resume parser.")
    """

    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config = load_model_config(config_path)
        self.rate_limiter = RateLimiter()
        self.cost_tracker = CostTracker()
        self._retry_config = self.config.get("retry", {})

    def _get_provider_config(self, provider_name: str) -> dict:
        """Get provider-level settings (base_url, env_key, rate limits)."""
        return self.config.get("providers", {}).get(provider_name, {})

    def _get_api_key(self, provider_config: dict) -> Optional[str]:
        """Resolve the API key from environment variables."""
        env_key = provider_config.get("env_key")
        if env_key:
            key = os.getenv(env_key, "")
            return key if key else None
        return None

    def _get_base_url(self, provider_name: str, provider_config: dict) -> str:
        """Resolve the base URL for a provider."""
        # Some providers use env-based URL (e.g., Ollama)
        base_url_env = provider_config.get("base_url_env")
        if base_url_env:
            return os.getenv(base_url_env, provider_config.get("default_base_url", ""))
        return provider_config.get("base_url", "")

    def _build_call_chain(self, tier: str) -> list[dict]:
        """Build the ordered list of provider/model configs to try (primary + fallbacks)."""
        tier_config = self.config.get("tiers", {}).get(tier)
        if not tier_config:
            raise ValueError(f"Unknown tier: '{tier}'. Available: {list(self.config.get('tiers', {}).keys())}")

        chain = [tier_config["primary"]]
        chain.extend(tier_config.get("fallbacks", []))
        return chain

    def _attempt_call(self, provider_name: str, model_config: dict,
                      prompt: str, system_prompt: Optional[str]) -> dict:
        """Attempt a single LLM call to a specific provider/model."""
        provider_config = self._get_provider_config(provider_name)
        rpm_limit = provider_config.get("rate_limit_rpm", 60)

        # Rate limit
        self.rate_limiter.wait_if_needed(provider_name, rpm_limit)

        # Resolve credentials and URL
        api_key = self._get_api_key(provider_config)
        base_url = self._get_base_url(provider_name, provider_config)

        caller = PROVIDER_CALLERS.get(provider_name)
        if not caller:
            raise ValueError(f"No caller implemented for provider: {provider_name}")

        # Check API key (except Ollama which doesn't need one)
        if provider_name != "ollama" and not api_key:
            raise ValueError(f"No API key found for provider '{provider_name}' (env: {provider_config.get('env_key')})")

        # Build kwargs
        call_kwargs: dict[str, Any] = {
            "model": model_config["model"],
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": model_config.get("temperature", 0.1),
            "max_tokens": model_config.get("max_tokens", 2048),
        }
        if base_url:
            call_kwargs["base_url"] = base_url
        if api_key:
            call_kwargs["api_key"] = api_key

        start_time = time.time()
        result = caller(**call_kwargs)
        latency_ms = (time.time() - start_time) * 1000

        # Log to cost tracker
        self.cost_tracker.log_llm_call(
            provider=result["provider"],
            model=result["model"],
            tokens_in=result["tokens_in"],
            tokens_out=result["tokens_out"],
            latency_ms=latency_ms,
        )

        result["latency_ms"] = latency_ms
        return result

    def complete(
        self,
        tier: str,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """
        Route an LLM call through the tier's provider chain.

        Args:
            tier: Task tier name (e.g., "parsing", "classification", "cover_letter")
            prompt: The user prompt to send
            system_prompt: Optional system prompt

        Returns:
            dict with keys: content, tokens_in, tokens_out, model, provider, latency_ms

        Raises:
            RuntimeError: If all providers in the chain fail
        """
        chain = self._build_call_chain(tier)
        max_retries = self._retry_config.get("max_retries", 3)
        base_delay = self._retry_config.get("base_delay_seconds", 1.0)
        max_delay = self._retry_config.get("max_delay_seconds", 30.0)
        exp_base = self._retry_config.get("exponential_base", 2.0)

        errors = []

        for i, model_config in enumerate(chain):
            provider_name = model_config["provider"]
            model_name = model_config["model"]

            for attempt in range(max_retries):
                try:
                    logger.info(
                        "Tier '%s' → %s/%s (attempt %d/%d)",
                        tier, provider_name, model_name, attempt + 1, max_retries,
                    )
                    return self._attempt_call(provider_name, model_config, prompt, system_prompt)

                except Exception as e:
                    delay = min(base_delay * (exp_base ** attempt), max_delay)
                    error_msg = f"{provider_name}/{model_name} attempt {attempt + 1}: {e}"
                    errors.append(error_msg)
                    logger.warning("%s — retrying in %.1fs", error_msg, delay)

                    if attempt < max_retries - 1:
                        time.sleep(delay)

            logger.warning("All retries exhausted for %s/%s, trying next fallback", provider_name, model_name)

        raise RuntimeError(
            f"All providers failed for tier '{tier}'.\nErrors:\n" + "\n".join(errors)
        )

    def list_tiers(self) -> dict[str, str]:
        """Return available tiers with their descriptions."""
        tiers = self.config.get("tiers", {})
        return {name: cfg.get("description", "") for name, cfg in tiers.items()}
