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

    # Monthly pricing in US Dollars (USD) — set as distinct, clean USD price
    # points rather than a raw NGN/FX conversion (standard SaaS practice;
    # uri-social-backend, the core product, has no live USD pricing of its
    # own to convert from — see note below).
    monthly_price_usd: float  # USD
    yearly_price_usd: float  # USD (discounted)

    # Credit quota — a "credit" is one real AI-generation action (as reported
    # by uri-social-backend via the X-URI-Credits-Consumed response header),
    # not a raw API request. Requests that don't generate anything (reads,
    # connection management, webhooks, etc.) cost 0 credits and don't count
    # against this quota.
    monthly_credits: int  # Included generation credits per month

    # Raw request throttling — unrelated to billing, protects infrastructure
    # regardless of whether a request actually costs credits.
    hourly_rate_limit: int  # Max requests per hour
    daily_rate_limit: int  # Max requests per day

    # Overage pricing
    overage_rate_per_credit_ngn: float  # NGN per credit over quota
    overage_rate_per_credit_usd: float  # USD per credit over quota

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


# Enterprise-grade pricing tiers (Nigerian Naira - NGN, with US Dollar list
# prices for the USD market). Exchange rate reference: $1 ≈ ₦1,600 (subject
# to market rates) — used only where a real number had to be derived (the
# USD overage rate below); base USD subscription prices are independent,
# deliberately-rounded list prices, not FX conversions.
#
# CREDIT PRICING BASIS: uri-social-backend (the core product) already sells
# the exact same unit — one AI-generation credit — directly to consumers at
# a real, live rate: its "Custom / pay-per-credit" tier charges ₦750/credit
# flat (app/services/SubscriptionService.py), and its bundled tiers cluster
# in the ₦714-800/credit range. The credit quotas and overage rates below
# are derived from that real number, not invented:
#   - monthly_credits per tier = base_price_ngn / (a bundled per-credit rate
#     at a volume discount off ₦750, discount scaling with tier size — the
#     same "bigger commitment, bigger discount" logic the core product
#     itself uses across its own tiers).
#   - overage_rate_per_credit_ngn = 750, i.e. exactly the core product's own
#     real walk-in/pay-as-you-go rate: once a developer exceeds their
#     bundled quota, they pay the same rate anyone pays outside a bundle.
#   - Free tier's monthly_credits = 10, matching the core product's own
#     real one-time trial_credits default (a reasonable, already-precedented
#     size for a no-cost allotment).
PRICING_TIERS: Dict[PlanTier, PricingPlan] = {
    PlanTier.FREE: PricingPlan(
        tier=PlanTier.FREE,
        name="Free",
        description="Perfect for testing and small projects",
        monthly_price_ngn=0.0,
        yearly_price_ngn=0.0,
        monthly_price_usd=0.0,
        yearly_price_usd=0.0,
        monthly_credits=10,  # matches core product's real trial_credits default
        hourly_rate_limit=10,
        daily_rate_limit=100,
        overage_rate_per_credit_ngn=0.0,  # No overage, hard limit
        overage_rate_per_credit_usd=0.0,  # No overage, hard limit
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
        monthly_price_usd=60.0,
        yearly_price_usd=576.0,  # ~20% discount (2 months free)
        monthly_credits=150,  # ₦75,000 / 150 = ₦500/credit (33% off ₦750 walk-in rate)
        hourly_rate_limit=5_000,
        daily_rate_limit=50_000,
        overage_rate_per_credit_ngn=750.0,  # core product's real per-credit walk-in rate
        overage_rate_per_credit_usd=0.50,  # ₦750 / ₦1,600 per $1, rounded
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
        monthly_price_usd=250.0,
        yearly_price_usd=2_400.0,  # ~20% discount
        monthly_credits=800,  # ₦320,000 / 800 = ₦400/credit (47% off ₦750 walk-in rate)
        hourly_rate_limit=50_000,
        daily_rate_limit=500_000,
        overage_rate_per_credit_ngn=750.0,  # core product's real per-credit walk-in rate
        overage_rate_per_credit_usd=0.50,  # ₦750 / ₦1,600 per $1, rounded
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
        monthly_price_usd=1_200.0,
        yearly_price_usd=11_520.0,  # ~20% discount
        monthly_credits=5_000,  # ₦1,600,000 / 5,000 = ₦320/credit (57% off ₦750 walk-in rate)
        hourly_rate_limit=1_000_000,
        daily_rate_limit=10_000_000,
        overage_rate_per_credit_ngn=750.0,  # core product's real per-credit walk-in rate
        overage_rate_per_credit_usd=0.50,  # ₦750 / ₦1,600 per $1, rounded
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


def calculate_overage_cost(plan: PricingPlan, total_credits: int, currency: str = "NGN") -> float:
    """
    Calculate overage cost for AI-generation credits exceeding monthly quota

    Args:
        plan: Pricing plan
        total_credits: Total generation credits consumed this billing period
        currency: Currency code (NGN or USD)

    Returns:
        Overage cost in the specified currency
    """
    if total_credits <= plan.monthly_credits:
        return 0.0

    overage_credits = total_credits - plan.monthly_credits
    rate = plan.overage_rate_per_credit_usd if currency == "USD" else plan.overage_rate_per_credit_ngn

    return round(overage_credits * rate, 2)


def calculate_total_cost(
    plan: PricingPlan,
    billing_interval: BillingInterval,
    total_credits: int,
    currency: str = "NGN"
) -> Dict[str, float]:
    """
    Calculate total cost including base price and credit overage

    Args:
        plan: Pricing plan
        billing_interval: Monthly or yearly
        total_credits: Total generation credits consumed this billing period
        currency: Currency code (NGN or USD)

    Returns:
        Dict with breakdown: {
            "base_price": float,
            "overage_cost": float,
            "total": float,
            "credits_included": int,
            "credits_overage": int,
            "currency": str
        }
    """
    if currency == "USD":
        base_price = plan.monthly_price_usd if billing_interval == BillingInterval.MONTHLY else plan.yearly_price_usd
    else:
        base_price = plan.monthly_price_ngn if billing_interval == BillingInterval.MONTHLY else plan.yearly_price_ngn

    overage_cost = calculate_overage_cost(plan, total_credits, currency)
    overage_credits = max(0, total_credits - plan.monthly_credits)

    return {
        "base_price": base_price,
        "overage_cost": overage_cost,
        "total": round(base_price + overage_cost, 2),
        "credits_included": min(total_credits, plan.monthly_credits),
        "credits_overage": overage_credits,
        "currency": currency,
    }


def get_rate_limits(plan: PricingPlan) -> Dict[str, int]:
    """Get rate limits for a plan"""
    return {
        "hourly": plan.hourly_rate_limit,
        "daily": plan.daily_rate_limit,
        "monthly_credits": plan.monthly_credits,
    }
