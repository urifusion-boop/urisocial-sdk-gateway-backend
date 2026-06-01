from beanie import Document, PydanticObjectId
from pydantic import Field
from datetime import datetime
from typing import Optional


class UsageLog(Document):
    api_key_id: PydanticObjectId = Field(index=True)
    developer_id: PydanticObjectId = Field(index=True)
    workspace_id: Optional[PydanticObjectId] = None
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
            "developer_id",
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


class RateLimitCounter(Document):
    """
    Track hourly and daily request counts for rate limiting
    """

    api_key_id: PydanticObjectId = Field(..., description="API key ID")

    # Time buckets
    hour: str = Field(..., description="Hour bucket (YYYY-MM-DD-HH)")
    day: str = Field(..., description="Day bucket (YYYY-MM-DD)")

    # Counters
    hourly_count: int = Field(default=0, description="Requests in current hour")
    daily_count: int = Field(default=0, description="Requests in current day")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "rate_limit_counters"
        indexes = [
            ("api_key_id", "hour"),  # Compound index for hourly lookup
            ("api_key_id", "day"),  # Compound index for daily lookup
            "created_at",  # For cleanup
        ]
