"""
Webhook management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import secrets
from beanie import PydanticObjectId

from app.schemas.webhook import (
    CreateWebhookRequest, WebhookResponse, UpdateWebhookRequest,
    WebhookDeliveryResponse, WebhookStatsResponse
)
from app.models.webhook import Webhook, WebhookDelivery
from app.models.developer import Developer
from app.api.deps import get_current_developer
from app.services.webhook_dispatcher import get_webhook_stats

router = APIRouter()


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    request: CreateWebhookRequest,
    current_developer: Developer = Depends(get_current_developer)
):
    """
    Create a new webhook endpoint.

    Subscribe to events and receive real-time notifications when they occur.
    """
    # Generate secret if not provided
    secret = request.secret or secrets.token_urlsafe(32)

    # Create webhook
    webhook = Webhook(
        developer_id=current_developer.id,
        url=request.url,
        description=request.description,
        secret=secret,
        events=request.events,
        is_active=True
    )

    await webhook.insert()

    return WebhookResponse(
        id=str(webhook.id),
        url=webhook.url,
        description=webhook.description,
        events=webhook.events,
        is_active=webhook.is_active,
        created_at=webhook.created_at,
        last_triggered_at=webhook.last_triggered_at,
        consecutive_failures=webhook.consecutive_failures,
        last_failure_at=webhook.last_failure_at,
        last_success_at=webhook.last_success_at,
        success_count=webhook.success_count,
        failure_count=webhook.failure_count,
    )


@router.get("", response_model=List[WebhookResponse])
async def list_webhooks(
    current_developer: Developer = Depends(get_current_developer)
):
    """List all webhooks for the authenticated developer."""
    webhooks = await Webhook.find(
        Webhook.developer_id == current_developer.id
    ).sort("-created_at").to_list()

    return [
        WebhookResponse(
            id=str(wh.id),
            url=wh.url,
            description=wh.description,
            events=wh.events,
            is_active=wh.is_active,
            created_at=wh.created_at,
            last_triggered_at=wh.last_triggered_at,
            consecutive_failures=wh.consecutive_failures,
            last_failure_at=wh.last_failure_at,
            last_success_at=wh.last_success_at,
            success_count=wh.success_count,
            failure_count=wh.failure_count,
        )
        for wh in webhooks
    ]


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: str,
    current_developer: Developer = Depends(get_current_developer)
):
    """Get details of a specific webhook."""
    try:
        webhook = await Webhook.get(PydanticObjectId(webhook_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    # Verify ownership
    if webhook.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this webhook"
        )

    return WebhookResponse(
        id=str(webhook.id),
        url=webhook.url,
        description=webhook.description,
        events=webhook.events,
        is_active=webhook.is_active,
        created_at=webhook.created_at,
        last_triggered_at=webhook.last_triggered_at,
        consecutive_failures=webhook.consecutive_failures,
        last_failure_at=webhook.last_failure_at,
        last_success_at=webhook.last_success_at,
        success_count=webhook.success_count,
        failure_count=webhook.failure_count,
    )


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    request: UpdateWebhookRequest,
    current_developer: Developer = Depends(get_current_developer)
):
    """Update a webhook's configuration."""
    try:
        webhook = await Webhook.get(PydanticObjectId(webhook_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    # Verify ownership
    if webhook.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this webhook"
        )

    # Update fields
    if request.url is not None:
        webhook.url = request.url
    if request.description is not None:
        webhook.description = request.description
    if request.events is not None:
        webhook.events = request.events
    if request.is_active is not None:
        webhook.is_active = request.is_active

    await webhook.save()

    return WebhookResponse(
        id=str(webhook.id),
        url=webhook.url,
        description=webhook.description,
        events=webhook.events,
        is_active=webhook.is_active,
        created_at=webhook.created_at,
        last_triggered_at=webhook.last_triggered_at,
        consecutive_failures=webhook.consecutive_failures,
        last_failure_at=webhook.last_failure_at,
        last_success_at=webhook.last_success_at,
        success_count=webhook.success_count,
        failure_count=webhook.failure_count,
    )


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    current_developer: Developer = Depends(get_current_developer)
):
    """Delete a webhook."""
    try:
        webhook = await Webhook.get(PydanticObjectId(webhook_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    # Verify ownership
    if webhook.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this webhook"
        )

    await webhook.delete()
    return None


@router.get("/{webhook_id}/deliveries", response_model=List[WebhookDeliveryResponse])
async def list_webhook_deliveries(
    webhook_id: str,
    current_developer: Developer = Depends(get_current_developer),
    limit: int = 50
):
    """Get delivery history for a webhook."""
    try:
        webhook = await Webhook.get(PydanticObjectId(webhook_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    # Verify ownership
    if webhook.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this webhook"
        )

    # Get deliveries
    deliveries = await WebhookDelivery.find(
        WebhookDelivery.webhook_id == webhook.id
    ).sort("-created_at").limit(limit).to_list()

    return [
        WebhookDeliveryResponse(
            id=str(d.id),
            event=d.event,
            url=d.url,
            status_code=d.status_code,
            success=d.success,
            error_message=d.error_message,
            created_at=d.created_at,
            delivered_at=d.delivered_at,
            attempt=d.attempt,
            max_attempts=d.max_attempts,
        )
        for d in deliveries
    ]


@router.get("/{webhook_id}/stats", response_model=WebhookStatsResponse)
async def get_webhook_statistics(
    webhook_id: str,
    current_developer: Developer = Depends(get_current_developer)
):
    """Get delivery statistics for a webhook."""
    try:
        webhook = await Webhook.get(PydanticObjectId(webhook_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    # Verify ownership
    if webhook.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this webhook"
        )

    stats = await get_webhook_stats(webhook.id)

    return WebhookStatsResponse(**stats)


@router.post("/{webhook_id}/test", status_code=status.HTTP_200_OK)
async def test_webhook(
    webhook_id: str,
    current_developer: Developer = Depends(get_current_developer)
):
    """Send a test event to verify webhook is working."""
    try:
        webhook = await Webhook.get(PydanticObjectId(webhook_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    # Verify ownership
    if webhook.developer_id != current_developer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to test this webhook"
        )

    # Send test event
    from app.services.webhook_dispatcher import dispatch_webhook
    from app.models.webhook import WebhookEvent

    delivery = await dispatch_webhook(
        webhook=webhook,
        event=WebhookEvent.API_KEY_CREATED,  # Use a test event
        payload={
            "test": True,
            "message": "This is a test webhook delivery",
            "timestamp": webhook.created_at.isoformat(),
        }
    )

    return {
        "success": delivery.success,
        "status_code": delivery.status_code,
        "error_message": delivery.error_message,
        "message": "Test webhook sent successfully" if delivery.success else "Test webhook failed"
    }
