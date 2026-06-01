"""
Enterprise-grade API Key management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timedelta, timezone
from typing import List
from beanie import PydanticObjectId

from app.schemas.api_key import (
    CreateAPIKeyRequest, CreateAPIKeyResponse,
    APIKeyResponse, UpdateAPIKeyRequest
)
from app.models.api_key import APIKey, APIKeyScope
from app.models.developer import Developer
from app.api.deps import get_current_developer
from app.core.api_key import generate_api_key, hash_api_key, get_key_prefix
from app.services.key_rotation import (
    rotate_key, enable_auto_rotation, disable_auto_rotation,
    get_rotation_status
)
from app.services.key_expiry import get_expiry_info
from app.services.scope_validator import get_effective_scopes
from app.services.ip_validator import parse_ip_list
from app.services.webhook_dispatcher import trigger_event
from app.models.webhook import WebhookEvent

router = APIRouter()


@router.post("", response_model=CreateAPIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: CreateAPIKeyRequest,
    current_developer: Developer = Depends(get_current_developer)
):
    """
    Create a new API key with advanced features.

    **Features:**
    - Scope-based permissions
    - IP whitelisting
    - Automatic rotation
    - Environment tagging

    **WARNING**: The full API key is only shown once during creation.
    Store it securely - you won't be able to retrieve it again!
    """
    # Validate IP whitelist format if provided
    if request.whitelisted_ips:
        try:
            validated_ips = parse_ip_list(",".join(request.whitelisted_ips))
            request.whitelisted_ips = validated_ips
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    # Generate API key
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    key_prefix = get_key_prefix(api_key)

    # Create API key document with advanced features
    now = datetime.now(timezone.utc)
    new_key = APIKey(
        key=key_hash,
        key_prefix=key_prefix,
        name=request.name,
        description=request.description,
        developer_id=current_developer.id,
        is_active=True,
        created_at=now.replace(tzinfo=None),

        # Scopes and permissions
        scopes=request.scopes or [APIKeyScope.ADMIN],

        # IP whitelisting
        whitelisted_ips=request.whitelisted_ips or [],

        # Environment
        environment=request.environment,

        # Auto-rotation
        rotation_enabled=request.rotation_enabled or False,
        rotation_days=request.rotation_days or 90,
    )

    # Set up rotation schedule if enabled
    if new_key.rotation_enabled:
        new_key.last_rotated_at = now.replace(tzinfo=None)
        new_key.next_rotation_at = (now + timedelta(days=new_key.rotation_days)).replace(tzinfo=None)

    await new_key.insert()

    # Trigger webhook event
    await trigger_event(
        developer_id=current_developer.id,
        event=WebhookEvent.API_KEY_CREATED,
        payload={
            "key_id": str(new_key.id),
            "name": new_key.name,
            "scopes": [s.value for s in new_key.scopes],
            "environment": new_key.environment,
        }
    )

    # Return response with full API key (only time it's shown!)
    return CreateAPIKeyResponse(
        api_key=api_key,
        key_id=str(new_key.id),
        key_prefix=key_prefix,
        name=new_key.name,
        description=new_key.description,
        created_at=new_key.created_at
    )


@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_developer: Developer = Depends(get_current_developer)
):
    """
    List all API keys for the authenticated developer.

    Returns masked keys (prefix only) with all metadata.
    """
    keys = await APIKey.find(
        APIKey.developer_id == current_developer.id
    ).sort("-created_at").to_list()

    return [
        APIKeyResponse(
            id=str(key.id),
            key_prefix=key.key_prefix,
            name=key.name,
            description=key.description,
            is_active=key.is_active,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            expires_at=key.expires_at,
            scopes=key.scopes,
            whitelisted_ips=key.whitelisted_ips,
            environment=key.environment,
            rotation_enabled=key.rotation_enabled,
            rotation_days=key.rotation_days,
            last_rotated_at=key.last_rotated_at,
            next_rotation_at=key.next_rotation_at,
            last_ip_address=key.last_ip_address,
            user_agent=key.user_agent,
        )
        for key in keys
    ]


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str,
    current_developer: Developer = Depends(get_current_developer)
):
    """Get detailed information about a specific API key"""
    try:
        key = await APIKey.get(PydanticObjectId(key_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    # Verify ownership
    if key.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this API key"
        )

    return APIKeyResponse(
        id=str(key.id),
        key_prefix=key.key_prefix,
        name=key.name,
        description=key.description,
        is_active=key.is_active,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        expires_at=key.expires_at,
        scopes=key.scopes,
        whitelisted_ips=key.whitelisted_ips,
        environment=key.environment,
        rotation_enabled=key.rotation_enabled,
        rotation_days=key.rotation_days,
        last_rotated_at=key.last_rotated_at,
        next_rotation_at=key.next_rotation_at,
        last_ip_address=key.last_ip_address,
        user_agent=key.user_agent,
    )


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: str,
    request: UpdateAPIKeyRequest,
    current_developer: Developer = Depends(get_current_developer)
):
    """Update an API key's settings"""
    try:
        key = await APIKey.get(PydanticObjectId(key_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    # Verify ownership
    if key.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this API key"
        )

    # Update basic fields
    if request.name is not None:
        key.name = request.name
    if request.description is not None:
        key.description = request.description
    if request.environment is not None:
        key.environment = request.environment

    # Update scopes
    if request.scopes is not None:
        key.scopes = request.scopes

    # Update IP whitelist
    if request.whitelisted_ips is not None:
        try:
            validated_ips = parse_ip_list(",".join(request.whitelisted_ips))
            key.whitelisted_ips = validated_ips
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    # Update rotation settings
    if request.rotation_enabled is not None:
        if request.rotation_enabled and not key.rotation_enabled:
            # Enable rotation
            await enable_auto_rotation(key, request.rotation_days or 90)
        elif not request.rotation_enabled and key.rotation_enabled:
            # Disable rotation
            await disable_auto_rotation(key)
    elif request.rotation_days is not None and key.rotation_enabled:
        # Update rotation interval
        key.rotation_days = request.rotation_days

    await key.save()

    return APIKeyResponse(
        id=str(key.id),
        key_prefix=key.key_prefix,
        name=key.name,
        description=key.description,
        is_active=key.is_active,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        expires_at=key.expires_at,
        scopes=key.scopes,
        whitelisted_ips=key.whitelisted_ips,
        environment=key.environment,
        rotation_enabled=key.rotation_enabled,
        rotation_days=key.rotation_days,
        last_rotated_at=key.last_rotated_at,
        next_rotation_at=key.next_rotation_at,
        last_ip_address=key.last_ip_address,
        user_agent=key.user_agent,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    current_developer: Developer = Depends(get_current_developer)
):
    """
    Revoke (deactivate) an API key.

    This makes the key unusable for authentication.
    The key record is kept for audit purposes.
    """
    try:
        key = await APIKey.get(PydanticObjectId(key_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    # Verify ownership
    if key.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to revoke this API key"
        )

    # Revoke the key
    key.is_active = False
    await key.save()

    # Trigger webhook event
    await trigger_event(
        developer_id=current_developer.id,
        event=WebhookEvent.API_KEY_REVOKED,
        payload={
            "key_id": str(key.id),
            "name": key.name,
        }
    )

    return None


@router.post("/{key_id}/rotate", response_model=CreateAPIKeyResponse, status_code=status.HTTP_200_OK)
async def rotate_api_key(
    key_id: str,
    current_developer: Developer = Depends(get_current_developer)
):
    """
    Manually rotate an API key (generate new key value).

    **WARNING**: The old key will be invalidated and the new key is only shown once!
    """
    try:
        key = await APIKey.get(PydanticObjectId(key_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    # Verify ownership
    if key.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to rotate this API key"
        )

    # Rotate the key
    updated_key, new_plain_key = await rotate_key(key.id)

    # Trigger webhook event
    await trigger_event(
        developer_id=current_developer.id,
        event=WebhookEvent.API_KEY_ROTATED,
        payload={
            "key_id": str(updated_key.id),
            "name": updated_key.name,
        }
    )

    return CreateAPIKeyResponse(
        api_key=new_plain_key,  # Full new key shown ONCE
        key_id=str(updated_key.id),
        key_prefix=updated_key.key_prefix,
        name=updated_key.name,
        description=updated_key.description,
        created_at=updated_key.created_at,
        warning="⚠️ Your API key has been rotated! The old key is now invalid. Save this new key securely!"
    )


@router.get("/{key_id}/info")
async def get_api_key_info(
    key_id: str,
    current_developer: Developer = Depends(get_current_developer)
):
    """Get detailed information about API key status (expiry, rotation, scopes)"""
    try:
        key = await APIKey.get(PydanticObjectId(key_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    # Verify ownership
    if key.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this API key"
        )

    # Get detailed information
    expiry_info = await get_expiry_info(key)
    rotation_info = await get_rotation_status(key)
    effective_scopes = get_effective_scopes(key)

    return {
        "key_id": str(key.id),
        "name": key.name,
        "is_active": key.is_active,

        # Expiry information
        "expiry": expiry_info,

        # Rotation information
        "rotation": rotation_info,

        # Scope information
        "scopes": {
            "assigned": [s.value for s in key.scopes],
            "effective": [s.value for s in effective_scopes],
        },

        # IP whitelist
        "ip_whitelist": {
            "enabled": len(key.whitelisted_ips) > 0,
            "ips": key.whitelisted_ips,
        },

        # Environment
        "environment": key.environment,

        # Usage metadata
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "last_ip_address": key.last_ip_address,
        "user_agent": key.user_agent,
    }
