"""Runtime config service: SQLite settings plus OS keychain keys."""
from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from ..schemas.config import ROLE_NAMES, AppConfig
from ..stores.sqlite.runtime_store import RuntimeStore

_KEYCHAIN_SERVICE = "theorise-backend"
_SECRET_EXCLUDE = {
    role: {"api_key"}
    for role in ROLE_NAMES
}


class KeyVault:
    """Stores API keys in the OS keychain, falling back to process memory."""

    def __init__(self) -> None:
        self._memory: dict[str, str] = {}
        self._available: bool | None = None
        self._warning: str | None = None

    @property
    def available(self) -> bool:
        if self._available is None:
            self._probe()
        return bool(self._available)

    @property
    def warning(self) -> str | None:
        if self._available is None:
            self._probe()
        return self._warning

    def _probe(self) -> None:
        try:
            import keyring  # type: ignore[import-not-found]

            keyring.get_keyring()
            self._available = True
        except Exception:
            self._available = False
            self._warning = (
                "OS keychain is unavailable; API keys are kept in memory "
                "for this session and are lost when the backend exits."
            )

    def get(self, role: str) -> str | None:
        if self.available:
            try:
                import keyring  # type: ignore[import-not-found]

                value = keyring.get_password(_KEYCHAIN_SERVICE, role)
                if value:
                    return value
            except Exception:
                self._available = False
                self._warning = (
                    "OS keychain failed; API keys are kept in memory "
                    "for this session and are lost when the backend exits."
                )
        return self._memory.get(role)

    def set(self, role: str, value: str) -> None:
        if self.available:
            try:
                import keyring  # type: ignore[import-not-found]

                keyring.set_password(_KEYCHAIN_SERVICE, role, value)
                self._memory.pop(role, None)
                return
            except Exception:
                self._available = False
                self._warning = (
                    "OS keychain failed; API keys are kept in memory "
                    "for this session and are lost when the backend exits."
                )
        self._memory[role] = value

    def delete(self, role: str) -> None:
        if self.available:
            try:
                import keyring  # type: ignore[import-not-found]

                keyring.delete_password(_KEYCHAIN_SERVICE, role)
            except Exception:
                pass
        self._memory.pop(role, None)

    def has(self, role: str) -> bool:
        return self.get(role) is not None


class ConfigService:
    """Loads, saves and masks the runtime model configuration."""

    def __init__(self, data_dir: str | Path) -> None:
        self.runtime_store = RuntimeStore(data_dir)
        self.vault = KeyVault()

    def load(self) -> AppConfig:
        config = self.runtime_store.load_config() or AppConfig()
        for role in ROLE_NAMES:
            role_obj = getattr(config, role)
            key = self.vault.get(role)
            role_obj.api_key = SecretStr(key) if key else None
        return config

    def save(self, payload: dict) -> AppConfig:
        incoming = AppConfig.model_validate(payload)
        existing = self.load()
        merged = existing.model_copy(deep=True)

        for role in ROLE_NAMES:
            role_payload = payload.get(role)
            if not isinstance(role_payload, dict):
                continue
            incoming_obj = getattr(incoming, role)
            merged_obj = getattr(merged, role)

            for field in type(incoming_obj).model_fields:
                if field == "api_key":
                    continue
                if field in role_payload:
                    setattr(merged_obj, field, getattr(incoming_obj, field))

            if "api_key" in role_payload:
                raw = role_payload["api_key"]
                if raw is None or raw == "":
                    self.vault.delete(role)
                    merged_obj.api_key = None
                else:
                    self.vault.set(role, str(raw))
                    merged_obj.api_key = SecretStr(str(raw))

        for field in ("concurrency", "token_budget_per_job"):
            if field in payload:
                setattr(merged, field, getattr(incoming, field))

        self.runtime_store.save_config(merged)
        return merged

    def public_config(self) -> dict:
        config = self.load()
        data = config.model_dump(mode="json", exclude=_SECRET_EXCLUDE)
        for role in ROLE_NAMES:
            data[role]["api_key_set"] = self.vault.has(role)
        data["keychain"] = {
            "available": self.vault.available,
            "warning": self.vault.warning,
        }
        return data

    def set_role_detection(self, role: str, **updates: object) -> None:
        config = self.load()
        role_obj = getattr(config, role)
        for name, value in updates.items():
            setattr(role_obj, name, value)
        self.runtime_store.save_config(config)
