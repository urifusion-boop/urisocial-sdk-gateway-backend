"""
Webhook event dispatcher and delivery service
"""
import hmac
import hashlib
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from beanie import PydanticObjectId

from app.models.webhook import Webhook, WebhookDelivery, WebhookEvent


async def generate_signature(payload: str, secret: str) -> str:
    """
    Generate HMAC SHA256 signature for webhook payload

    Args:
        payload: JSON string of the payload
        secret: Webhook secret

    Returns:
        Hex signature
    """
    return hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()


async def dispatch_webhook(
    webhook: Webhook,
    event: WebhookEvent,
    payload: Dict[str, Any]
) -> WebhookDelivery:
    """
    Dispatch a webhook event

    Args:
        webhook: Webhook configuration
        event: Event type
        payload: Event payload

    Returns:
        WebhookDelivery record
    """
    # Create delivery record
    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        developer_id=webhook.developer_id,
        event=event,
        payload=payload,
        url=webhook.url
    )

    # Prepare payload with metadata
    full_payload = {
        "id": str(delivery.id),
        "event": event.value,
        "created_at": delivery.created_at.isoformat(),
        "data": payload
    }

    # Convert to JSON string for signing
    import json
    payload_str = json.dumps(full_payload, separators=(',', ':'))

    # Generate signature
    signature = await generate_signature(payload_str, webhook.secret)

    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
        "X-Webhook-Event": event.value,
        "X-Webhook-ID": str(delivery.id),
        "User-Agent": "URISocial-Webhook/1.0"
    }

    # Attempt delivery
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook.url,
                content=payload_str,
                headers=headers
            )

            delivery.status_code = response.status_code
            delivery.response_body = response.text[:1000]  # Limit to 1000 chars
            delivery.delivered_at = datetime.now(timezone.utc)

            # Consider 2xx status codes as success
            if 200 <= response.status_code < 300:
                delivery.success = True
                webhook.consecutive_failures = 0
                webhook.last_success_at = datetime.now(timezone.utc)
                webhook.success_count += 1
            else:
                delivery.success = False
                delivery.error_message = f"HTTP {response.status_code}: {response.text[:200]}"
                webhook.consecutive_failures += 1
                webhook.last_failure_at = datetime.now(timezone.utc)
                webhook.failure_count += 1

    except Exception as e:
        delivery.success = False
        delivery.error_message = str(e)[:500]
        delivery.delivered_at = datetime.now(timezone.utc)
        webhook.consecutive_failures += 1
        webhook.last_failure_at = datetime.now(timezone.utc)
        webhook.failure_count += 1

    # Schedule retry if failed and attempts remaining
    if not delivery.success and delivery.attempt < delivery.max_attempts:
        # Exponential backoff: 5min, 30min, 2hr
        retry_delays = [300, 1800, 7200]  # seconds
        delay = retry_delays[delivery.attempt - 1]
        delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)

    # Auto-disable webhook after 10 consecutive failures
    if webhook.consecutive_failures >= 10:
        webhook.is_active = False

    # Update webhook timestamps
    webhook.last_triggered_at = datetime.now(timezone.utc)

    # Save records
    await delivery.save()
    await webhook.save()

    return delivery


async def trigger_event(
    developer_id: PydanticObjectId,
    event: WebhookEvent,
    payload: Dict[str, Any],
    workspace_id: Optional[PydanticObjectId] = None
) -> int:
    """
    Trigger webhook event for all matching webhooks

    Args:
        developer_id: Developer ID
        event: Event type
        payload: Event data
        workspace_id: Optional workspace ID

    Returns:
        Number of webhooks triggered
    """
    # Find all active webhooks subscribed to this event
    query_filter = {
        "developer_id": developer_id,
        "is_active": True
    }

    if workspace_id:
        query_filter["workspace_id"] = workspace_id

    webhooks = await Webhook.find(query_filter).to_list()

    triggered_count = 0
    for webhook in webhooks:
        # Check if webhook is subscribed to this event
        if event in webhook.events or not webhook.events:  # Empty events = subscribe to all
            await dispatch_webhook(webhook, event, payload)
            triggered_count += 1

    return triggered_count


