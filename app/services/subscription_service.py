"""
Subscription Service
Manages subscription lifecycle, upgrades, downgrades, and renewals
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
from app.models.billing import Subscription, PaymentTransaction
from app.core.pricing import PRICING_TIERS, PlanTier, BillingInterval, get_plan
from app.services.payment_service import payment_service


class SubscriptionService:
    """Subscription management service"""

    async def create_subscription(
        self,
        user_id: str,
        plan_tier: str,
        billing_interval: str,
        payment_ref: str,
        currency: str = "NGN",
        workspace_id: Optional[str] = None
    ) -> Subscription:
        """
        Create new subscription after successful payment

        Args:
            user_id: User ID
            plan_tier: Plan tier (free, starter, professional, enterprise)
            billing_interval: monthly or yearly
            payment_ref: Squad payment transaction reference
            currency: Currency code (NGN or USD)
            workspace_id: Optional workspace ID

        Returns:
            Created subscription
        """
        # Get plan details
        tier_enum = PlanTier(plan_tier)
        plan = get_plan(tier_enum)

        # Calculate billing period
        now = datetime.now(timezone.utc)
        if billing_interval == "yearly":
            period_end = now + timedelta(days=365)
        else:
            period_end = now + timedelta(days=30)

        # Get pricing based on currency
        if currency == "USD":
            base_price_usd = plan.yearly_price_usd if billing_interval == "yearly" else plan.monthly_price_usd
            base_price_ngn = None
        else:
            base_price_ngn = plan.yearly_price_ngn if billing_interval == "yearly" else plan.monthly_price_ngn
            base_price_usd = None

        # Create subscription
        subscription = Subscription(
            user_id=user_id,
            workspace_id=workspace_id,
            plan_tier=plan_tier,
            billing_interval=billing_interval,
            base_price_ngn=base_price_ngn,
            base_price_usd=base_price_usd,
            currency=currency,
            status="active",
            current_period_start=now,
            current_period_end=period_end,
            last_payment_ref=payment_ref,
            created_at=now,
            updated_at=now
        )

        await subscription.insert()

        print(f"✅ Subscription created: {user_id} - {plan_tier} ({billing_interval}) - {currency}")
        return subscription

    async def get_subscription(self, user_id: str) -> Optional[Subscription]:
        """
        Get user's active subscription

        Args:
            user_id: User ID

        Returns:
            Active subscription or None
        """
        return await Subscription.find_one(
            Subscription.user_id == user_id,
            Subscription.status == "active"
        )

    async def upgrade_subscription(
        self,
        user_id: str,
        new_tier: str,
        new_interval: str = "monthly"
    ) -> Dict:
        """
        Upgrade subscription to higher tier (with proration)

        Args:
            user_id: User ID
            new_tier: New plan tier
            new_interval: New billing interval

        Returns:
            Dict with upgrade details and prorated amount
        """
        # Get current subscription
        current_sub = await self.get_subscription(user_id)

        if not current_sub:
            raise ValueError("No active subscription found")

        # Calculate prorated amount, in the subscription's own currency
        new_plan = get_plan(PlanTier(new_tier))
        currency = current_sub.currency

        # Get new plan price
        if currency == "USD":
            new_price = new_plan.yearly_price_usd if new_interval == "yearly" else new_plan.monthly_price_usd
            current_base_price = current_sub.base_price_usd
        else:
            new_price = new_plan.yearly_price_ngn if new_interval == "yearly" else new_plan.monthly_price_ngn
            current_base_price = current_sub.base_price_ngn

        # Calculate remaining days in current period
        now = datetime.now(timezone.utc)
        remaining_days = (current_sub.current_period_end - now).days

        # Calculate prorated credit from current plan
        if current_sub.billing_interval == "yearly":
            total_days = 365
        else:
            total_days = 30

        unused_amount = ((current_base_price or 0.0) / total_days) * remaining_days

        # Amount to charge = new plan price - unused credit
        prorated_amount = max(new_price - unused_amount, 0)

        return {
            "current_plan": current_sub.plan_tier,
            "new_plan": new_tier,
            "currency": currency,
            "prorated_amount": round(prorated_amount, 2),
            "unused_credit": round(unused_amount, 2),
            "new_price": new_price,
            "remaining_days": remaining_days
        }

    async def apply_upgrade(
        self,
        user_id: str,
        new_tier: str,
        new_interval: str,
        payment_ref: str
    ) -> Subscription:
        """
        Apply subscription upgrade after payment

        Args:
            user_id: User ID
            new_tier: New plan tier
            new_interval: New billing interval
            payment_ref: Payment transaction reference

        Returns:
            Updated subscription
        """
        current_sub = await self.get_subscription(user_id)

        if not current_sub:
            raise ValueError("No active subscription found")

        # Get new plan
        new_plan = get_plan(PlanTier(new_tier))
        currency = current_sub.currency

        # Calculate new billing period, in the subscription's own currency
        now = datetime.now(timezone.utc)
        if currency == "USD":
            base_price_usd = new_plan.yearly_price_usd if new_interval == "yearly" else new_plan.monthly_price_usd
            base_price_ngn = None
        else:
            base_price_ngn = new_plan.yearly_price_ngn if new_interval == "yearly" else new_plan.monthly_price_ngn
            base_price_usd = None

        if new_interval == "yearly":
            period_end = now + timedelta(days=365)
        else:
            period_end = now + timedelta(days=30)

        # Update subscription
        current_sub.plan_tier = new_tier
        current_sub.billing_interval = new_interval
        current_sub.base_price_ngn = base_price_ngn
        current_sub.base_price_usd = base_price_usd
        current_sub.current_period_start = now
        current_sub.current_period_end = period_end
        current_sub.last_payment_ref = payment_ref
        current_sub.updated_at = now

        await current_sub.save()

        print(f"✅ Subscription upgraded: {user_id} - {new_tier}")
        return current_sub

    async def downgrade_subscription(
        self,
        user_id: str,
        new_tier: str
    ) -> Subscription:
        """
        Schedule downgrade at end of billing period

        Args:
            user_id: User ID
            new_tier: New plan tier

        Returns:
            Updated subscription
        """
        subscription = await self.get_subscription(user_id)

        if not subscription:
            raise ValueError("No active subscription found")

        # For now, just update the tier (can add scheduled downgrade logic later)
        subscription.plan_tier = new_tier
        subscription.updated_at = datetime.now(timezone.utc)

        await subscription.save()

        print(f"✅ Subscription downgraded: {user_id} - {new_tier}")
        return subscription

    async def cancel_subscription(
        self,
        user_id: str,
        immediate: bool = False
    ) -> Dict:
        """
        Cancel subscription

        Args:
            user_id: User ID
            immediate: If True, cancel immediately. If False, cancel at period end

        Returns:
            Dict with cancellation details
        """
        subscription = await self.get_subscription(user_id)

        if not subscription:
            raise ValueError("No active subscription found")

        now = datetime.now(timezone.utc)

        if immediate:
            subscription.status = "canceled"
            subscription.canceled_at = now
            subscription.current_period_end = now
        else:
            subscription.cancel_at_period_end = True
            subscription.canceled_at = now

        subscription.updated_at = now
        await subscription.save()

        print(f"✅ Subscription canceled: {user_id} (immediate={immediate})")

        return {
            "canceled": True,
            "immediate": immediate,
            "access_until": subscription.current_period_end.isoformat() if not immediate else now.isoformat()
        }

    async def renew_subscription(self, subscription_id: str) -> bool:
        """
        Process subscription renewal (called by cron job)

        Args:
            subscription_id: Subscription ID to renew

        Returns:
            True if renewal successful
        """
        subscription = await Subscription.get(subscription_id)

        if not subscription or subscription.status != "active":
            return False

        # Check if should cancel at period end
        if subscription.cancel_at_period_end:
            subscription.status = "canceled"
            await subscription.save()
            print(f"⚠️ Subscription canceled at period end: {subscription.user_id}")
            return False

        # Calculate new billing period
        now = datetime.now(timezone.utc)
        if subscription.billing_interval == "yearly":
            new_period_end = now + timedelta(days=365)
        else:
            new_period_end = now + timedelta(days=30)

        # Update subscription
        subscription.current_period_start = now
        subscription.current_period_end = new_period_end
        subscription.updated_at = now

        await subscription.save()

        print(f"✅ Subscription renewed: {subscription.user_id}")
        return True

    async def check_subscription_status(self, user_id: str) -> Dict:
        """
        Get current subscription status and details

        Args:
            user_id: User ID

        Returns:
            Dict with subscription details
        """
        subscription = await self.get_subscription(user_id)

        if not subscription:
            # User is on free tier
            free_plan = get_plan(PlanTier.FREE)
            return {
                "has_subscription": False,
                "plan_tier": "free",
                "plan_name": free_plan.name,
                "status": "active",
                "monthly_credits": free_plan.monthly_credits,
                "max_api_keys": free_plan.max_api_keys,
                "features": {
                    "ip_whitelisting": free_plan.ip_whitelisting,
                    "webhook_notifications": free_plan.webhook_notifications,
                    "priority_support": free_plan.priority_support,
                    "audit_logs": free_plan.audit_logs
                }
            }

        plan = get_plan(PlanTier(subscription.plan_tier))

        # Calculate days until renewal
        now = datetime.now(timezone.utc)
        # Ensure current_period_end is timezone-aware
        period_end = subscription.current_period_end
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        days_until_renewal = (period_end - now).days

        # Ensure dates are timezone-aware for serialization
        period_start = subscription.current_period_start
        if period_start.tzinfo is None:
            period_start = period_start.replace(tzinfo=timezone.utc)

        return {
            "has_subscription": True,
            "subscription_id": str(subscription.id),
            "plan_tier": subscription.plan_tier,
            "plan_name": plan.name,
            "billing_interval": subscription.billing_interval,
            "status": subscription.status,
            "current_period_start": period_start.isoformat(),
            "current_period_end": period_end.isoformat(),
            "days_until_renewal": days_until_renewal,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "base_price_ngn": subscription.base_price_ngn,
            "base_price_usd": subscription.base_price_usd,
            "currency": subscription.currency,
            "monthly_credits": plan.monthly_credits,
            "max_api_keys": plan.max_api_keys,
            "features": {
                "ip_whitelisting": plan.ip_whitelisting,
                "custom_rate_limits": plan.custom_rate_limits,
                "webhook_notifications": plan.webhook_notifications,
                "priority_support": plan.priority_support,
                "dedicated_infrastructure": plan.dedicated_infrastructure,
                "audit_logs": plan.audit_logs,
                "sso_enabled": plan.sso_enabled
            }
        }


# Singleton instance
subscription_service = SubscriptionService()
