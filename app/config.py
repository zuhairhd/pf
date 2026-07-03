from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "PF AI Personal Finance"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/pf_ai"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/pf_ai"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60 * 24 * 7  # Deprecated: kept for compatibility
    JWT_ACCESS_EXPIRATION_MINUTES: int = 15  # Access token lifetime
    JWT_REFRESH_EXPIRATION_DAYS: int = 7  # Refresh token lifetime
    
    # Email / Notifications
    EMAIL_DEV_MODE: bool = True  # When True, email links are logged instead of sent
    EMAIL_BACKEND: str = "console"  # console | smtp | disabled
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    EMAIL_FROM: str = "noreply@pf-ai.com"
    EMAIL_FROM_NAME: str = "PF AI Personal Finance"
    NOTIFICATIONS_ENABLED: bool = True
    BILL_REMINDER_DAYS_DEFAULT: int = 3
    SUBSCRIPTION_REMINDER_DAYS_DEFAULT: int = 7

    # AI / OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_MODEL_PREMIUM: str = "gpt-4o"
    AI_MAX_REQUESTS_PER_DAY_FREE: int = 5
    AI_MAX_REQUESTS_PER_DAY_PREMIUM: int = 50
    
    # File Storage
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    
    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    
    # Frontend
    CURRENCY_DEFAULT: str = "OMR"
    CURRENCY_DECIMALS: int = 3
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
