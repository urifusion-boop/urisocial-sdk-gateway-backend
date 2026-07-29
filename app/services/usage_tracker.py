"""
Usage tracking and rate limiting service
"""
from datetime import datetime
from typing import Optional
from fastapi import HTTPException, status
from beanie import PydanticObjectId

from app.models.usage_log import UsageLog, RateLimitCounter


# Rate limit defaults (can be made configurable per tier later)
HOURLY_LIMIT = 1000  # 1000 requests per hour
DAILY_LIMIT = 10000  # 10000 requests per day


async def check_rate_limit(api_key_id: PydanticObjectId) -> None:
    """
    Check if API key has exceeded rate limits.

    Args:
        api_key_id: API key ID to check

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    now = datetime.utcnow()
    hour_bucket = now.strftime("%Y-%m-%d-%H")
    day_bucket = now.strftime("%Y-%m-%d")

    # Get or create rate limit counter for current hour
    counter = await RateLimitCounter.find_one(
        RateLimitCounter.api_key_id == api_key_id,
        RateLimitCounter.hour == hour_bucket,
    )

    if not counter:
        # Create new counter for this hour
        counter = RateLimitCounter(
            api_key_id=api_key_id,
            hour=hour_bucket,
            day=day_bucket,
            hourly_count=0,
            daily_count=0,
        )
        await counter.insert()

    # Check hourly limit
    if counter.hourly_count >= HOURLY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Hourly rate limit exceeded. Limit: {HOURLY_LIMIT} requests/hour. Try again in the next hour.",
            headers={
                "X-RateLimit-Limit": str(HOURLY_LIMIT),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": now.replace(minute=0, second=0, microsecond=0).isoformat(),
            },
        )

    # Check daily limit
    if counter.daily_count >= DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily rate limit exceeded. Limit: {DAILY_LIMIT} requests/day. Try again tomorrow.",
            headers={
                "X-RateLimit-Limit": str(DAILY_LIMIT),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            },
        )


async def increment_usage(
    api_key_id: PydanticObjectId,
    developer_id: PydanticObjectId,
    workspace_id: Optional[PydanticObjectId],
) -> None:
    """
    Increment usage counters after successful request.

    Args:
        api_key_id: API key ID
        developer_id: Developer ID
        workspace_id: Optional workspace ID
    """
    now = datetime.utcnow()
    hour_bucket = now.strftime("%Y-%m-%d-%H")
    day_bucket = now.strftime("%Y-%m-%d")

    # Get or create counter
    counter = await RateLimitCounter.find_one(
        RateLimitCounter.api_key_id == api_key_id,
        RateLimitCounter.hour == hour_bucket,
    )

    if not counter:
        counter = RateLimitCounter(
            api_key_id=api_key_id,
            hour=hour_bucket,
            day=day_bucket,
            hourly_count=1,
            daily_count=1,
        )
        await counter.insert()
    else:
        # Increment counters
        counter.hourly_count += 1
        counter.daily_count += 1
        counter.updated_at = now
        await counter.save()


async def log_request(
    api_key_id: PydanticObjectId,
    developer_id: PydanticObjectId,
    workspace_id: Optional[PydanticObjectId],
    endpoint: str,
    method: str,
    status_code: int,
    response_time_ms: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    error_message: Optional[str] = None,
    credits_consumed: int = 0,
) -> None:
    """
    Log API request for analytics and debugging.

    Args:
        api_key_id: API key ID
        developer_id: Developer ID
        workspace_id: Optional workspace ID
        endpoint: Request endpoint path
        method: HTTP method
        status_code: Response status code
        response_time_ms: Response time in milliseconds
        ip_address: Client IP address
        user_agent: User agent string
        error_message: Error message if request failed
        credits_consumed: Real URI Social credit cost of this request, as
            reported by the main backend (0 for non-generation requests)
    """
    log = UsageLog(
        api_key_id=api_key_id,
        developer_id=developer_id,
        workspace_id=workspace_id,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        response_time_ms=response_time_ms,
        ip_address=ip_address,
        user_agent=user_agent,
        error_message=error_message,
        credits_consumed=credits_consumed,
    )
    await log.insert()
