from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional
from bson import ObjectId


class APIKey(Document):
    key: str = Field(unique=True, index=True)  # Hashed API key
    key_prefix: str  # First 12 chars for display (e.g., "urisocial_abc...")
    name: str  # User-friendly name
    description: Optional[str] = None
    developer_id: ObjectId = Field(index=True)
    workspace_id: Optional[ObjectId] = None

    is_active: bool = True
    last_used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    class Settings:
        name = "api_keys"
        indexes = [
            "key",
            "developer_id",
            "workspace_id",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Production API Key",
                "description": "Main production key",
                "key_prefix": "urisocial_abc",
                "is_active": True,
            }
        }
