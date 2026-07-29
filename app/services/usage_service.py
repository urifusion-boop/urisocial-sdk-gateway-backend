"""
Usage Service
Tracks real API usage and billable credit consumption for the current
billing period.

This reads directly from app.models.usage_log.UsageLog and
RateLimitCounter — the same records the proxy itself writes on every
request (see app/api/v1/endpoints/proxy.py and app/services/usage_tracker.py)
and the same records app/middleware/api_key_validation.py's hourly/daily
throttling reads. There used to be a second, parallel aggregation system
(app.models.billing.UsageRecord + a second UsageLog class colliding with
this one on the same MongoDB collection name) fed by a separate global
middleware — it silently never tracked two of the three proxy routes
(a real, confirmed bug) and duplicated a second API-key DB lookup on every
request. That system has been removed; this is now the single source of
truth for usage, billing, and quota enforcement.

"Requests" and "credits" are deliberately different numbers: a request is
any proxied API call; a credit is one real AI-generation action with a
real upstream cost, as reported by uri-social-backend via the
X-URI-Credits-Consumed response header. Only credits are billed/quota-
limited; raw request volume is only ever throttled (hourly/daily), never
charged for directly.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from beanie import PydanticObjectId

from app.models.usage_log import UsageLog
from app.services.subscription_service import subscription_service
from app.core.pricing import get_plan, PlanTier, calculate_overage_cost


class UsageService:
    """Credit-based API usage tracking and billing service."""

    async def _get_period_and_plan(self, developer_id: str):
        """Resolve the current billing-period window and plan for a developer.

        Falls back to a calendar-month window on the free tier, matching
        the previous system's behavior for developers with no subscription
        document at all.
        """
        subscription = await subscription_service.get_subscription(developer_id)

        if subscription:
            period_start = subscription.current_period_start
            period_end = subscription.current_period_end
            plan_tier = PlanTier(subscription.plan_tier)
        else:
            now = datetime.now(timezone.utc)
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            plan_tier = PlanTier.FREE

        return period_start, period_end, get_plan(plan_tier), plan_tier

    async def _aggregate_totals(self, developer_id: str, period_start: datetime, period_end: datetime) -> Dict:
        """DB-side aggregation of request/credit totals for a billing period.

        Aggregates at the database level rather than loading individual
        UsageLog documents into Python — a developer on a high-volume plan
        can easily have hundreds of thousands of log rows in a period, and
        pulling all of them into app memory on every usage check would not
        scale.
        """
        pipeline = [
            {
                "$match": {
                    "developer_id": PydanticObjectId(developer_id),
                    "created_at": {"$gte": period_start, "$lte": period_end},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_requests": {"$sum": 1},
                    "successful_requests": {
                        "$sum": {
                            "$cond": [
                                {"$and": [
                                    {"$gte": ["$status_code", 200]},
                                    {"$lt": ["$status_code", 400]},
                                ]},
                                1,
                                0,
                            ]
                        }
                    },
                    "total_credits": {"$sum": "$credits_consumed"},
                }
            },
        ]

        results = await UsageLog.find(
            UsageLog.developer_id == PydanticObjectId(developer_id)
        ).aggregate(pipeline).to_list()

        if not results:
            return {"total_requests": 0, "successful_requests": 0, "total_credits": 0}

        row = results[0]
        return {
            "total_requests": row.get("total_requests", 0),
            "successful_requests": row.get("successful_requests", 0),
            "total_credits": row.get("total_credits", 0),
        }

    async def get_current_usage(self, developer_id: str) -> Dict:
        """
        Get current billing period usage, in real credits.

        Args:
            developer_id: Developer ID (str form of the gateway Developer._id)

        Returns:
            Dict with usage details
        """
        period_start, period_end, plan, _plan_tier = await self._get_period_and_plan(developer_id)
        totals = await self._aggregate_totals(developer_id, period_start, period_end)

        total_requests = totals["total_requests"]
        successful_requests = totals["successful_requests"]
        failed_requests = total_requests - successful_requests
        total_credits = totals["total_credits"]

        included_credits = plan.monthly_credits
        overage_credits = max(0, total_credits - included_credits)
        overage_cost_ngn = calculate_overage_cost(plan, total_credits)
        percentage_used = (total_credits / included_credits * 100) if included_credits > 0 else 0.0

        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "total_credits": total_credits,
            "included_credits": included_credits,
            "overage_credits": overage_credits,
            "overage_cost_ngn": overage_cost_ngn,
            "percentage_used": round(percentage_used, 2),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        }

    async def calculate_overage(self, developer_id: str) -> float:
        """
        Calculate credit overage charges for current period

        Args:
            developer_id: Developer ID

        Returns:
            Overage cost in NGN
        """
        usage = await self.get_current_usage(developer_id)
        return usage["overage_cost_ngn"]

    async def get_usage_breakdown(self, developer_id: str) -> Dict:
        """
        Get endpoint-level usage analytics (request counts and credits
        consumed per endpoint) for the current billing period.

        Args:
            developer_id: Developer ID

        Returns:
            Dict with endpoint breakdown
        """
        period_start, period_end, _plan, _plan_tier = await self._get_period_and_plan(developer_id)

        pipeline = [
            {
                "$match": {
                    "developer_id": PydanticObjectId(developer_id),
                    "created_at": {"$gte": period_start, "$lte": period_end},
                }
            },
            {
                "$group": {
                    "_id": "$endpoint",
                    "requests": {"$sum": 1},
                    "credits": {"$sum": "$credits_consumed"},
                }
            },
            {"$sort": {"requests": -1}},
        ]

        rows = await UsageLog.find(
            UsageLog.developer_id == PydanticObjectId(developer_id)
        ).aggregate(pipeline).to_list()

        total_requests = sum(row["requests"] for row in rows)

        return {
            "total_requests": total_requests,
            "endpoints": [
                {
                    "endpoint": row["_id"],
                    "requests": row["requests"],
                    "credits": row["credits"],
                    "percentage": round((row["requests"] / total_requests) * 100, 2) if total_requests > 0 else 0,
                }
                for row in rows
            ],
        }

    async def check_credit_quota(self, developer_id: str) -> Dict:
        """
        Check whether a developer may proceed, based on monthly credit quota.

        Only the free tier hard-blocks on quota exhaustion (matching the
        prior system's semantics) — paid tiers always allow the request and
        accrue overage, billed later via the invoice. Because of that, this
        only runs the aggregation query for free-tier developers; paid-tier
        callers skip it entirely, keeping this cheap on the hot request path.

        Args:
            developer_id: Developer ID

        Returns:
            Dict with quota status
        """
        _period_start, _period_end, plan, plan_tier = await self._get_period_and_plan(developer_id)

        if plan_tier != PlanTier.FREE:
            return {
                "allowed": True,
                "overage_allowed": True,
            }

        usage = await self.get_current_usage(developer_id)
        quota_exceeded = usage["total_credits"] >= plan.monthly_credits

        if quota_exceeded:
            return {
                "allowed": False,
                "reason": "Monthly credit quota exceeded. Please upgrade your plan.",
                "limit_type": "monthly_credits",
                "current_usage": usage["total_credits"],
                "limit": plan.monthly_credits,
            }

        return {
            "allowed": True,
            "overage_allowed": False,
            "current_usage": usage["total_credits"],
            "limit": plan.monthly_credits,
        }


# Singleton instance
usage_service = UsageService()
