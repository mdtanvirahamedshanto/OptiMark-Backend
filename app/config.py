"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/optimark"

    # JWT - SECRET_KEY must be set in production
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS - comma-separated origins, e.g. "http://localhost:3000,https://app.example.com"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Storage
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # Stripe (optional)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # First admin (set email to grant admin role on signup)
    ADMIN_EMAIL: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True

    def get_cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS into list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def is_production(self) -> bool:
        """Check if running in production (e.g. SECRET_KEY changed from default)."""
        return self.SECRET_KEY != "change-me-in-production"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
