"""
Lightweight in-process background scheduler.

No job-queue dependency (Celery, APScheduler, etc.) exists anywhere in this
project, so periodic maintenance work — retrying failed webhook deliveries,
checking paid subscriptions for quota-threshold webhook events — has never
actually run despite the code for it existing (webhook_dispatcher.py's
retry_failed_deliveries() docstring even says "Should be run every 5 minutes
via cron/scheduler", but nothing ever called it). This starts two simple
asyncio background loops on app startup instead of pulling in a full job
queue for what is, for a single-instance FastAPI service, a very small need.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

WEBHOOK_RETRY_INTERVAL_SECONDS = 300  # 5 minutes
QUOTA_CHECK_INTERVAL_SECONDS = 1800  # 30 minutes
SUBSCRIPTION_HOUSEKEEPING_INTERVAL_SECONDS = 1800  # 30 minutes

_background_tasks: list = []


async def _webhook_retry_loop() -> None:
    from app.services.webhook_dispatcher import retry_failed_deliveries

    while True:
        try:
            await asyncio.sleep(WEBHOOK_RETRY_INTERVAL_SECONDS)
            retried = await retry_failed_deliveries()
            if retried:
                logger.info(f"Webhook retry loop: retried {retried} failed delivery(ies)")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Webhook retry loop error: {e}")


async def _quota_check_loop() -> None:
    from app.services.usage_service import usage_service

    while True:
        try:
            await asyncio.sleep(QUOTA_CHECK_INTERVAL_SECONDS)
            await usage_service.check_paid_subscription_quota_events()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Quota check loop error: {e}")


async def _subscription_housekeeping_loop() -> None:
    """
    Closes out billing periods that have ended (generating the closing
    invoice, then canceling or marking past_due — see
    subscription_service.process_expired_periods) and revokes API keys
    past their expiry date. Neither of these ran at all before this
    scheduler existed: subscriptions never actually expired regardless of
    cancel_at_period_end, no invoice was ever generated for any period, and
    expired keys stayed is_active=True in the database (though request-time
    validation already independently rejects them by expires_at).
    """
    from app.services.subscription_service import subscription_service
    from app.services.key_expiry import revoke_expired_keys

    while True:
        try:
            await asyncio.sleep(SUBSCRIPTION_HOUSEKEEPING_INTERVAL_SECONDS)
            await subscription_service.process_expired_periods()
            revoked = await revoke_expired_keys()
            if revoked:
                logger.info(f"Subscription housekeeping loop: revoked {revoked} expired API key(s)")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Subscription housekeeping loop error: {e}")


def start_background_jobs() -> None:
    """Call once from the app's startup/lifespan handler."""
    _background_tasks.append(asyncio.create_task(_webhook_retry_loop()))
    _background_tasks.append(asyncio.create_task(_quota_check_loop()))
    _background_tasks.append(asyncio.create_task(_subscription_housekeeping_loop()))
    logger.info("Background jobs started: webhook retry loop, quota check loop, subscription housekeeping loop")


def stop_background_jobs() -> None:
    """Call once from the app's shutdown handler."""
    for task in _background_tasks:
        task.cancel()
    _background_tasks.clear()
