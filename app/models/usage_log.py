from beanie import Document, PydanticObjectId
from pydantic import Field
from datetime import datetime
from typing import Optional


class UsageLog(Document):
    api_key_id: PydanticObjectId = Field(index=True)
    endpoint: str
    method: str
    status_code: int
    response_time_ms: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    class Settings:
        name = "usage_logs"
        indexes = [
            "api_key_id",
            "created_at",
            ("api_key_id", "created_at"),  # Compound index for queries
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "endpoint": "/api/v1/content/generate",
                "method": "POST",
                "status_code": 200,
                "response_time_ms": 150,
            }
        }
