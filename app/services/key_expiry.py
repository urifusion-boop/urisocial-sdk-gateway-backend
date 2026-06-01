"""
API Key expiry and renewal management
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from beanie import PydanticObjectId

from app.models.api_key import APIKey
from app.core.pricing import PlanTier, get_plan


async def set_key_expiry(
    api_key: APIKey,
    plan_tier: PlanTier,
    custom_days: Optional[int] = None
) -> APIKey:
    """
    Set expiry date for API key based on plan tier

    Args:
        api_key: The API key to set expiry for
        plan_tier: The subscription plan tier
        custom_days: Custom expiry days (overrides plan default)

    Returns:
        Updated API key
    """
    plan = get_plan(plan_tier)

    # Determine expiry days
    if custom_days is not None:
        expiry_days = custom_days
    else:
        expiry_days = plan.api_key_expiry_days

    # Set expiry date (None means never expires)
    if expiry_days is None:
        api_key.expires_at = None
    else:
        now = datetime.now(timezone.utc)
        api_key.expires_at = now + timedelta(days=expiry_days)

    await api_key.save()
    return api_key


async def renew_key(
    api_key_id: PydanticObjectId,
    plan_tier: PlanTier,
    custom_days: Optional[int] = None
) -> APIKey:
    """
    Renew an API key by extending its expiry date

    Args:
        api_key_id: ID of the API key to renew
        plan_tier: The current subscription plan tier
        custom_days: Custom renewal period (overrides plan default)

    Returns:
        Renewed API key

    Raises:
        ValueError: If key not found
    """
    api_key = await APIKey.get(api_key_id)
    if not api_key:
        raise ValueError(f"API key {api_key_id} not found")

    plan = get_plan(plan_tier)

    # Determine renewal period
    if custom_days is not None:
        renewal_days = custom_days
    else:
        renewal_days = plan.api_key_expiry_days

    # Renew from current expiry or now (whichever is later)
    now = datetime.now(timezone.utc)

    if renewal_days is None:
        # Never expires
        api_key.expires_at = None
    else:
        if api_key.expires_at:
            # Extend from current expiry if in future, otherwise from now
            expires_at = api_key.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            base_date = max(expires_at, now)
        else:
            base_date = now

        api_key.expires_at = base_date + timedelta(days=renewal_days)

    # Reactivate if was inactive
    api_key.is_active = True

    await api_key.save()
    return api_key


async def auto_renew_on_payment(
    developer_id: PydanticObjectId,
    plan_tier: PlanTier
) -> int:
    """
    Automatically renew all active keys for a developer after successful payment

    Args:
        developer_id: The developer's user ID
        plan_tier: The subscription plan tier

    Returns:
        Number of keys renewed
    """
    plan = get_plan(plan_tier)

    # Find all active keys for this developer
    keys = await APIKey.find(
        APIKey.developer_id == developer_id,
        APIKey.is_active == True
    ).to_list()

    renewed_count = 0
    for key in keys:
        await renew_key(key.id, plan_tier)
        renewed_count += 1

    return renewed_count


async def expire_keys_for_failed_payment(
    developer_id: PydanticObjectId,
    grace_period_days: int = 7
) -> int:
    """
    Set expiry dates for keys when payment fails (with grace period)

    Args:
        developer_id: The developer's user ID
        grace_period_days: Days until keys expire (default 7)

    Returns:
        Number of keys updated
    """
    now = datetime.now(timezone.utc)
    grace_expiry = now + timedelta(days=grace_period_days)

    # Find all active keys for this developer
    keys = await APIKey.find(
        APIKey.developer_id == developer_id,
        APIKey.is_active == True
    ).to_list()

    updated_count = 0
    for key in keys:
        # Only update if current expiry is None or later than grace period
        if key.expires_at is None or key.expires_at > grace_expiry:
            key.expires_at = grace_expiry
            await key.save()
            updated_count += 1

    return updated_count


async def revoke_expired_keys() -> int:
    """
    Background job: Revoke all expired API keys
    Should be run daily via cron/scheduler

    Returns:
        Number of keys revoked
    """
    now = datetime.now(timezone.utc)

    # Find all active keys that have expired
    expired_keys = await APIKey.find(
        APIKey.is_active == True,
        APIKey.expires_at != None
    ).to_list()

    revoked_count = 0
    for key in expired_keys:
        expires_at = key.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            key.is_active = False
            await key.save()
            revoked_count += 1

    return revoked_count


async def get_expiry_info(api_key: APIKey) -> dict:
    """
    Get detailed expiry information for an API key

    Args:
        api_key: The API key

    Returns:
        Dict with expiry details
    """
    if api_key.expires_at is None:
        return {
            "expires": False,
            "expires_at": None,
            "days_until_expiry": None,
            "is_expired": False,
            "status": "never_expires"
        }

    now = datetime.now(timezone.utc)
    expires_at = api_key.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    is_expired = expires_at < now
    days_until_expiry = (expires_at - now).days if not is_expired else 0

    # Determine status
    if is_expired:
        status = "expired"
    elif days_until_expiry <= 7:
        status = "expiring_soon"
    elif days_until_expiry <= 30:
        status = "expiring_this_month"
    else:
        status = "active"

    return {
        "expires": True,
        "expires_at": expires_at.isoformat(),
        "days_until_expiry": days_until_expiry,
        "is_expired": is_expired,
        "status": status
    }
