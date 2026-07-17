from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct"


@lru_cache
def get_settings() -> Settings:
    return Settings()
