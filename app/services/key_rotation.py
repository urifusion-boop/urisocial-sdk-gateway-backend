"""
Automatic API key rotation service
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from beanie import PydanticObjectId

from app.models.api_key import APIKey
from app.core.api_key import generate_api_key, hash_api_key, get_key_prefix


async def enable_auto_rotation(
    api_key: APIKey,
    rotation_days: int = 90
) -> APIKey:
    """
    Enable automatic rotation for an API key

    Args:
        api_key: The API key to enable rotation for
        rotation_days: Number of days between rotations

    Returns:
        Updated API key
    """
    api_key.rotation_enabled = True
    api_key.rotation_days = rotation_days

    # Set next rotation date
    now = datetime.now(timezone.utc)
    api_key.last_rotated_at = now
    api_key.next_rotation_at = now + timedelta(days=rotation_days)

    await api_key.save()
    return api_key


async def disable_auto_rotation(api_key: APIKey) -> APIKey:
    """
    Disable automatic rotation for an API key

    Args:
        api_key: The API key to disable rotation for

    Returns:
        Updated API key
    """
    api_key.rotation_enabled = False
    api_key.next_rotation_at = None

    await api_key.save()
    return api_key


async def rotate_key(api_key_id: PydanticObjectId) -> Tuple[APIKey, str]:
    """
    Manually rotate an API key (generates new key, keeps same settings)

    Args:
        api_key_id: ID of the API key to rotate

    Returns:
        Tuple of (updated_api_key, new_plain_key)
        WARNING: new_plain_key is only returned once!

    Raises:
        ValueError: If key not found
    """
    api_key = await APIKey.get(api_key_id)
    if not api_key:
        raise ValueError(f"API key {api_key_id} not found")

    # Generate new key
    new_plain_key = generate_api_key()
    new_hashed_key = hash_api_key(new_plain_key)
    new_prefix = get_key_prefix(new_plain_key)

    # Update the key (keeps all other settings)
    api_key.key = new_hashed_key
    api_key.key_prefix = new_prefix

    # Update rotation timestamps
    now = datetime.now(timezone.utc)
    api_key.last_rotated_at = now

    if api_key.rotation_enabled and api_key.rotation_days:
        api_key.next_rotation_at = now + timedelta(days=api_key.rotation_days)

    # Reset usage metadata
    api_key.last_used_at = None
    api_key.user_agent = None
    api_key.last_ip_address = None

    await api_key.save()

    return api_key, new_plain_key


async def check_rotation_due(api_key: APIKey) -> bool:
    """
    Check if API key is due for rotation

    Args:
        api_key: The API key to check

    Returns:
        True if rotation is due, False otherwise
    """
    if not api_key.rotation_enabled:
        return False

    if not api_key.next_rotation_at:
        return False

    now = datetime.now(timezone.utc)
    next_rotation = api_key.next_rotation_at
    if next_rotation.tzinfo is None:
        next_rotation = next_rotation.replace(tzinfo=timezone.utc)

    return next_rotation <= now


async def auto_rotate_due_keys() -> int:
    """
    Background job: Automatically rotate all keys that are due for rotation
    Should be run daily via cron/scheduler

    Returns:
        Number of keys rotated
    """
    # Find all active keys with rotation enabled
    keys = await APIKey.find(
        APIKey.is_active == True,
        APIKey.rotation_enabled == True
    ).to_list()

    rotated_count = 0
    for key in keys:
        if await check_rotation_due(key):
            # Auto-rotate the key
            await rotate_key(key.id)
            rotated_count += 1

    return rotated_count


async def get_rotation_status(api_key: APIKey) -> dict:
    """
    Get detailed rotation status for an API key

    Args:
        api_key: The API key

    Returns:
        Dict with rotation status details
    """
    if not api_key.rotation_enabled:
        return {
            "enabled": False,
            "rotation_days": None,
            "last_rotated_at": None,
            "next_rotation_at": None,
            "days_until_rotation": None,
            "is_due": False
        }

    now = datetime.now(timezone.utc)

    # Calculate days until rotation
    days_until_rotation = None
    is_due = False

    if api_key.next_rotation_at:
        next_rotation = api_key.next_rotation_at
        if next_rotation.tzinfo is None:
            next_rotation = next_rotation.replace(tzinfo=timezone.utc)

        days_until_rotation = (next_rotation - now).days
        is_due = next_rotation <= now

    # Format last rotated
    last_rotated = None
    if api_key.last_rotated_at:
        last_rotated = api_key.last_rotated_at
        if last_rotated.tzinfo is None:
            last_rotated = last_rotated.replace(tzinfo=timezone.utc)

    return {
        "enabled": True,
        "rotation_days": api_key.rotation_days,
        "last_rotated_at": last_rotated.isoformat() if last_rotated else None,
        "next_rotation_at": next_rotation.isoformat() if api_key.next_rotation_at else None,
        "days_until_rotation": max(0, days_until_rotation) if days_until_rotation is not None else None,
        "is_due": is_due
    }


async def schedule_rotation(
    api_key: APIKey,
    days_from_now: int
) -> APIKey:
    """
    Schedule a key rotation for a specific date in the future

    Args:
        api_key: The API key
        days_from_now: Number of days from now to schedule rotation

    Returns:
        Updated API key
    """
    now = datetime.now(timezone.utc)
    api_key.next_rotation_at = now + timedelta(days=days_from_now)
    api_key.rotation_enabled = True

    await api_key.save()
    return api_key
