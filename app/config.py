from dataclasses import dataclass
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class ProviderConfig:
    """One configured LLM provider instance.

    ``type`` is the key into PROVIDER_REGISTRY; ``name`` is the label shown in
    results and stored on rows (defaults to ``type``).
    """

    type: str
    api_key: str
    model: str
    enabled: bool = True
    name: str | None = None

    @property
    def label(self) -> str:
        return self.name or self.type


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AdScope"
    app_env: str = "development"
    debug: bool = True

    app_username: str = "admin"
    app_password: str = "change-me"
    session_secret: str = "change-this-secret"
    cookie_secure: bool = False

    database_url: str = "sqlite:///./data/adscope.db"

    demo_mode: bool = True
    llm_timeout_seconds: int = 60

    # --- Pipeline tunables (no magic numbers in code) ---
    queries_per_provider: int = 10
    # How many results each model may return per query, per publisher type.
    # Attribute names must match PER_TYPE_LIMIT_FIELDS in entities.models.
    max_websites_per_query: int = 10
    max_youtube_per_query: int = 10
    max_apps_per_query: int = 10
    max_final_websites: int = 50
    llm_concurrency: int = 8

    # How often the polling pages (query generation / discovery) auto-refresh.
    poll_interval_seconds: int = 10

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct"

    def provider_configs(self) -> list[ProviderConfig]:
        """Declarative list of provider instances the pipeline may use.

        Adding a new LLM provider is: (1) write a BaseProvider subclass,
        (2) register it in app.providers.registry.PROVIDER_REGISTRY, and
        (3) add an entry here reading its api key / model settings.
        """
        return [
            ProviderConfig(type="gemini", api_key=self.gemini_api_key, model=self.gemini_model),
            ProviderConfig(type="groq", api_key=self.groq_api_key, model=self.groq_model),
            ProviderConfig(
                type="openrouter", api_key=self.openrouter_api_key, model=self.openrouter_model
            ),
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
