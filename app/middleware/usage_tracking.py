"""
Usage Tracking Middleware
Tracks all API requests for billing and rate limiting
"""
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.usage_service import usage_service


class UsageTrackingMiddleware(BaseHTTPMiddleware):
    """
    Tracks API usage for billing

    Logs all requests to usage database and checks rate limits
    """

    async def dispatch(self, request: Request, call_next):
        # Skip tracking for non-proxy endpoints
        if not request.url.path.startswith("/api/v1/social-media") and \
           not request.url.path.startswith("/api/v1/proxy"):
            return await call_next(request)

        # Skip health check and docs
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        start_time = time.time()
        user_id = None
        api_key_id = None
        workspace_id = None

        # Extract user info from API key header
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")

        if api_key:
            try:
                # Validate API key and get user info
                from app.models.api_key import APIKey
                from app.core.api_key import hash_api_key

                # Hash the API key to find it in database
                key_hash = hash_api_key(api_key)
                api_key_obj = await APIKey.find_one(
                    APIKey.key == key_hash,
                    APIKey.is_active == True
                )

                if api_key_obj:
                    user_id = str(api_key_obj.developer_id)
                    api_key_id = str(api_key_obj.id)
                    workspace_id = str(api_key_obj.workspace_id) if api_key_obj.workspace_id else None

                    # Check rate limits before processing
                    rate_limit_check = await usage_service.check_rate_limit(user_id)

                    if not rate_limit_check["allowed"]:
                        # Return 429 Too Many Requests
                        return Response(
                            content=f'{{"error": "{rate_limit_check["reason"]}"}}',
                            status_code=429,
                            media_type="application/json",
                            headers={
                                "X-RateLimit-Limit": str(rate_limit_check["limit"]),
                                "X-RateLimit-Remaining": "0",
                                "X-RateLimit-Reset": str(int(time.time()) + 86400)
                            }
                        )

            except Exception as e:
                print(f"❌ Error validating API key: {str(e)}")

        # Process request
        response = await call_next(request)

        # Track usage if we have user info
        if user_id and api_key_id:
            duration_ms = (time.time() - start_time) * 1000

            try:
                await usage_service.track_request(
                    user_id=user_id,
                    api_key_id=api_key_id,
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("User-Agent"),
                    workspace_id=workspace_id
                )

                # Add usage headers to response
                usage = await usage_service.get_current_usage(user_id)

                response.headers["X-RateLimit-Limit"] = str(usage["included_requests"])
                response.headers["X-RateLimit-Remaining"] = str(max(0, usage["included_requests"] - usage["total_requests"]))
                response.headers["X-RateLimit-Used"] = str(usage["total_requests"])

                # Warn if in overage
                if usage["overage_requests"] > 0:
                    response.headers["X-Overage-Warning"] = "true"
                    response.headers["X-Overage-Cost-NGN"] = str(usage["overage_cost_ngn"])

            except Exception as e:
                # Log error but don't fail the request
                print(f"❌ Error tracking usage: {str(e)}")

        return response
