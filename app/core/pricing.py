"""
Enterprise-grade pricing tiers and billing configuration
"""
from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel


class BillingInterval(str, Enum):
    """Billing cycle intervals"""
    MONTHLY = "monthly"
    YEARLY = "yearly"


class PlanTier(str, Enum):
    """Subscription plan tiers"""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class PricingPlan(BaseModel):
    """Pricing plan configuration"""
    tier: PlanTier
    name: str
    description: str

    # Monthly pricing in Nigerian Naira (NGN)
    monthly_price_ngn: float  # NGN
    yearly_price_ngn: float  # NGN (discounted)

    # Request quotas
    monthly_requests: int  # Included requests per month
    hourly_rate_limit: int  # Max requests per hour
    daily_rate_limit: int  # Max requests per day

    # Overage pricing
    overage_rate_per_1k_ngn: float  # NGN per 1000 requests over quota

    # Features
    max_api_keys: int  # Maximum number of API keys
    api_key_expiry_days: Optional[int]  # Days until key expires (None = never)

    # Advanced features
    ip_whitelisting: bool
    custom_rate_limits: bool
    webhook_notifications: bool
    priority_support: bool
    sla_guarantee: Optional[float]  # SLA uptime percentage

    # Enterprise features
    dedicated_infrastructure: bool
    custom_integrations: bool
    audit_logs: bool
    sso_enabled: bool


# Enterprise-grade pricing tiers (Nigerian Naira - NGN)
# Exchange rate reference: $1 ≈ ₦1,600 (subject to market rates)
PRICING_TIERS: Dict[PlanTier, PricingPlan] = {
    PlanTier.FREE: PricingPlan(
        tier=PlanTier.FREE,
        name="Free",
        description="Perfect for testing and small projects",
        monthly_price_ngn=0.0,
        yearly_price_ngn=0.0,
        monthly_requests=100,  # 100 requests per month
        hourly_rate_limit=10,
        daily_rate_limit=100,
        overage_rate_per_1k_ngn=0.0,  # No overage, hard limit
        max_api_keys=1,
        api_key_expiry_days=None,  # Never expires
        ip_whitelisting=False,
        custom_rate_limits=False,
        webhook_notifications=False,
        priority_support=False,
        sla_guarantee=None,
        dedicated_infrastructure=False,
        custom_integrations=False,
        audit_logs=False,
        sso_enabled=False,
    ),

    PlanTier.STARTER: PricingPlan(
        tier=PlanTier.STARTER,
        name="Starter",
        description="For growing startups and small businesses",
        monthly_price_ngn=75_000.0,  # ≈ $47
        yearly_price_ngn=720_000.0,  # ~20% discount (2 months free)
        monthly_requests=50_000,
        hourly_rate_limit=5_000,
        daily_rate_limit=50_000,
        overage_rate_per_1k_ngn=800.0,  # ₦800 per 1000 requests
        max_api_keys=5,
        api_key_expiry_days=365,  # 1 year
        ip_whitelisting=True,
        custom_rate_limits=False,
        webhook_notifications=True,
        priority_support=False,
        sla_guarantee=99.0,  # 99% uptime
        dedicated_infrastructure=False,
        custom_integrations=False,
        audit_logs=False,
        sso_enabled=False,
    ),

    PlanTier.PROFESSIONAL: PricingPlan(
        tier=PlanTier.PROFESSIONAL,
        name="Professional",
        description="For established businesses with high volume",
        monthly_price_ngn=320_000.0,  # ≈ $200
        yearly_price_ngn=3_072_000.0,  # ~20% discount
        monthly_requests=500_000,
        hourly_rate_limit=50_000,
        daily_rate_limit=500_000,
        overage_rate_per_1k_ngn=480.0,  # ₦480 per 1000 requests
        max_api_keys=25,
        api_key_expiry_days=730,  # 2 years
        ip_whitelisting=True,
        custom_rate_limits=True,
        webhook_notifications=True,
        priority_support=True,
        sla_guarantee=99.5,  # 99.5% uptime
        dedicated_infrastructure=False,
        custom_integrations=True,
        audit_logs=True,
        sso_enabled=False,
    ),

    PlanTier.ENTERPRISE: PricingPlan(
        tier=PlanTier.ENTERPRISE,
        name="Enterprise",
        description="Custom solutions for large organizations",
        monthly_price_ngn=1_600_000.0,  # ≈ $1,000
        yearly_price_ngn=15_360_000.0,  # ~20% discount
        monthly_requests=10_000_000,
        hourly_rate_limit=1_000_000,
        daily_rate_limit=10_000_000,
        overage_rate_per_1k_ngn=160.0,  # ₦160 per 1000 requests
        max_api_keys=100,
        api_key_expiry_days=None,  # Never expires (or custom)
        ip_whitelisting=True,
        custom_rate_limits=True,
        webhook_notifications=True,
        priority_support=True,
        sla_guarantee=99.99,  # 99.99% uptime
        dedicated_infrastructure=True,
        custom_integrations=True,
        audit_logs=True,
        sso_enabled=True,
    ),
}


def get_plan(tier: PlanTier) -> PricingPlan:
    """Get pricing plan by tier"""
    return PRICING_TIERS[tier]


def calculate_overage_cost(plan: PricingPlan, total_requests: int) -> float:
    """
    Calculate overage cost for requests exceeding monthly quota

    Args:
        plan: Pricing plan
        total_requests: Total requests made this billing period

    Returns:
        Overage cost in NGN
    """
    if total_requests <= plan.monthly_requests:
        return 0.0

    overage_requests = total_requests - plan.monthly_requests
    overage_thousands = overage_requests / 1000

    return round(overage_thousands * plan.overage_rate_per_1k_ngn, 2)


def calculate_total_cost(
    plan: PricingPlan,
    billing_interval: BillingInterval,
    total_requests: int
) -> Dict[str, float]:
    """
    Calculate total cost including base price and overage

    Args:
        plan: Pricing plan
        billing_interval: Monthly or yearly
        total_requests: Total requests made this billing period

    Returns:
        Dict with breakdown: {
            "base_price": float,
            "overage_cost": float,
            "total": float,
            "requests_included": int,
            "requests_overage": int
        }
    """
    base_price = plan.monthly_price_ngn if billing_interval == BillingInterval.MONTHLY else plan.yearly_price_ngn
    overage_cost = calculate_overage_cost(plan, total_requests)

    overage_requests = max(0, total_requests - plan.monthly_requests)

    return {
        "base_price": base_price,
        "overage_cost": overage_cost,
        "total": round(base_price + overage_cost, 2),
        "requests_included": min(total_requests, plan.monthly_requests),
        "requests_overage": overage_requests,
    }


def get_rate_limits(plan: PricingPlan) -> Dict[str, int]:
    """Get rate limits for a plan"""
    return {
        "hourly": plan.hourly_rate_limit,
        "daily": plan.daily_rate_limit,
        "monthly": plan.monthly_requests,
    }
