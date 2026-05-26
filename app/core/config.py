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

    # Email/SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "URI Social SDK"

    class Config:
        env_file = ".env"


settings = Settings()
