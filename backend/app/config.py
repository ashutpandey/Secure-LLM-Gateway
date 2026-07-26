"""App configuration — env-validated, with a YAML overlay for guardrail modes.

Secrets (provider keys) come from the environment; they must NEVER reach the
client. The guardrails.yaml overlay sets each detector's initial mode/weight so
you can ship a config change without touching code.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pyyaml optional at import time
    yaml = None

_BASE = Path(__file__).resolve().parent.parent


class Settings:
    def __init__(self) -> None:
        self.demo_mode = os.getenv("DEMO_MODE", "true").lower() != "false"
        # Control-plane writes (PATCH /registry) change what is ENFORCED, so they
        # are safe-by-default: allowed in DEMO_MODE, OFF in prod unless explicitly
        # enabled (and then they still belong behind admin-RBAC — see Cycle 4).
        self.allow_control_plane_writes = os.getenv(
            "ALLOW_CONTROL_PLANE_WRITES", "true" if self.demo_mode else "false"
        ).lower() == "true"
        self.cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        self.per_detector_timeout_s = float(os.getenv("DETECTOR_TIMEOUT_S", "2.0"))
        self.provider_timeout_s = float(os.getenv("PROVIDER_TIMEOUT_S", "4.0"))
        # Guardrail Service hardening (Cycle 2).
        self.guardrail_strategy = os.getenv("GUARDRAIL_STRATEGY", "parallel")  # parallel | cascade
        self.cache_enabled = os.getenv("SIGNAL_CACHE_ENABLED", "true").lower() != "false"
        self.cache_max_entries = int(os.getenv("SIGNAL_CACHE_MAX", "2048"))
        self.cache_ttl_s = float(os.getenv("SIGNAL_CACHE_TTL_S", "300"))
        self.circuit_failure_threshold = int(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "5"))
        self.circuit_reset_timeout_s = float(os.getenv("CIRCUIT_RESET_TIMEOUT_S", "30"))
        # Secrets (used once real providers land in Cycle 4).
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        # ML guardrail sidecar (Cycle 6). Empty -> ML detectors are unavailable
        # (they fail-open, so the regex detectors remain the enforced baseline).
        self.ml_service_url = os.getenv("ML_SERVICE_URL", "").rstrip("/")
        self.ml_timeout_s = float(os.getenv("ML_TIMEOUT_S", "1.5"))
        # --- Cycle 7: providers, limits, durable audit, tenancy ---------------
        # PROVIDER_CHAIN sets the failover order, e.g. "openai,anthropic,mock".
        # Empty -> the default two-mock chain (keyless demo + tests).
        self.provider_chain = [
            p.strip() for p in os.getenv("PROVIDER_CHAIN", "").split(",") if p.strip()
        ]
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
        # Rate limit: token bucket per tenant (requests). Budget: tokens/day/tenant.
        self.rate_capacity = int(os.getenv("RATE_CAPACITY", "30"))
        self.rate_refill_per_s = float(os.getenv("RATE_REFILL_PER_S", "0.5"))
        self.token_budget_per_day = int(os.getenv("TOKEN_BUDGET_PER_DAY", "200000"))
        # Durable audit: a sqlite path makes the audit survive restarts. Empty ->
        # in-memory only (bounded, non-durable).
        self.audit_db = os.getenv("AUDIT_DB", "").strip()
        # Admin API key gates control-plane writes (in addition to the demo flag).
        self.admin_api_key = os.getenv("ADMIN_API_KEY", "").strip()
        # --- Cycle 8: plugin safety / blast radius ---------------------------
        # Data residency: when false, detectors that send data off-box
        # (egress="external", e.g. a hosted moderation API) are skipped.
        self.allow_external_egress = os.getenv("ALLOW_EXTERNAL_EGRESS", "true").lower() != "false"
        self.max_input_chars = int(os.getenv("MAX_INPUT_CHARS", "16000"))
        self.guardrails_config_path = os.getenv(
            "GUARDRAILS_CONFIG", str(_BASE / "app" / "guardrails.yaml")
        )
        self.policy_config_path = os.getenv(
            "POLICY_CONFIG", str(_BASE / "app" / "policy.yaml")
        )

    def load_guardrails_config(self) -> dict:
        path = Path(self.guardrails_config_path)
        if yaml is None or not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data.get("detectors", {})


@lru_cache
def get_settings() -> Settings:
    return Settings()
