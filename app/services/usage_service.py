"""
Usage Service
Tracks API usage for billing and analytics
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from app.models.billing import UsageRecord, UsageLog
from app.services.subscription_service import subscription_service
from app.core.pricing import get_plan, PlanTier, calculate_overage_cost


class UsageService:
    """API usage tracking and billing service"""

    async def track_request(
        self,
        user_id: str,
        api_key_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        workspace_id: Optional[str] = None
    ):
        """
        Track individual API request for billing

        Args:
            user_id: User ID
            api_key_id: API key used
            endpoint: API endpoint path
            method: HTTP method
            status_code: Response status code
            duration_ms: Request duration in milliseconds
            ip_address: Client IP address
            user_agent: Client user agent
            workspace_id: Workspace ID
        """
        # Log individual request
        usage_log = UsageLog(
            user_id=user_id,
            api_key_id=api_key_id,
            workspace_id=workspace_id,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc),
            ip_address=ip_address,
            user_agent=user_agent,
            billable=True
        )
        await usage_log.insert()

        # Update aggregated usage record
        await self._update_usage_record(user_id, endpoint, status_code)

    async def _update_usage_record(self, user_id: str, endpoint: str, status_code: int):
        """Update aggregated usage record for current billing period"""
        # Get current subscription
        subscription = await subscription_service.get_subscription(user_id)

        if subscription:
            period_start = subscription.current_period_start
            period_end = subscription.current_period_end
            subscription_id = str(subscription.id)
            plan_tier = PlanTier(subscription.plan_tier)
        else:
            # Free tier - use calendar month
            now = datetime.now(timezone.utc)
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            subscription_id = None
            plan_tier = PlanTier.FREE

        period_month = period_start.strftime("%Y-%m")

        # Get or create usage record
        usage_record = await UsageRecord.find_one(
            UsageRecord.user_id == user_id,
            UsageRecord.period_month == period_month
        )

        if not usage_record:
            plan = get_plan(plan_tier)
            usage_record = UsageRecord(
                user_id=user_id,
                subscription_id=subscription_id,
                period_start=period_start,
                period_end=period_end,
                period_month=period_month,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                endpoint_usage={},
                included_requests=plan.monthly_requests,
                overage_requests=0,
                overage_cost_ngn=0.0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )

        # Update counts
        usage_record.total_requests += 1

        if 200 <= status_code < 400:
            usage_record.successful_requests += 1
        else:
            usage_record.failed_requests += 1

        # Update endpoint breakdown
        if endpoint not in usage_record.endpoint_usage:
            usage_record.endpoint_usage[endpoint] = 0
        usage_record.endpoint_usage[endpoint] += 1

        # Calculate overage
        if usage_record.total_requests > usage_record.included_requests:
            usage_record.overage_requests = usage_record.total_requests - usage_record.included_requests
            plan = get_plan(plan_tier)
            usage_record.overage_cost_ngn = calculate_overage_cost(plan, usage_record.total_requests)
        else:
            usage_record.overage_requests = 0
            usage_record.overage_cost_ngn = 0.0

        usage_record.updated_at = datetime.now(timezone.utc)

        if usage_record.id:
            await usage_record.save()
        else:
            await usage_record.insert()

    async def get_current_usage(self, user_id: str) -> Dict:
        """
        Get current billing period usage

        Args:
            user_id: User ID

        Returns:
            Dict with usage details
        """
        # Get current subscription
        subscription = await subscription_service.get_subscription(user_id)

        if subscription:
            period_month = subscription.current_period_start.strftime("%Y-%m")
            plan_tier = PlanTier(subscription.plan_tier)
        else:
            # Free tier
            now = datetime.now(timezone.utc)
            period_month = now.strftime("%Y-%m")
            plan_tier = PlanTier.FREE

        # Get usage record
        usage_record = await UsageRecord.find_one(
            UsageRecord.user_id == user_id,
            UsageRecord.period_month == period_month
        )

        plan = get_plan(plan_tier)

        if not usage_record:
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "included_requests": plan.monthly_requests,
                "overage_requests": 0,
                "overage_cost_ngn": 0.0,
                "percentage_used": 0.0,
                "endpoint_usage": {}
            }

        percentage_used = (usage_record.total_requests / plan.monthly_requests) * 100 if plan.monthly_requests > 0 else 0

        return {
            "total_requests": usage_record.total_requests,
            "successful_requests": usage_record.successful_requests,
            "failed_requests": usage_record.failed_requests,
            "included_requests": usage_record.included_requests,
            "overage_requests": usage_record.overage_requests,
            "overage_cost_ngn": usage_record.overage_cost_ngn,
            "percentage_used": round(percentage_used, 2),
            "endpoint_usage": usage_record.endpoint_usage,
            "period_start": usage_record.period_start.isoformat(),
            "period_end": usage_record.period_end.isoformat()
        }

    async def calculate_overage(self, user_id: str) -> float:
        """
        Calculate overage charges for current period

        Args:
            user_id: User ID

        Returns:
            Overage cost in NGN
        """
        usage = await self.get_current_usage(user_id)
        return usage["overage_cost_ngn"]

    async def get_usage_breakdown(self, user_id: str) -> Dict:
        """
        Get endpoint-level usage analytics

        Args:
            user_id: User ID

        Returns:
            Dict with endpoint breakdown
        """
        usage = await self.get_current_usage(user_id)

        # Sort endpoints by usage
        endpoint_usage = usage["endpoint_usage"]
        sorted_endpoints = sorted(
            endpoint_usage.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return {
            "total_requests": usage["total_requests"],
            "endpoints": [
                {
                    "endpoint": endpoint,
                    "requests": count,
                    "percentage": round((count / usage["total_requests"]) * 100, 2) if usage["total_requests"] > 0 else 0
                }
                for endpoint, count in sorted_endpoints
            ]
        }

    async def check_rate_limit(self, user_id: str) -> Dict:
        """
        Check if user has exceeded rate limits

        Args:
            user_id: User ID

        Returns:
            Dict with rate limit status
        """
        # Get subscription
        subscription = await subscription_service.get_subscription(user_id)

        if subscription:
            plan_tier = PlanTier(subscription.plan_tier)
        else:
            plan_tier = PlanTier.FREE

        plan = get_plan(plan_tier)
        usage = await self.get_current_usage(user_id)

        # Check monthly limit
        monthly_limit_exceeded = usage["total_requests"] >= plan.monthly_requests

        # For free tier, block overage
        if plan_tier == PlanTier.FREE and monthly_limit_exceeded:
            return {
                "allowed": False,
                "reason": "Monthly request limit exceeded. Please upgrade your plan.",
                "limit_type": "monthly",
                "current_usage": usage["total_requests"],
                "limit": plan.monthly_requests
            }

        return {
            "allowed": True,
            "current_usage": usage["total_requests"],
            "monthly_limit": plan.monthly_requests,
            "overage_allowed": plan_tier != PlanTier.FREE
        }


# Singleton instance
usage_service = UsageService()
