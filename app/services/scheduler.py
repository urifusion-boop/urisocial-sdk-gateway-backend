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


def start_background_jobs() -> None:
    """Call once from the app's startup/lifespan handler."""
    _background_tasks.append(asyncio.create_task(_webhook_retry_loop()))
    _background_tasks.append(asyncio.create_task(_quota_check_loop()))
    logger.info("Background jobs started: webhook retry loop, quota check loop")


def stop_background_jobs() -> None:
    """Call once from the app's shutdown handler."""
    for task in _background_tasks:
        task.cancel()
    _background_tasks.clear()
