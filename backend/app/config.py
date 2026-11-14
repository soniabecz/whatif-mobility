"""Settings read from environment variables and the git-ignored backend/.env.

Never hardcode secrets; see backend/.env.example for the available settings.
"""

from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.database import BACKEND_DIR
from app.services.walking import WalkingModel


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

    # Walking (see app/services/walking.py). Distance = straight line x 1.3.
    # Invented assumptions. Off: journeys to or from a closed stop are excluded.
    walking_enabled: bool = True
    walk_speed_kmh: float = Field(default=5.0, ge=1, le=10)
    max_walk_m: float = Field(default=1000.0, ge=100, le=3000)  # at the start or end
    max_transfer_walk_m: float = Field(default=500.0, ge=0, le=3000)  # between two buses, <= max_walk_m
    # False: walk only from or to a CLOSED stop, never between open stops or
    # between buses (the model of Day 10 to Day 14 part 3, step A).
    walk_between_open_stops: bool = True

    @model_validator(mode="after")
    def _transfer_walk_fits(self) -> "Settings":
        if self.max_transfer_walk_m > self.max_walk_m:
            raise ValueError("MAX_TRANSFER_WALK_M must not be larger than MAX_WALK_M")
        return self

    @property
    def walking(self) -> WalkingModel | None:
        if not self.walking_enabled:
            return None
        return WalkingModel(
            speed_kmh=self.walk_speed_kmh,
            max_walk_m=self.max_walk_m,
            max_transfer_walk_m=self.max_transfer_walk_m,
            between_open_stops=self.walk_between_open_stops,
        )

    @property
    def ai_enabled(self) -> bool:
        return self.groq_api_key is not None and bool(self.groq_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    """Cached settings; also usable as a FastAPI dependency (overridable in tests)."""
    return Settings()
