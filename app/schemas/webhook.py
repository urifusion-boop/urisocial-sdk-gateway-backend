"""
Webhook request/response schemas
"""
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from typing import Optional, List

from app.models.webhook import WebhookEvent


class CreateWebhookRequest(BaseModel):
    """Request schema for creating a webhook"""
    url: str = Field(..., description="Webhook endpoint URL")
    description: Optional[str] = Field(None, max_length=500, description="Optional description")
    events: List[WebhookEvent] = Field(..., description="Events to subscribe to")
    secret: Optional[str] = Field(None, description="Custom HMAC secret (auto-generated if not provided)")


class WebhookResponse(BaseModel):
    """Response schema for webhook"""
    id: str
    url: str
    description: Optional[str] = None
    events: List[WebhookEvent]
    is_active: bool
    created_at: datetime
    last_triggered_at: Optional[datetime] = None

    # Health stats
    consecutive_failures: int = 0
    last_failure_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0


class UpdateWebhookRequest(BaseModel):
    """Request schema for updating a webhook"""
    url: Optional[str] = None
    description: Optional[str] = None
    events: Optional[List[WebhookEvent]] = None
    is_active: Optional[bool] = None


class WebhookDeliveryResponse(BaseModel):
    """Response schema for webhook delivery"""
    id: str
    event: WebhookEvent
    url: str
    status_code: Optional[int] = None
    success: bool
    error_message: Optional[str] = None
    created_at: datetime
    delivered_at: Optional[datetime] = None
    attempt: int
    max_attempts: int


class WebhookStatsResponse(BaseModel):
    """Response schema for webhook statistics"""
    total_deliveries: int
    successful: int
    failed: int
    success_rate: float
    recent_deliveries: List[dict]
