"""Application configuration."""


from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_env: str = "development"

    # Database
    database_url: str = "sqlite:///./data/threadify.db"

    # Security
    secret_aes_key: str | None = None

    # OpenAI
    openai_api_key: str | None = None

    # Twitter/X OAuth
    x_client_id: str | None = None
    x_client_secret: str | None = None
    oauth_redirect_url: str | None = None

    # Services
    length_service_url: str = "http://localhost:8080"

    # Auth
    basic_auth_user: str | None = None
    basic_auth_hash: str | None = None

    # Timezone
    tz: str = "America/Toronto"


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
