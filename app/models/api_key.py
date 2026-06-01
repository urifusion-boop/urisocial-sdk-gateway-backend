from beanie import Document, PydanticObjectId
from pydantic import Field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class APIKeyScope(str, Enum):
    """API Key permission scopes"""
    # Social Media Management
    SOCIAL_MEDIA_READ = "social_media:read"
    SOCIAL_MEDIA_WRITE = "social_media:write"
    SOCIAL_MEDIA_DELETE = "social_media:delete"

    # Content Generation
    CONTENT_GENERATE = "content:generate"
    CONTENT_ANALYZE = "content:analyze"

    # Analytics
    ANALYTICS_READ = "analytics:read"

    # Campaigns
    CAMPAIGNS_READ = "campaigns:read"
    CAMPAIGNS_WRITE = "campaigns:write"
    CAMPAIGNS_DELETE = "campaigns:delete"

    # Account Management
    ACCOUNT_READ = "account:read"
    ACCOUNT_WRITE = "account:write"

    # Admin (full access)
    ADMIN = "admin:*"


class APIKey(Document):
    key: str = Field(unique=True, index=True)  # Hashed API key
    key_prefix: str  # First 12 chars for display (e.g., "urisocial_abc...")
    name: str  # User-friendly name
    description: Optional[str] = None
    developer_id: PydanticObjectId = Field(index=True)
    workspace_id: Optional[PydanticObjectId] = None

    # Status and lifecycle
    is_active: bool = True
    last_used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    # Scopes and permissions
    scopes: List[APIKeyScope] = Field(default_factory=lambda: [APIKeyScope.ADMIN])

    # IP whitelisting (empty list = allow all IPs)
    whitelisted_ips: List[str] = Field(default_factory=list)

    # Automatic key rotation
    rotation_enabled: bool = False
    rotation_days: Optional[int] = 90  # Auto-rotate every N days
    last_rotated_at: Optional[datetime] = None
    next_rotation_at: Optional[datetime] = None

    # Environment tagging
    environment: Optional[str] = None  # e.g., "production", "development", "staging"

    # Metadata
    user_agent: Optional[str] = None  # Last user agent that used this key
    last_ip_address: Optional[str] = None  # Last IP that used this key

    class Settings:
        name = "api_keys"
        indexes = [
            "key",
            "developer_id",
            "workspace_id",
            "is_active",
            "expires_at",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Production API Key",
                "description": "Main production key",
                "key_prefix": "urisocial_abc",
                "is_active": True,
                "scopes": ["admin:*"],
                "environment": "production"
            }
        }
