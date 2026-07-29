"""
Proxy endpoints to forward authenticated requests to main backend
"""
import httpx
import time
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, Response, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.middleware.api_key_validation import validate_api_key
from app.services.usage_tracker import increment_usage, log_request

router = APIRouter()

# Main backend URL from settings
MAIN_BACKEND_URL = getattr(settings, "MAIN_BACKEND_URL", "https://api.urisocial.com")


def _parse_credits_header(raw: Optional[str]) -> int:
    """Defensively parse X-URI-Credits-Consumed — malformed/missing always
    means 0, never an error that could break the proxy response."""
    if not raw:
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


async def proxy_request(
    request: Request,
    path: str,
    developer_context: dict,
) -> Response:
    """
    Proxy request to main backend with developer context.

    Args:
        request: Original FastAPI request
        path: Path to forward to (e.g., "/social-media/generate")
        developer_context: Developer context from API key validation

    Returns:
        Response from main backend
    """
    # Start timing
    start_time = time.time()

    # Build target URL
    target_url = f"{MAIN_BACKEND_URL}{path}"

    # Get original request body (wrapped in try-except for disconnects)
    try:
        body = await request.body()
    except Exception:
        body = b""

    # Get original headers but remove Host and potentially problematic headers
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("x-api-key", None)  # Remove API key, we'll use internal auth

    # Add developer context to headers for main backend
    headers["X-Developer-ID"] = str(developer_context["developer_id"])
    if developer_context.get("workspace_id"):
        headers["X-Workspace-ID"] = str(developer_context["workspace_id"])
    headers["X-API-Key-ID"] = str(developer_context["api_key_id"])

    # Prove this request actually came from the gateway (not a forged
    # header sent directly to the main backend) via a shared secret that
    # must match uri-social-backend's SDK_GATEWAY_INTERNAL_SECRET exactly.
    headers["X-Internal-Service"] = settings.SDK_GATEWAY_INTERNAL_SECRET

    # Get client info for logging
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Forward the request
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=request.query_params,
            )

            # Calculate response time
            response_time_ms = int((time.time() - start_time) * 1000)

            # Increment usage counter (fire and forget)
            await increment_usage(
                api_key_id=developer_context["api_key_id"],
                developer_id=developer_context["developer_id"],
                workspace_id=developer_context.get("workspace_id"),
            )

            # Real cost of this request in URI Social credits, reported by the
            # main backend on generation endpoints (see
            # complete_social_manager.py's _report_sdk_credit_cost). Absent/
            # invalid on every other request, which is the correct default —
            # only generation actions have a real AI-generation cost to meter.
            credits_consumed = _parse_credits_header(response.headers.get("x-uri-credits-consumed"))

            # Log request (fire and forget)
            await log_request(
                api_key_id=developer_context["api_key_id"],
                developer_id=developer_context["developer_id"],
                workspace_id=developer_context.get("workspace_id"),
                endpoint=path,
                method=request.method,
                status_code=response.status_code,
                response_time_ms=response_time_ms,
                ip_address=client_ip,
                user_agent=user_agent,
                credits_consumed=credits_consumed,
            )

            # Return response with same status code and headers
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type"),
            )

        except httpx.RequestError as e:
            # Log error
            response_time_ms = int((time.time() - start_time) * 1000)
            await log_request(
                api_key_id=developer_context["api_key_id"],
                developer_id=developer_context["developer_id"],
                workspace_id=developer_context.get("workspace_id"),
                endpoint=path,
                method=request.method,
                status_code=503,
                response_time_ms=response_time_ms,
                ip_address=client_ip,
                user_agent=user_agent,
                error_message=str(e),
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to main backend: {str(e)}",
            )
        except Exception as e:
            # Log error
            response_time_ms = int((time.time() - start_time) * 1000)
            await log_request(
                api_key_id=developer_context["api_key_id"],
                developer_id=developer_context["developer_id"],
                workspace_id=developer_context.get("workspace_id"),
                endpoint=path,
                method=request.method,
                status_code=500,
                response_time_ms=response_time_ms,
                ip_address=client_ip,
                user_agent=user_agent,
                error_message=str(e),
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Proxy error: {str(e)}",
            )


@router.api_route(
    "/social-media/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    tags=["Social Media Proxy"],
    operation_id="proxy_social_media_{method}",
)
async def proxy_social_media(
    path: str,
    request: Request,
    developer_context: dict = Depends(validate_api_key),
):
    """
    Proxy social media manager endpoints to main backend.

    All requests to /social-media/* will be forwarded to the main backend
    with developer authentication.
    """
    return await proxy_request(
        request=request,
        path=f"/social-media/{path}",
        developer_context=developer_context,
    )


@router.api_route(
    "/workspace/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    tags=["Workspace Proxy"],
    operation_id="proxy_workspace_{method}",
)
async def proxy_workspace(
    path: str,
    request: Request,
    developer_context: dict = Depends(validate_api_key),
):
    """
    Proxy workspace endpoints to main backend.

    All requests to /workspace/* will be forwarded to the main backend
    with developer authentication.
    """
    return await proxy_request(
        request=request,
        path=f"/workspace/{path}",
        developer_context=developer_context,
    )


@router.api_route(
    "/client/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    tags=["Client Proxy"],
    operation_id="proxy_client_{method}",
)
async def proxy_client(
    path: str,
    request: Request,
    developer_context: dict = Depends(validate_api_key),
):
    """
    Proxy client endpoints to main backend.

    All requests to /client/* will be forwarded to the main backend
    with developer authentication.
    """
    return await proxy_request(
        request=request,
        path=f"/client/{path}",
        developer_context=developer_context,
    )
