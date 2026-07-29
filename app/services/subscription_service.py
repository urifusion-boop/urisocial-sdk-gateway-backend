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
        Create (or replace) the developer's subscription after successful
        payment.

        If the developer already has an active subscription (e.g. they paid
        for a different tier through the same "buy a plan" flow rather than
        the dedicated prorated-upgrade flow), that existing subscription is
        superseded in place rather than left active alongside a second one —
        get_subscription() looks up a single active subscription per user_id,
        so two simultaneously-active documents would make which one "wins"
        arbitrary.

        Args:
            user_id: User ID
            plan_tier: Plan tier (free, starter, professional, enterprise)
            billing_interval: monthly or yearly
            payment_ref: Squad payment transaction reference
            currency: Currency code (NGN or USD)
            workspace_id: Optional workspace ID

        Returns:
            The active subscription
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

        existing = await self.get_subscription(user_id)
        if existing:
            existing.plan_tier = plan_tier
            existing.billing_interval = billing_interval
            existing.base_price_ngn = base_price_ngn
            existing.base_price_usd = base_price_usd
            existing.currency = currency
            existing.status = "active"
            existing.current_period_start = now
            existing.current_period_end = period_end
            existing.cancel_at_period_end = False
            existing.canceled_at = None
            existing.last_payment_ref = payment_ref
            existing.last_quota_warning_period = None
            existing.last_quota_exceeded_period = None
            existing.updated_at = now
            await existing.save()

            print(f"✅ Subscription replaced: {user_id} - {plan_tier} ({billing_interval}) - {currency}")
            return existing

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

    async def process_expired_periods(self) -> None:
        """
        Periodic (non-request-path) housekeeping: for every active
        subscription whose current_period_end has already passed, close
        out that billing period with a real invoice, then either cancel it
        (if cancel_at_period_end was set) or mark it past_due.

        There is no tokenized/recurring payment mechanism here — every
        payment is a fresh Squad checkout redirect — so this cannot
        auto-charge the developer for the next period. Marking past_due
        rather than silently extending current_period_end for free is the
        honest outcome: get_subscription() only looks up status=="active",
        so a past_due subscription naturally stops being returned, and the
        developer correctly falls back to free-tier limits until they pay
        again through the normal purchase flow (which replaces this
        subscription in place — see create_subscription).

        Called periodically by app/services/scheduler.py; nothing else
        calls this — without it, subscriptions never actually expired
        (cancel_at_period_end had no effect) and no invoice was ever
        generated for any billing period.
        """
        from app.services.invoice_service import invoice_service

        now = datetime.now(timezone.utc)
        expired = await Subscription.find(
            Subscription.status == "active",
            Subscription.current_period_end <= now,
        ).to_list()

        for subscription in expired:
            try:
                await invoice_service.generate_invoice(
                    user_id=subscription.user_id,
                    period_start=subscription.current_period_start,
                    period_end=subscription.current_period_end,
                    subscription_id=str(subscription.id),
                )
            except Exception as e:
                print(f"⚠️ Failed to generate closing invoice for {subscription.user_id}: {e}")

            if subscription.cancel_at_period_end:
                subscription.status = "canceled"
                print(f"⚠️ Subscription canceled at period end: {subscription.user_id}")
            else:
                subscription.status = "past_due"
                print(f"⚠️ Subscription past_due (period ended, not renewed): {subscription.user_id}")

            subscription.updated_at = now
            await subscription.save()

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
            # No active subscription — either never subscribed, or a
            # previous subscription lapsed (see process_expired_periods).
            # Report a lapsed one honestly rather than silently looking
            # identical to "never subscribed": the developer is correctly
            # on free-tier limits either way, but they should know why.
            past_due = await Subscription.find_one(
                Subscription.user_id == user_id,
                Subscription.status == "past_due",
            )

            free_plan = get_plan(PlanTier.FREE)
            return {
                "has_subscription": False,
                "plan_tier": "free",
                "plan_name": free_plan.name,
                "status": "active",
                "monthly_credits": free_plan.monthly_credits,
                "max_api_keys": free_plan.max_api_keys,
                "past_due_plan_tier": past_due.plan_tier if past_due else None,
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
