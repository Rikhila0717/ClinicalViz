"""
Centralized configuration loaded from environment variables.
Keeps secrets out of source and makes the service 12-factor compliant.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    CT_API_BASE: str = "https://clinicaltrials.gov/api/v2"
    CT_API_PAGE_SIZE: int = 50
    CT_API_MAX_PAGES: int = 5
    CT_API_RATE_LIMIT_RPS: float = 3.0
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
