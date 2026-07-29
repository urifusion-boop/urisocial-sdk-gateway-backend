from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # MongoDB Database
    MONGODB_URL: str
    DATABASE_NAME: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Redis
    REDIS_URL: str

    # CORS
    FRONTEND_URL: str

    # Environment
    ENVIRONMENT: str = "development"

    # API Keys
    API_KEY_PREFIX: str = "urisocial_"

    # Main Backend URL
    MAIN_BACKEND_URL: str = "https://api.urisocial.com"

    # Shared secret proving proxied requests actually came from this
    # gateway — must match uri-social-backend's SDK_GATEWAY_INTERNAL_SECRET
    # exactly (a per-deployment secret, never a fixed/guessable literal).
    SDK_GATEWAY_INTERNAL_SECRET: str = ""

    # Email/SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "URI Social SDK"

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""

    # Squad Payment Gateway
    SQUAD_MODE: str = "sandbox"  # sandbox or live
    SQUAD_SANDBOX_SECRET_KEY: str = ""
    SQUAD_SANDBOX_PUBLIC_KEY: str = ""
    SQUAD_LIVE_SECRET_KEY: str = ""
    SQUAD_LIVE_PUBLIC_KEY: str = ""
    SQUAD_WEBHOOK_SECRET: str = ""
    SQUAD_WEBHOOK_URL: str = ""
    SQUAD_CALLBACK_URL: str = "http://localhost:3000/dashboard/billing/callback"

    class Config:
        env_file = ".env"


settings = Settings()


def get_settings() -> Settings:
    """Get settings instance"""
    return settings
