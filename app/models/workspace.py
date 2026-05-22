from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional
from bson import ObjectId
import enum


class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class Workspace(Document):
    name: str
    slug: str = Field(unique=True, index=True)
    owner_id: ObjectId = Field(index=True)

    subscription_tier: SubscriptionTier = SubscriptionTier.FREE
    is_active: bool = True

    # Usage limits
    monthly_request_limit: int = 1000  # Free tier default
    monthly_requests_used: int = 0

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "workspaces"
        indexes = [
            "slug",
            "owner_id",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "My Workspace",
                "slug": "my-workspace",
                "subscription_tier": "free",
                "monthly_request_limit": 1000,
                "is_active": True,
            }
        }
