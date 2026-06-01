"""
Billing and Subscription Models
Enterprise-grade billing system with Squad payment integration
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict
from beanie import Document
from pydantic import Field


class Subscription(Document):
    """
    User subscription with billing cycle tracking
    Tracks active subscriptions, payment history, and lifecycle
    """
    user_id: str = Field(..., description="User ID from authentication system")
    workspace_id: Optional[str] = Field(None, description="Associated workspace")

    # Plan details
    plan_tier: str = Field(..., description="free, starter, professional, enterprise")
    billing_interval: str = Field(default="monthly", description="monthly or yearly")

    # Pricing in NGN
    base_price_ngn: float = Field(..., description="Base subscription price in NGN")
    currency: str = Field(default="NGN", description="Currency code")

    # Lifecycle status
    status: str = Field(default="active", description="active, past_due, canceled, expired, trialing")
    current_period_start: datetime = Field(..., description="Current billing period start")
    current_period_end: datetime = Field(..., description="Current billing period end")
    cancel_at_period_end: bool = Field(default=False, description="Whether to cancel at end of period")
    canceled_at: Optional[datetime] = None

    # Squad payment integration
    last_payment_ref: Optional[str] = Field(None, description="Latest Squad transaction reference")
    payment_method: Optional[str] = Field(None, description="card, bank_transfer, ussd")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "subscriptions"
        indexes = [
            "user_id",
            "workspace_id",
            "status",
            "current_period_end",
        ]


class PaymentTransaction(Document):
    """
    Payment transaction records with Squad integration
    Tracks all payment attempts, successes, and failures
    """
    user_id: str = Field(..., description="User making payment")
    subscription_id: Optional[str] = Field(None, description="Associated subscription ID")

    # Squad payment details
    transaction_ref: str = Field(..., description="Unique Squad transaction reference")
    amount_ngn: float = Field(..., description="Payment amount in NGN")
    currency: str = Field(default="NGN", description="Currency code")
    status: str = Field(default="pending", description="pending, completed, failed, refunded")

    # Squad response
    payment_method: Optional[str] = None
    gateway_response: Optional[Dict] = Field(None, description="Full Squad webhook payload")
    gateway_transaction_id: Optional[str] = Field(None, description="Squad's internal transaction ID")

    # Billing details
    billing_period_start: Optional[datetime] = None
    billing_period_end: Optional[datetime] = None
    plan_tier: str = Field(..., description="Plan purchased")
    billing_interval: str = Field(default="monthly", description="monthly or yearly")

    # Invoice reference
    invoice_id: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None

    class Settings:
        name = "payment_transactions"
        indexes = [
            "user_id",
            "transaction_ref",
            "status",
            "created_at",
        ]


class UsageRecord(Document):
    """
    API usage tracking for billing and analytics
    Aggregated usage data per user per billing period
    """
    user_id: str = Field(..., description="User ID")
    subscription_id: Optional[str] = Field(None, description="Associated subscription")

    # Time period (billing cycle)
    period_start: datetime = Field(..., description="Billing period start")
    period_end: datetime = Field(..., description="Billing period end")
    period_month: str = Field(..., description="YYYY-MM for easy querying")

    # Usage metrics
    total_requests: int = Field(default=0, description="Total API requests")
    successful_requests: int = Field(default=0, description="2xx responses")
    failed_requests: int = Field(default=0, description="4xx/5xx responses")

    # Endpoint breakdown {"/v1/social-media/generate": 1500, ...}
    endpoint_usage: Dict[str, int] = Field(default_factory=dict, description="Per-endpoint request counts")

    # Billing calculations
    included_requests: int = Field(..., description="Requests included in plan quota")
    overage_requests: int = Field(default=0, description="Requests beyond quota")
    overage_cost_ngn: float = Field(default=0.0, description="Overage charges in NGN")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "usage_records"
        indexes = [
            "user_id",
            "period_month",
            "period_start",
        ]


class Invoice(Document):
    """
    Generated invoices for subscriptions and overage charges
    Tracks billing statements and payment status
    """
    user_id: str = Field(..., description="User ID")
    subscription_id: Optional[str] = Field(None, description="Associated subscription")
    invoice_number: str = Field(..., description="Unique invoice number (e.g., INV-2025-05-001)")

    # Billing period
    period_start: datetime = Field(..., description="Invoice period start")
    period_end: datetime = Field(..., description="Invoice period end")

    # Line items
    subscription_charge_ngn: float = Field(default=0.0, description="Base plan cost")
    overage_charge_ngn: float = Field(default=0.0, description="Extra usage charges")
    discount_ngn: float = Field(default=0.0, description="Discounts applied")
    tax_ngn: float = Field(default=0.0, description="Tax amount (if applicable)")
    total_ngn: float = Field(..., description="Total amount due")
    currency: str = Field(default="NGN", description="Currency code")

    # Line item details
    line_items: List[Dict] = Field(default_factory=list, description="Detailed line items")

    # Status
    status: str = Field(default="draft", description="draft, issued, paid, overdue, void, refunded")
    issued_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    void_reason: Optional[str] = None

    # Payment
    payment_transaction_id: Optional[str] = Field(None, description="Associated payment transaction")

    # PDF/Document
    pdf_url: Optional[str] = Field(None, description="URL to invoice PDF")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "invoices"
        indexes = [
            "user_id",
            "invoice_number",
            "status",
            "period_start",
        ]


class UsageLog(Document):
    """
    Individual API request logs for detailed tracking
    Used for billing, analytics, and debugging
    """
    user_id: str = Field(..., description="User making request")
    api_key_id: str = Field(..., description="API key used")
    workspace_id: Optional[str] = None

    # Request details
    endpoint: str = Field(..., description="API endpoint path")
    method: str = Field(..., description="HTTP method")
    status_code: int = Field(..., description="Response status code")

    # Timing
    duration_ms: float = Field(..., description="Request duration in milliseconds")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Metadata
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    # Billing
    billable: bool = Field(default=True, description="Whether to count for billing")

    class Settings:
        name = "usage_logs"
        indexes = [
            "user_id",
            "api_key_id",
            "timestamp",
            "endpoint",
        ]
