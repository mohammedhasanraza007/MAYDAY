from __future__ import annotations

import base64
import getpass
import json
import os
import socket
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.exceptions import PermissionDeniedError, ProviderFailureError
from runtime.provider_clients.claude_client import ClaudeClient
from runtime.provider_clients.gemini_client import GeminiClient
from runtime.provider_clients.openai_compatible_client import OpenAICompatibleClient
from runtime.provider_config import ProviderConfigManager

ROOT = Path(__file__).resolve().parent.parent
SALT_PATH = ROOT / ".mayday_salt"
KEYS_PATH = ROOT / "keys.enc"

APIApprovalRequired = PermissionDeniedError


class ApiManager:
    def __init__(self, keys_path: Path | None = None, salt_path: Path | None = None) -> None:
        self._load_local_env()
        self.keys_path = keys_path or KEYS_PATH
        self.salt_path = salt_path or SALT_PATH
        self.api_user_approved = False
        self._active_provider = ""
        self.provider_config = ProviderConfigManager()

    def set_user_approved(self, value: bool) -> None:
        self.api_user_approved = bool(value)

    def save_key(self, provider: str, key: str) -> None:
        provider_name = self._normalize_provider(provider)
        if not key or not key.strip():
            raise ValueError("API key must be non-empty")
        data = self._load_keys()
        data[provider_name] = key.strip()
        self._write_keys(data)
        self._active_provider = provider_name

    def save_provider_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        return self.provider_config.save(updates)

    def get_key(self, provider: str) -> str:
        provider_name = self._normalize_provider(provider)
        data = self._load_keys()
        key = data.get(provider_name)
        if not key:
            key = self._env_key_for(provider_name)
        if not key:
            raise ProviderFailureError(f"No API key saved for provider: {provider_name}")
        return key

    def has_active_provider(self) -> bool:
        data = self._load_keys()
        if self._active_provider in data:
            return True
        return bool(data) or bool(self._env_provider_name())

    def active_provider_name(self) -> str:
        data = self._load_keys()
        if self._active_provider in data:
            return self._active_provider
        return next(iter(data), self._env_provider_name() or "none")

    def complete(self, prompt: str, context: str = "") -> str:
        return self.complete_messages(self._build_messages(prompt, context))

    def complete_messages(self, messages: list[dict[str, str]]) -> str:
        if not self.api_user_approved:
            raise APIApprovalRequired("API call requires explicit user approval")

        provider = self.active_provider_name()
        if provider == "none":
            raise ProviderFailureError("No active API provider configured")

        # Sanitize messages to convert 'tool' role to standard 'user' role
        # to ensure compatibility with all API endpoints (OpenAI, Gemini, Claude, OpenRouter)
        sanitized = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "tool":
                sanitized.append({"role": "user", "content": f"Tool Result: {content}"})
            else:
                sanitized.append({"role": role, "content": content})

        key = self.get_key(provider)
        client = self._client_for(provider, key)
        return client.complete(messages=sanitized, system=sanitized[0]["content"] if sanitized else "", max_tokens=2000)

    def _client_for(self, provider: str, key: str):
        if provider == "claude":
            return ClaudeClient(key)
        if provider == "gemini":
            return GeminiClient(key)
        if provider == "openai":
            return OpenAICompatibleClient(key)
        if provider == "openai_compatible":
            return OpenAICompatibleClient(
                key,
                base_url=self.provider_config.openai_compatible_base_url(),
                model=self.provider_config.openai_compatible_model(),
            )
        raise ProviderFailureError(f"Unsupported API provider: {provider}")

    def _load_local_env(self) -> None:
        try:
            from dotenv import load_dotenv
        except ImportError:
            return
        load_dotenv(ROOT / ".env", override=False)

    def _env_provider_name(self) -> str:
        if os.environ.get("OPENROUTER_OPENAI_API_KEY") or os.environ.get("OPENAI_COMPATIBLE_API_KEY"):
            return "openai_compatible"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        return ""

    def _env_key_for(self, provider: str) -> str:
        if provider == "openai_compatible":
            return (
                os.environ.get("OPENAI_COMPATIBLE_API_KEY")
                or os.environ.get("OPENROUTER_OPENAI_API_KEY")
                or ""
            )
        if provider == "openai":
            return os.environ.get("OPENAI_API_KEY", "")
        return ""

    def _build_messages(self, prompt: str, context: str) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": "You are M.A.Y.D.A.Y. Reply concisely."}]
        if context:
            messages.append({"role": "system", "content": f"Context:\n{context[:12000]}"})
        messages.append({"role": "user", "content": prompt[:12000]})
        return messages

    def _get_or_create_salt(self) -> bytes:
        if self.salt_path.exists():
            salt = self.salt_path.read_bytes()
            if len(salt) != 32:
                raise ProviderFailureError("Invalid API key-store salt")
            return salt

        salt = os.urandom(32)
        self.salt_path.write_bytes(salt)
        try:
            self.salt_path.chmod(0o600)
        except OSError:
            pass
        return salt

    def _derive_key(self, salt: bytes) -> bytes:
        secret = os.environ.get("MAYDAY_KEYSTORE_SECRET")
        if not secret:
            secret = f"{getpass.getuser()}@{socket.gethostname()}"
        if not secret.strip():
            raise ProviderFailureError("Unable to derive API key-store secret")

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))

    def _fernet(self) -> Fernet:
        return Fernet(self._derive_key(self._get_or_create_salt()))

    def _load_keys(self) -> dict[str, str]:
        if not self.keys_path.exists():
            return {}
        try:
            raw = self._fernet().decrypt(self.keys_path.read_bytes())
            data: Any = json.loads(raw.decode("utf-8"))
        except (InvalidToken, json.JSONDecodeError, OSError) as exc:
            raise ProviderFailureError(f"Could not read encrypted API keys: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderFailureError("Encrypted API key store is malformed")
        return {str(k): str(v) for k, v in data.items()}

    def _write_keys(self, data: dict[str, str]) -> None:
        self.keys_path.write_bytes(self._fernet().encrypt(json.dumps(data).encode("utf-8")))
        try:
            self.keys_path.chmod(0o600)
        except OSError:
            pass

    def _normalize_provider(self, provider: str) -> str:
        name = (provider or "").strip().lower().replace("-", "_")
        aliases = {
            "anthropic": "claude",
            "google": "gemini",
            "openai_compatible": "openai_compatible",
            "openrouter": "openai_compatible"
        }
        return aliases.get(name, name)
