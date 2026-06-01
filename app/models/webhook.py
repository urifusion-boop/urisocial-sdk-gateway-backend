"""
Webhook configuration and event models
"""
from beanie import Document, PydanticObjectId
from pydantic import Field, HttpUrl
from datetime import datetime
from typing import Optional, List
from enum import Enum


class WebhookEvent(str, Enum):
    """Webhook event types"""
    # API Key events
    API_KEY_CREATED = "api_key.created"
    API_KEY_ROTATED = "api_key.rotated"
    API_KEY_REVOKED = "api_key.revoked"
    API_KEY_EXPIRED = "api_key.expired"
    API_KEY_EXPIRING_SOON = "api_key.expiring_soon"  # 7 days before expiry

    # Usage events
    RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"
    QUOTA_WARNING = "quota.warning"  # 80% of quota used
    QUOTA_EXCEEDED = "quota.exceeded"

    # Billing events (for future use)
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    SUBSCRIPTION_UPDATED = "subscription.updated"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"

    # Security events
    SUSPICIOUS_ACTIVITY = "security.suspicious_activity"
    IP_BLOCKED = "security.ip_blocked"


class Webhook(Document):
    """Webhook configuration"""
    developer_id: PydanticObjectId = Field(index=True)
    workspace_id: Optional[PydanticObjectId] = None

    # Webhook details
    url: str  # Endpoint to send webhooks to
    description: Optional[str] = None
    secret: str  # HMAC secret for signature verification

    # Event subscriptions
    events: List[WebhookEvent] = Field(default_factory=list)

    # Status
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_triggered_at: Optional[datetime] = None

    # Health tracking
    consecutive_failures: int = 0
    last_failure_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0

    class Settings:
        name = "webhooks"
        indexes = [
            "developer_id",
            "workspace_id",
            "is_active",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com/webhooks",
                "description": "Production webhook endpoint",
                "events": ["api_key.created", "rate_limit.exceeded"],
                "is_active": True
            }
        }


class WebhookDelivery(Document):
    """Webhook delivery log"""
    webhook_id: PydanticObjectId = Field(index=True)
    developer_id: PydanticObjectId = Field(index=True)

    # Event details
    event: WebhookEvent
    payload: dict

    # Delivery details
    url: str
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    delivered_at: Optional[datetime] = None

    # Retry tracking
    attempt: int = 1
    max_attempts: int = 3
    next_retry_at: Optional[datetime] = None

    # Success tracking
    success: bool = False

    class Settings:
        name = "webhook_deliveries"
        indexes = [
            "webhook_id",
            "developer_id",
            "event",
            "created_at",
            "next_retry_at",
        ]
