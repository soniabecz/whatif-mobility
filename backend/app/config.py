"""Settings read from environment variables and the git-ignored backend/.env.

Never hardcode secrets; see backend/.env.example for the available settings.
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.database import BACKEND_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SecretStr keeps the key out of logs and error messages.
    groq_api_key: SecretStr | None = None
    ai_model: str = "openai/gpt-oss-120b"
    ai_timeout_seconds: float = 30.0

    # Minutes added to a journey for every change of bus, on top of waiting:
    # the inconvenience of changing (walking to the other stop, risk of
    # missing the bus). 0 = changing bus costs only the wait.
    transfer_penalty_min: float = Field(default=2.0, ge=0, le=60)

    # True: at every boarding passengers wait half the route's headway
    # (they arrive at random). False: no waiting; with a 5-min penalty this
    # reproduces the results from before Day 10 exactly.
    include_waiting: bool = True

    @property
    def ai_enabled(self) -> bool:
        return self.groq_api_key is not None and bool(self.groq_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    """Cached settings; also usable as a FastAPI dependency (overridable in tests)."""
    return Settings()
