"""
API Key validation middleware for SDK Gateway
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import Header, HTTPException, status, Request
from beanie import PydanticObjectId

from app.models.api_key import APIKey
from app.core.api_key import hash_api_key
from app.services.usage_tracker import check_rate_limit
from app.services.usage_service import usage_service
from app.services.ip_validator import get_client_ip, require_ip_whitelist


async def validate_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API Key for authentication")
) -> dict:
    """
    Validate API key from X-API-Key header and return developer context.

    Args:
        x_api_key: API key from X-API-Key header

    Returns:
        dict: {
            "developer_id": PydanticObjectId,
            "workspace_id": Optional[PydanticObjectId],
            "api_key_id": PydanticObjectId
        }

    Raises:
        HTTPException: 401 if key is invalid, expired, or inactive
        HTTPException: 429 if rate limit exceeded
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required. Please provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Validate key format
    if not x_api_key.startswith("urisocial_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format. Key must start with 'urisocial_'.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Hash the key and lookup in database
    key_hash = hash_api_key(x_api_key)
    api_key = await APIKey.find_one(APIKey.key == key_hash)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key. Please check your credentials.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Check if key is active
    if not api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has been revoked. Please create a new key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Check if key is expired (timezone-aware comparison)
    now = datetime.now(timezone.utc)
    if api_key.expires_at:
        # Make expires_at timezone-aware if it isn't
        expires_at = api_key.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"API key expired on {expires_at.strftime('%Y-%m-%d')}. Please renew your subscription or create a new key.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    # Check IP whitelisting (if configured)
    client_ip = get_client_ip(request)
    require_ip_whitelist(api_key, client_ip)

    # Check rate limits (will raise 429 if exceeded) — raw request throttling,
    # unrelated to billing, protects infrastructure regardless of plan.
    await check_rate_limit(api_key.id)

    # Check monthly credit quota — only free-tier developers are ever
    # blocked here (paid tiers allow overage, billed later via invoice), so
    # this only queries the database for free-tier callers.
    quota = await usage_service.check_credit_quota(str(api_key.developer_id))
    if not quota["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=quota["reason"],
            headers={
                "X-Credits-Limit": str(quota["limit"]),
                "X-Credits-Used": str(quota["current_usage"]),
            },
        )

    # Update last_used_at timestamp and metadata (timezone-aware)
    api_key.last_used_at = now.replace(tzinfo=None)  # Store as naive UTC in MongoDB
    api_key.last_ip_address = client_ip
    api_key.user_agent = request.headers.get("User-Agent")
    await api_key.save()

    # Return developer context and API key object for proxying
    return {
        "developer_id": api_key.developer_id,
        "workspace_id": api_key.workspace_id,
        "api_key_id": api_key.id,
        "api_key": api_key,  # Include full API key for scope checking
    }
