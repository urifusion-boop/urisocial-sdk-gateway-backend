from beanie import Document
from pydantic import EmailStr, Field
from datetime import datetime
from typing import Optional
from bson import ObjectId


class Developer(Document):
    email: EmailStr = Field(unique=True, index=True)
    hashed_password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False

    # Email verification fields
    verification_code: Optional[str] = None
    verification_code_expires: Optional[datetime] = None

    # Password reset fields
    reset_code: Optional[str] = None
    reset_code_expires: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "developers"
        indexes = [
            "email",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "email": "developer@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "company_name": "Acme Inc",
                "is_active": True,
                "is_verified": False,
            }
        }
