"""PolicyStore — holds the live PolicyConfig and hot-reloads it from YAML.

The Policy Engine (policy.py) stays PURE (no I/O); this store is the thin,
impure boundary that owns loading/reloading. The service reads the current
config through `store.get` (passed as its policy_provider), so a reload takes
effect on the next request with no restart and no code change.
"""

from __future__ import annotations

from pathlib import Path

from .policy import PolicyConfig

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


class PolicyStore:
    def __init__(self, path: str | None = None) -> None:
        self._path = path
        self._config = PolicyConfig()
        if path:
            self.reload()

    def get(self) -> PolicyConfig:
        return self._config

    def set(self, config: PolicyConfig) -> None:
        self._config = config

    def reload(self) -> PolicyConfig:
        """Re-read the YAML file into a fresh PolicyConfig. No-op if unavailable."""
        if not self._path or yaml is None:
            return self._config
        p = Path(self._path)
        if not p.exists():
            return self._config
        with p.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        self._config = PolicyConfig.from_dict(data.get("policy", data))
        return self._config