async def retry_failed_deliveries() -> int:
    """
    Background job: Retry failed webhook deliveries
    Should be run every 5 minutes via cron/scheduler

    Returns:
        Number of deliveries retried
    """
    now = datetime.now(timezone.utc)

    # Find failed deliveries that are ready for retry
    failed_deliveries = await WebhookDelivery.find(
        WebhookDelivery.success == False,
        WebhookDelivery.next_retry_at != None,
        WebhookDelivery.attempt < WebhookDelivery.max_attempts
    ).to_list()

    retried_count = 0

    for delivery in failed_deliveries:
        # Check if retry time has come
        retry_at = delivery.next_retry_at
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)

        if retry_at <= now:
            # Get webhook config
            webhook = await Webhook.get(delivery.webhook_id)
            if not webhook or not webhook.is_active:
                continue

            # Increment attempt
            delivery.attempt += 1

            # Retry delivery
            import json
            full_payload = {
                "id": str(delivery.id),
                "event": delivery.event.value,
                "created_at": delivery.created_at.isoformat(),
                "data": delivery.payload
            }
            payload_str = json.dumps(full_payload, separators=(',', ':'))
            signature = await generate_signature(payload_str, webhook.secret)

            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
                "X-Webhook-Event": delivery.event.value,
                "X-Webhook-ID": str(delivery.id),
                "X-Webhook-Retry": str(delivery.attempt),
                "User-Agent": "URISocial-Webhook/1.0"
            }

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        webhook.url,
                        content=payload_str,
                        headers=headers
                    )

                    delivery.status_code = response.status_code
                    delivery.response_body = response.text[:1000]
                    delivery.delivered_at = datetime.now(timezone.utc)

                    if 200 <= response.status_code < 300:
                        delivery.success = True
                        delivery.next_retry_at = None
                        webhook.consecutive_failures = 0
                        webhook.last_success_at = datetime.now(timezone.utc)
                        webhook.success_count += 1
                    else:
                        delivery.error_message = f"HTTP {response.status_code}: {response.text[:200]}"
                        webhook.failure_count += 1

            except Exception as e:
                delivery.error_message = str(e)[:500]
                delivery.delivered_at = datetime.now(timezone.utc)
                webhook.failure_count += 1

            # Schedule next retry if still failed
            if not delivery.success and delivery.attempt < delivery.max_attempts:
                retry_delays = [300, 1800, 7200]
                delay = retry_delays[min(delivery.attempt - 1, len(retry_delays) - 1)]
                delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            else:
                delivery.next_retry_at = None

            await delivery.save()
            await webhook.save()
            retried_count += 1

    return retried_count


async def get_webhook_stats(webhook_id: PydanticObjectId) -> dict:
    """
    Get delivery statistics for a webhook

    Args:
        webhook_id: Webhook ID

    Returns:
        Dict with statistics
    """
    # Get all deliveries for this webhook
    deliveries = await WebhookDelivery.find(
        WebhookDelivery.webhook_id == webhook_id
    ).to_list()

    total = len(deliveries)
    successful = sum(1 for d in deliveries if d.success)
    failed = total - successful

    # Calculate success rate
    success_rate = (successful / total * 100) if total > 0 else 0

    # Get recent deliveries (last 10)
    recent = sorted(deliveries, key=lambda d: d.created_at, reverse=True)[:10]

    return {
        "total_deliveries": total,
        "successful": successful,
        "failed": failed,
        "success_rate": round(success_rate, 2),
        "recent_deliveries": [
            {
                "id": str(d.id),
                "event": d.event.value,
                "success": d.success,
                "status_code": d.status_code,
                "created_at": d.created_at.isoformat(),
                "attempt": d.attempt
            }
            for d in recent
        ]
    }
